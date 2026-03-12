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
        cursor.execute("PRAGMA table_info(knowledge_bases)")
        columns = [info[1] for info in cursor.fetchall()]
        
        # Add is_public
        if 'is_public' not in columns:
            print("Adding 'is_public' column to knowledge_bases...")
            cursor.execute("ALTER TABLE knowledge_bases ADD COLUMN is_public BOOLEAN DEFAULT 0 NOT NULL")
        else:
            print("'is_public' already exists.")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
