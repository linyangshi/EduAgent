from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from config.settings import DATABASE_URL
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def migrate():
    """Add AI Editor billing columns to users table"""
    with app.app_context():
        try:
            # Check if columns exist
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(users)"))
                columns = [row[1] for row in result.fetchall()]
                
                # Add daily_ai_editor_count
                if 'daily_ai_editor_count' not in columns:
                    print("Adding daily_ai_editor_count column...")
                    conn.execute(text("ALTER TABLE users ADD COLUMN daily_ai_editor_count INTEGER NOT NULL DEFAULT 0"))
                else:
                    print("daily_ai_editor_count column already exists.")

                # Add last_ai_editor_reset_date
                if 'last_ai_editor_reset_date' not in columns:
                    print("Adding last_ai_editor_reset_date column...")
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_ai_editor_reset_date DATE"))
                else:
                    print("last_ai_editor_reset_date column already exists.")
                    
                conn.commit()
                print("Migration completed successfully!")
                
        except Exception as e:
            print(f"Migration failed: {e}")
            sys.exit(1)

if __name__ == '__main__':
    migrate()
