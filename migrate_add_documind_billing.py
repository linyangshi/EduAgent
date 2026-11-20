import sqlite3
import os

def migrate():
    db_path = 'eduagent.db'
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        
        new_columns = {
            'weekly_usage_mini': 'INTEGER NOT NULL DEFAULT 0',
            'weekly_usage_flash': 'INTEGER NOT NULL DEFAULT 0',
            'last_weekly_reset_date': 'DATE'
        }

        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                print(f"Adding {col_name} column...")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            else:
                print(f"{col_name} column already exists.")

        conn.commit()
        print("✅ Migration completed successfully.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
