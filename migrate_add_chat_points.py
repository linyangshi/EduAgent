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
        
        if 'daily_free_count' not in columns:
            print("Adding daily_free_count column...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_free_count INTEGER NOT NULL DEFAULT 0")
        else:
            print("daily_free_count column already exists.")

        if 'last_free_reset_date' not in columns:
            print("Adding last_free_reset_date column...")
            cursor.execute("ALTER TABLE users ADD COLUMN last_free_reset_date DATE")
        else:
            print("last_free_reset_date column already exists.")

        conn.commit()
        print("✅ Migration completed successfully.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
