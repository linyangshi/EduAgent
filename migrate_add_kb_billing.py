import sqlite3
import os

# 获取当前脚本所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# 数据库文件路径
db_path = os.path.join(current_dir, 'instance', 'eduagent.db')
if not os.path.exists(db_path):
    db_path = os.path.join(current_dir, 'eduagent.db')

print(f"Checking database at: {db_path}")

def run_migration():
    if not os.path.exists(db_path):
        print("Error: Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        
        # Add daily_kb_medium_count
        if 'daily_kb_medium_count' not in columns:
            print("Adding 'daily_kb_medium_count' column...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_kb_medium_count INTEGER DEFAULT 0 NOT NULL")
        else:
            print("'daily_kb_medium_count' already exists.")

        # Add daily_kb_large_count
        if 'daily_kb_large_count' not in columns:
            print("Adding 'daily_kb_large_count' column...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_kb_large_count INTEGER DEFAULT 0 NOT NULL")
        else:
            print("'daily_kb_large_count' already exists.")

        # Add last_kb_upload_reset_date
        if 'last_kb_upload_reset_date' not in columns:
            print("Adding 'last_kb_upload_reset_date' column...")
            cursor.execute("ALTER TABLE users ADD COLUMN last_kb_upload_reset_date DATE DEFAULT NULL")
        else:
            print("'last_kb_upload_reset_date' already exists.")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
