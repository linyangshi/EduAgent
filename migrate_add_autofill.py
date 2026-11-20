"""
数据库迁移：添加自动填充相关字段
Migration: Add auto-fill related columns to user_sessions table
"""

from flask import Flask
from models.user import db, UserSession
from config.settings import DATABASE_URL
import sqlalchemy as sa

def run_migration():
    """运行迁移"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        # 检查列是否存在
        inspector = sa.inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('user_sessions')]
        
        print(f"现有列: {columns}")
        
        # 添加 remember_me 列
        if 'remember_me' not in columns:
            print("添加 remember_me 列...")
            db.session.execute(sa.text(
                "ALTER TABLE user_sessions ADD COLUMN remember_me BOOLEAN DEFAULT FALSE NOT NULL"
            ))
            print("✅ remember_me 列添加成功")
        else:
            print("✓ remember_me 列已存在")
        
        # 添加 encrypted_credentials 列
        if 'encrypted_credentials' not in columns:
            print("添加 encrypted_credentials 列...")
            db.session.execute(sa.text(
                "ALTER TABLE user_sessions ADD COLUMN encrypted_credentials TEXT"
            ))
            print("✅ encrypted_credentials 列添加成功")
        else:
            print("✓ encrypted_credentials 列已存在")
        
        db.session.commit()
        print("\n✅ 迁移完成！")

if __name__ == '__main__':
    run_migration()
