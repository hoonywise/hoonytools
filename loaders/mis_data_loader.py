import os
import pandas as pd
import sys
import traceback
from pathlib import Path

# Ensure the project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    
# Import in this specific order to avoid circular dependencies
from config import PROJECT_PATH as BASE_PATH
from config import PROJECT_PATH as base_path
from libs import abort_manager
from libs.oracle_db_connector import get_db_connection
from libs.layout_definitions import LAYOUTS
from libs.table_utils import create_index_if_columns_exist
import logging

# Directory where the MIS .dat files are placed
MIS_FOLDER = Path(__file__).resolve().parent.parent / "MIS"

logger = logging.getLogger(__name__)

def parse_fixed_width_file(file_path, layout, file_code=None):
    """
    Parse a fixed-width file according to the specified layout.
    Added file_code parameter to handle special cases for FA and SF files.
    """
    data = []
    max_len = max(end for _, _, end in layout)

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
            content = file.read()

            # Try splitting on \r (Mac-style) if no \n is present
            if '\n' not in content:
                print("[DEBUG] Splitting on \\r")
                lines = content.split('\r')
            else:
                print("[DEBUG] Splitting on \\n")
                lines = content.splitlines()
                
            print(f"[DEBUG] Total lines detected: {len(lines)}")
            print(f"[DEBUG] Layout expects width: {max_len}")    

            # 🔍 Inspect first 5 lines for length & content
            for i, raw_line in enumerate(lines[:5]):
                print(f"[DEBUG] Line {i} — len={len(raw_line)} — {repr(raw_line)}")

            for i, line in enumerate(lines):
                if not line.strip():
                    continue

                if len(line) < max_len:
                    print(f"[DEBUG] Padding short line {i} from {len(line)} → {max_len}")
                    padded = line.ljust(max_len)
                else:
                    padded = line[:max_len]  # Truncate if longer than expected

                try:
                    # Special handling for FA and SF files
                    if file_code in ["FA", "SF", "SB"]:
                        # Create a row with all fields initialized to empty strings
                        row = {name: "" for name, _, _ in layout}
                        
                        # Only extract fields that are within the actual line length
                        for name, start, end in layout:
                            if start < len(padded):
                                actual_end = min(end, len(padded))
                                row[name] = padded[start:actual_end]
                    else:
                        # Standard parsing for other file types
                        row = {
                            name: padded[start:end]
                            for name, start, end in layout
                        }
                    data.append(row)
                except Exception as e:
                    print(f"❌ Error parsing line {i}: {e}")
                    print(f"🔍 Line content: {repr(line)}")
                    if file_code in ["FA", "SF", "SB"]:
                        # For FA/SF files, continue with best-effort parsing
                        print(f"⚠️ Continuing with best-effort parsing for {file_code} file")
                        continue
                    else:
                        raise
    except Exception as e:
        print(f"❌ Fatal error in parse_fixed_width_file: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise

    print(f"✅ Returning parsed DataFrame with {len(data)} rows")
    return pd.DataFrame(data)

def load_to_oracle(df, table_name, annual_code, conn, cursor, layout, file_code=None):
    """Load data into Oracle Database"""
    logger.info(f"Starting load_to_oracle for table {table_name} with {len(df)} rows")
    
    try:
        df.columns = [str(col).upper() for col in df.columns]
        print(f"📊 DataFrame loaded for {table_name} — {len(df)} rows")
        print(f"🧪 Columns: {df.columns.tolist()}")
    except Exception as e:
        print(f"🔥 Failed to uppercase column names: {e}")
        print("🔍 Raw df.columns:", df.columns)
        raise
    
    print(f"📊 DataFrame loaded for {table_name} — {len(df)} rows")
    if not df.empty:
        print("🧪 First row sample:", df.iloc[0].to_dict())
    else:
        print("❌ DataFrame is empty!")    
        
    print("🧱 Checking if table exists...")

    try:
        cursor.execute("""
            SELECT COUNT(*) FROM all_tables 
            WHERE table_name = :1 AND owner = 'DWH'
        """, [table_name.upper()])
        exists = cursor.fetchone()[0] > 0
        print(f"✅ Table exists? {exists}")
    except Exception as e:
        print(f"❌ Error checking if table exists: {e}")
        if file_code in ["FA", "SF", "SB"]:
            print(f"⚠️ Continuing despite error for {file_code} file")
            exists = False
        else:
            raise
    
    logger.info(f"About to create table {table_name}")

    if not exists:
        try:
            columns = ', '.join([
                f'{col.upper()} VARCHAR2(2)' if col.upper() == 'GI90_RECORD_CODE' else
                f'{col.upper()} VARCHAR2(3)' if col.upper() in ['GI01_DISTRICT_COLLEGE_ID', 'GI03_TERM_ID'] else
                f'{col.upper()} VARCHAR2(9)' if col.upper() == 'SB00_STUDENT_ID' else
                f'{col.upper()} VARCHAR2(4000)'
                for col in df.columns
            ])
            create_sql = f'CREATE TABLE DWH.{table_name.upper()} ({columns})'
            
            print("📜 SQL:", create_sql)
            
            cursor.execute(create_sql)
            cursor.execute(f'GRANT SELECT ON DWH.{table_name.upper()} TO PUBLIC')
            abort_manager.register_created_table(table_name)
            logger.info(f"Table {table_name} created successfully")
            logger.info(f"🆕 Created table {table_name} and granted SELECT to PUBLIC.")
        except Exception as e:
            logger.error(f"❌ Failed to create table {table_name}: {e}")
            if file_code in ["FA", "SF", "SB"]:
                logger.warning(f"⚠️ Continuing despite table creation error for {file_code} file")
            else:
                return False

        # Create index with special handling for FA and SF files
        if file_code not in ["FA", "SF"]:
            # Only create indexes for non-FA/SF tables to avoid indexing issues
            safe_index_cols = [col for col in ["GI90_RECORD_CODE", "GI01_DISTRICT_COLLEGE_ID", "GI03_TERM_ID"] if col in df.columns]
            logger.debug(f"🔍 Attempting to index columns in {table_name}: {safe_index_cols}")
            try:
                create_index_if_columns_exist(cursor, "DWH", table_name, safe_index_cols)
            except Exception as e:
                logger.warning(f"⚠️ Index creation failed but continuing: {e}")

    try:
        if 'GI03_TERM_ID' in df.columns:
            print(f"🧹 Deleting old data for GI03_TERM_ID = {annual_code}")
            cursor.execute(f'DELETE FROM DWH.{table_name.upper()} WHERE GI03_TERM_ID = :1', [annual_code])
            logger.info(f"🧹 Deleted existing records from {table_name} for GI03_TERM_ID = {annual_code}")
    except Exception as e:
        logger.warning(f"⚠️ Error deleting old data: {e}")
        # Continue despite error

    try:
        columns = ', '.join(f'{col.upper()}' for col in df.columns)
        values = ', '.join(f':{i+1}' for i in range(len(df.columns)))
        insert_sql = f'INSERT INTO DWH.{table_name.upper()} ({columns}) VALUES ({values})'
    except Exception as e:
        logger.error(f"❌ Error preparing INSERT SQL: {e}")
        if file_code in ["FA", "SF", "SB"]:
            logger.warning(f"⚠️ Cannot continue with {file_code} file due to SQL preparation error")
            return False
        else:
            raise
    
    # Drop rows where all values are empty
    try:
        df = df[~(df == '').all(axis=1)]
    except Exception as e:
        logger.warning(f"⚠️ Error dropping empty rows: {e}")
        # Continue despite error

    # Special handling for required fields validation based on file type
    try:
        if file_code in ["FA", "SF", "SB"]:
            # For FA/SF files, use a more lenient approach
            logger.info(f"🔧 Using lenient validation for {file_code} file")
            df = df.fillna('')  # Replace NaN with empty string
            df = df.astype(str)  # Convert all columns to string
        else:
            # For other files, use the standard validation
            required_fields = [name for name, _, _ in layout if 'FILLER' not in name]
            df = df.applymap(lambda x: None if isinstance(x, str) and x.strip() == '' else x)
            df = df.dropna(subset=required_fields, how='any')
            df = df.astype(str)
    except Exception as e:
        logger.warning(f"⚠️ Error during field validation: {e}")
        # Fallback approach for all file types if validation fails
        try:
            df = df[~(df == '').all(axis=1)]
            df = df.fillna('')
            df = df.astype(str)
        except Exception as e2:
            logger.error(f"❌ Even fallback validation failed: {e2}")
            if file_code in ["FA", "SF", "SB"]:
                logger.warning(f"⚠️ Cannot continue with {file_code} file due to validation errors")
                return False
            else:
                raise
    
    print("🧪 Starting insert loop...")
    inserted = 0 

    for _, row in df.iterrows():
        if abort_manager.should_abort:
            abort_manager.cleanup_on_abort(conn, cursor)
            return False
            
        if len(row) != len(df.columns):
            logger.error(f"❌ Row column mismatch in {table_name}: {row}")
            continue  # skip problematic row

        if any(pd.isna(v) for v in row.values):
            logger.warning(f"⚠️ NULL value detected in row for {table_name}: {row}")
        
        try:
            cursor.execute(insert_sql, tuple(row))
            inserted += 1
        except Exception as e:
            print(f"❌ INSERT ERROR: {e}")
            print(f"🧪 Row content: {row.to_dict()}")
            
            if file_code in ["FA", "SF", "SB"]:
                # For FA/SF files, log the error but continue with other rows
                logger.warning(f"⚠️ Error inserting row for {file_code} file, continuing: {e}")
                continue
            else:
                raise
            
    logger.info(f"Successfully loaded {len(df)} rows into {table_name}")    
    logger.info(f"✅ Loaded {inserted} rows into {table_name}")
    return True

def run_mis_loader(existing_conn=None):    
    """
    Main function to load MIS data files into Oracle.
    
    Args:
        existing_conn: Optional database connection. If provided, it will be ignored
                      and a new connection will be created in this thread.
    
    Returns:
        bool: True if successful, False otherwise
    """
    print("🚨 MIS LOADER STARTED")
    print("🚨 ENTERED run_mis_loader")
    
    conn = None  # ✅ Ensure safe cleanup if crash happens before assignment
    cursor = None
    
    try:
        # CRITICAL CHANGE: Always create a new connection in this thread, ignore existing_conn
        print("🔌 Creating new database connection in MIS loader thread")
        from tkinter import _default_root
        if existing_conn:
            conn = existing_conn
        else:
            conn = get_db_connection(force_shared=True, root=_default_root)

        if not conn:
            logger.error("❌ Connection failed. Aborting MIS loader.")
            return
        if not conn:
            logger.error("❌ Could not connect to Oracle.")
            return False
            
        cursor = conn.cursor()
        
        try:
            print("🔧 Calling abort_manager.reset()")
            abort_manager.reset()
            print("✅ abort_manager.reset() complete")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"🔥 Crash in abort_manager.reset(): {e}")
            return False

        print(f"📁 Looking in MIS_FOLDER: {MIS_FOLDER}")
        print(f"📁 Exists? {MIS_FOLDER.exists()}")
        print(f"📁 Is dir? {MIS_FOLDER.is_dir()}")
        
        try:
            folder_contents = list(MIS_FOLDER.glob('*.dat'))
            print(f"📁 Contents: {folder_contents}")
        except Exception as e:
            logger.error(f"❌ Error listing folder contents: {e}")
            return False
        
        if not MIS_FOLDER.exists():
            logger.error(f"❌ ERROR: MIS folder not found at {MIS_FOLDER}")
            return False

        success_count = 0
        error_count = 0
        total_files = 0
        
        preloop_state = f"Start loop — success_count={success_count}, error_count={error_count}, total={total_files}"
        logger.debug(preloop_state)        

        for filename in os.listdir(MIS_FOLDER):
            if filename.endswith(".dat"):
                total_files += 1
                file_path = MIS_FOLDER / filename
                
                try:
                    annual_code = filename[3:6]
                    file_code = filename[-6:-4].upper()
                except Exception as e:
                    logger.error(f"❌ Failed to parse filename {filename}: {e}")
                    error_count += 1
                    continue
                
                # Define table_name for ALL file types
                table_name = f"MIS_{file_code}_IN"
                logger.info(f"Table name will be: {table_name}")                
                print(f"📄 Attempting to parse file: {file_path}")
                print(f"🧪 Layout fields: {len(LAYOUTS[file_code])}")
                logger.info(f"📥 Processing {filename} into {table_name}...")

                try:
                    # Pass file_code to parse_fixed_width_file for special handling
                    df = parse_fixed_width_file(file_path, LAYOUTS[file_code], file_code)
                    print(f"✅ Parsed DataFrame for {filename} — {len(df)} rows")
                    if not df.empty:
                        print("🔎 First 1 row:", df.head(1).to_dict(orient="records"))
                    layout = LAYOUTS[file_code]
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    logger.error(f"🔥 Failed while parsing {filename}: {e}")
                    
                    if file_code in ["FA", "SF", "SB"]:
                        # For FA/SF files, log the error but continue with other files
                        logger.warning(f"⚠️ Error parsing {file_code} file, continuing with other files: {e}")
                        error_count += 1
                        continue
                    else:
                        error_count += 1
                        continue
   
                print("🧪 Calling load_to_oracle with table", table_name)
                
                try:
                    # Pass file_code to load_to_oracle for special handling
                    file_success = load_to_oracle(df, table_name, annual_code, conn, cursor, layout, file_code)
                    if file_success:
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"❌ Error loading {filename}: {e}")
                    
                    if file_code in ["FA", "SF", "SB"]:
                        # For FA/SF files, log the error but continue with other files
                        logger.warning(f"⚠️ Error loading {file_code} file, continuing with other files: {e}")
                        error_count += 1
                        continue
                    else:
                        error_count += 1
                        continue
                    
        logger.info("🧪 ABOUT TO CHECK abort_manager.should_abort")                    
        logger.info(f"🧾 Loop finished. Final counts — success: {success_count}, error: {error_count}, total: {total_files}")                        
        if not abort_manager.should_abort:
            try:                
                conn.commit()
                logger.info("🧪 Commit successful")
                logger.info(f"✅ MIS loading complete: {success_count} files loaded successfully, {error_count} files with errors out of {total_files} total files.")
                return success_count > 0  # Return True if at least one file was loaded successfully
            except Exception as e:
                logger.error(f"❌ Error during final commit: {e}")
                return False
        else:
            logger.warning("⏹️ MIS Loader aborted by user.")
            return False

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"🔥 CRASH in run_mis_loader: {e}")
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as e:
                if "DPY-1001" not in str(e):
                    logger.warning(f"⚠️ Failed to close cursor: {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                if "DPY-1001" not in str(e):
                    logger.warning(f"⚠️ Failed to close connection: {e}")
        
        print("🏁 MIS Loader execution completed")
