import sqlite3
import os

# 数据库路径
# settings.py: DATABASE_URL = f'sqlite:///{PROJECT_ROOT}/eduagent.db'
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eduagent.db')

def migrate():
    print(f"Opening database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create feedbacks table
        print("Creating feedbacks table...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            contact VARCHAR(100),
            image_url VARCHAR(500),
            status VARCHAR(20) DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')
        
        conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
