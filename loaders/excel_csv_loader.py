import os
import pandas as pd
import oracledb
import logging
from tkinter import Tk, filedialog, simpledialog, Toplevel, Label, Checkbutton, IntVar, Button, Entry
import sys
from pathlib import Path
from libs.table_utils import create_index_if_columns_exist

# Add path to shared connector
from libs.paths import PROJECT_PATH as base_path

# Logging setup
logger = logging.getLogger(__name__)

from libs.oracle_db_connector import get_db_connection
from libs import abort_manager

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")

def prompt_schema_choice():
    result = {"choice": None}

    def select_user():
        result["choice"] = "user"
        win.destroy()

    def select_dwh():
        result["choice"] = "dwh"
        win.destroy()

    def cancel():
        result["choice"] = None
        win.destroy()

    win = Toplevel()
    win.title("Select Schema Scope")
    center_window(win, 300, 140)
    win.resizable(False, False)

    Label(win, text="Load to which schema?", font=("Arial", 11, "bold")).pack(pady=(15, 10))

    from tkinter import Frame  # Ensure Frame is imported

    btn_frame = Frame(win)
    btn_frame.pack(pady=5)

    b1 = Button(btn_frame, text="User Schema", width=12, command=select_user)
    b2 = Button(btn_frame, text="DWH Schema", width=12, command=select_dwh)
    b3 = Button(btn_frame, text="Cancel", width=12, command=cancel)

    b1.pack(side="left", padx=5)
    b2.pack(side="left", padx=5)
    b3.pack(side="left", padx=5)

    b1.focus()
    b1.configure(takefocus=True)
    b2.configure(takefocus=True)
    b3.configure(takefocus=True)

    win.grab_set()
    win.wait_window()

    return result["choice"]

# ==== CLEAN COLUMN NAMES TO BE ORACLE-COMPATIBLE ====
def clean_column_names(df):
    df.columns = [col.strip().replace(' ', '_').replace('-', '_').replace('.', '_').upper() for col in df.columns]
    return df

# ==== DROP TABLE IF EXISTS ====
def drop_table_if_exists(cursor, schema, table_name):
    try:
        cursor.execute("""
            SELECT table_name FROM all_tables 
            WHERE table_name = :1 AND owner = :2
        """, [table_name.upper(), schema])
        if cursor.fetchone():
            cursor.execute(f'DROP TABLE {schema}.{table_name.upper()} PURGE')
            logger.info(f"🗑️ Dropped existing table {schema}.{table_name}")
    except Exception as e:
        logger.warning(f"⚠️ Could not drop table {table_name}: {e}")

# ==== CREATE TABLE ====
def create_table(cursor, schema, table_name, df):
    cols_sql = ', '.join([
        f'"{col}" VARCHAR2(9)' if col.upper() in ['PIDM', 'STUDENT_ID'] else
        f'"{col}" VARCHAR2(6)' if col.upper() == 'TERM' else
        f'"{col}" VARCHAR2(4000)'
        for col in df.columns
    ])
    cursor.execute(f'CREATE TABLE {schema}.{table_name.upper()} ({cols_sql})')
    cursor.execute(f'GRANT SELECT ON {schema}.{table_name.upper()} TO PUBLIC')
    abort_manager.register_created_table(table_name)
    logger.info(f"✅ Created table and granted SELECT to PUBLIC: {schema}.{table_name}")
    
    # ==== CREATE INDEX IF COLUMNS EXIST ====
    create_index_if_columns_exist(cursor, schema, table_name, ["PIDM", "TERM", "STUDENT_ID"])

# ==== INSERT DATA ====
def insert_data(cursor, schema, table_name, df, conn):
    columns = ', '.join([f'"{col}"' for col in df.columns])
    values = ', '.join([f':{i+1}' for i in range(len(df.columns))])
    insert_sql = f'INSERT INTO {schema}.{table_name.upper()} ({columns}) VALUES ({values})'

    logger.info(f"📊 Preparing to insert {len(df)} rows into {schema}.{table_name}")

    success_count = 0
    fail_count = 0

    for i, row in df.iterrows():
        if abort_manager.should_abort:
            abort_manager.cleanup_on_abort(conn, cursor)
            return False
        try:
            cursor.execute(insert_sql, tuple(row))
            success_count += 1
        except Exception as e:
            logger.warning(f"❌ Failed to insert row {i+1}: {e}")
            fail_count += 1

    logger.info(f"✅ Inserted {success_count} rows into {schema}.{table_name} ({fail_count} failed)")
    return True

# ==== SHEET SELECTOR DIALOG ====
def select_sheets_gui(file, sheets):
    from tkinter import Toplevel, Label, IntVar, Entry, Button, Checkbutton, Frame, Canvas, Scrollbar, VERTICAL, RIGHT, LEFT, BOTH, Y

    result = {}

    def on_submit():
        for i, sheet in enumerate(sheets):
            if vars_[i]["var"].get():
                entered = vars_[i]["entry"].get().strip()
                if entered:
                    result[sheet] = entered.upper()
        top.destroy()

    def on_cancel():
        result.clear()
        top.destroy()

    top = Toplevel()
    top.title(f"Select Sheets: {os.path.basename(file)}")
    center_window(top, 500, 600)

    Label(
        top,
        text="🔍 Columns named PIDM, TERM, and STUDENT_ID will be indexed (if present)",
        font=("Arial", 9),
        fg="gray"
    ).pack(pady=(0, 10))

    # Top-aligned buttons
    btn_frame = Frame(top)
    btn_frame.pack(pady=(0, 10))
    Button(btn_frame, text="OK", width=10, command=on_submit).pack(side="left", padx=10)
    Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=10)
    
    top.bind("<Return>", lambda event: on_submit())  # ✅ Pressing Enter submits

    # Scrollable canvas for sheet list
    canvas = Canvas(top)
    scrollbar = Scrollbar(top, orient=VERTICAL, command=canvas.yview)
    scrollable_frame = Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill=Y)

    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    vars_ = []
    for sheet in sheets:
        frame = Frame(scrollable_frame)
        var = IntVar(value=1)
        chk = Checkbutton(frame, text=sheet, variable=var)
        chk.pack(side="left")
        entry = Entry(frame)
        default_table_name = f"{os.path.splitext(os.path.basename(file))[0]}_{sheet}".replace('-', '_').replace(' ', '_').upper()
        entry.insert(0, default_table_name)
        entry.pack(side="right", padx=10, fill="x", expand=True)        
        
        if len(vars_) == 0:
            entry.focus()
            entry.select_range(0, 'end')  # ✅ Highlight entire prefilled name    
        
        frame.pack(fill="x", padx=10, pady=2)
        vars_.append({"var": var, "entry": entry})

    top.grab_set()
    top.wait_window()
    return result if result else None

# ==== MAIN FUNCTION ====
def load_multiple_files():
    root = Tk()
    root.withdraw()

    schema_choice = prompt_schema_choice()
    if schema_choice is None:
        return

    conn = get_db_connection(force_shared=(schema_choice == "dwh"))
    if not conn:
        logger.error("❌ Failed to connect to Oracle.")
        return

    file_paths = filedialog.askopenfilenames(filetypes=[("Excel or CSV", ["*.xlsx", "*.xls", "*.csv"])])
    if not file_paths:
        logger.warning("❌ No files selected. Aborting.")
        return

    schema = "DWH" if schema_choice == "dwh" else conn.username.upper()
    logger.info(f"🔐 Connected to schema: {schema}")
    
    cursor = conn.cursor()
    abort_manager.reset()

    try:
        for file_path in file_paths:
            file_name = os.path.splitext(os.path.basename(file_path))[0].replace('-', '_').replace(' ', '_').upper()

            if file_path.endswith('.csv'):
                try:
                    df = pd.read_csv(file_path)
                    df = clean_column_names(df)
                    # Strip file prefix from column names if accidentally included
                    file_prefix = file_name
                    df.columns = [col.replace(f"{file_prefix}_", "") for col in df.columns]
                    df = df.astype(str).fillna('')
                    table_name = file_name
                    from tkinter.simpledialog import askstring
                    override = askstring("Rename Table", f"Default table name is '{table_name}'. Enter a new name or leave blank:")
                    if override and override.strip():
                        table_name = override.strip().replace('-', '_').replace(' ', '_').upper()                    
                    drop_table_if_exists(cursor, schema, table_name)
                    create_table(cursor, schema, table_name, df)
                    success = insert_data(cursor, schema, table_name, df, conn)
                    if not success:
                        return
                    logger.info(f"🚀 Loaded CSV: {schema}.{table_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to load CSV {file_path}: {e}")
            else:
                try:
                    all_sheets = pd.ExcelFile(file_path).sheet_names

                    if len(all_sheets) > 1:
                        sheet_map = select_sheets_gui(file_path, all_sheets)
                        if not sheet_map:
                            logger.warning("❌ User cancelled sheet selection.")
                            return
                    else:
                        sheet_name = all_sheets[0]
                        sheet_map = select_sheets_gui(file_path, [sheet_name])
                        if not sheet_map:
                            logger.warning("❌ User cancelled sheet selection.")
                            return

                    for sheet, table_name in sheet_map.items():
                        df = pd.read_excel(file_path, sheet_name=sheet, dtype=str, na_filter=False)
                        df = df.loc[df.apply(lambda row: any(str(cell).strip() for cell in row), axis=1)]
                        df = clean_column_names(df)

                        drop_table_if_exists(cursor, schema, table_name)
                        create_table(cursor, schema, table_name, df)
                        success = insert_data(cursor, schema, table_name, df, conn)
                        if not success:
                            return
                        logger.info(f"🚀 Loaded Excel: {schema}.{table_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to load Excel {file_path}: {e}")

        conn.commit()
        logger.info("✅ All files processed successfully.")

    except Exception as e:
        logger.error(f"❌ Unexpected error during file processing: {e}")
        abort_manager.cleanup_on_abort(conn, cursor)
        return

    try:
        cursor.close()
    except Exception as e:
        if "DPY-1001" not in str(e):
            logger.warning(f"⚠️ Failed to close cursor: {e}")

    try:
        conn.close()
    except Exception as e:
        if "DPY-1001" not in str(e):
            logger.warning(f"⚠️ Failed to close connection: {e}")

    try:
        root.destroy()
    except Exception:
        pass

if __name__ == '__main__':
    load_multiple_files()

    
