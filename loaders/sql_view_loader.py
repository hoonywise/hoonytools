import tkinter as tk
from tkinter import messagebox, scrolledtext
import logging
from libs.oracle_db_connector import get_db_connection
from libs import session
import ctypes
from libs.paths import ASSETS_PATH

logger = logging.getLogger(__name__)

def run_sql_view_loader(on_finish=None):
    def on_submit():
        view_name = view_name_entry.get().strip()
        sql_query = sql_text.get("1.0", tk.END).strip()
        use_dwh = dwh_var.get()

        if not view_name:
            messagebox.showerror("Missing View Name", "❌ Please enter a view name.")
            return

        if not sql_query:
            messagebox.showerror("Missing SQL", "❌ Please paste a SQL query.")
            return

        # Choose credentials source
        conn = get_db_connection(force_shared=True) if use_dwh else get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            ddl = f"CREATE OR REPLACE VIEW {view_name} AS {sql_query}"
            cursor.execute(ddl)

            # ✅ Grant select to PUBLIC
            grant_stmt = f'GRANT SELECT ON {view_name} TO PUBLIC'
            cursor.execute(grant_stmt)

            conn.commit()
            logger.info(f"✅ View '{view_name}' created and granted SELECT to PUBLIC.")

            messagebox.showinfo("Success", f"✅ View '{view_name}' created successfully.")
            builder_window.destroy()
            if on_finish:
                on_finish()            
        except Exception as e:
            logger.error(f"❌ Error creating view: {e}")
            messagebox.showerror("Error", f"❌ Failed to create view:\n{e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close cursor: {e}")

            try:
                if conn:
                    conn.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close connection: {e}")

    def on_cancel():
        builder_window.destroy()
        if on_finish:
            on_finish()

    builder_window = tk.Toplevel()
    builder_window.title("SQL View Loader")
    builder_window.geometry("800x600")
    builder_window.grab_set()

    # ✅ Ensure taskbar icon and branding is preserved
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        builder_window.iconbitmap(default=icon_path)
    except Exception as e:
        logger.warning(f"⚠️ Failed to set taskbar icon: {e}")

    tk.Label(builder_window, text="Enter SQL to turn into a view:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    sql_text = scrolledtext.ScrolledText(builder_window, width=95, height=20, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10))

    control_frame = tk.Frame(builder_window)
    control_frame.pack(pady=5)

    tk.Label(control_frame, text="View Name:").grid(row=0, column=0, padx=(0, 5))
    view_name_entry = tk.Entry(control_frame, width=40)
    view_name_entry.grid(row=0, column=1, padx=(0, 20))

    dwh_var = tk.BooleanVar()
    dwh_checkbox = tk.Checkbutton(control_frame, text="Load to DWH schema (shared login)", variable=dwh_var)
    dwh_checkbox.grid(row=0, column=2)

    btn_frame = tk.Frame(builder_window)
    btn_frame.pack(pady=15)

    tk.Button(btn_frame, text="Create View", command=on_submit, width=15).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=10)

    # Center on screen
    builder_window.update_idletasks()
    width = builder_window.winfo_width()
    height = builder_window.winfo_height()
    x = (builder_window.winfo_screenwidth() // 2) - (width // 2)
    y = (builder_window.winfo_screenheight() // 2) - (height // 2)
    builder_window.geometry(f"{width}x{height}+{x}+{y}")
    builder_window.mainloop()
