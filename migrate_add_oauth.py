"""
数据库迁移脚本 - 添加OAuth字段
Migration Script - Add OAuth Fields to User Model
"""

from models.user import db, User
from interface.flask_app import UniversityFlaskAPI
from sqlalchemy import text

def migrate_add_oauth_fields():
    """添加OAuth字段到users表"""
    print("🔄 开始数据库迁移：添加OAuth字段...")
    
    try:
        # 检查字段是否已存在
        with db.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result]
            
            if 'wechat_openid' in columns and 'qq_openid' in columns:
                print("✅ OAuth字段已存在，无需迁移")
                return True
        
        # 添加新字段
        print("➕ 添加 wechat_openid 字段...")
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN wechat_openid VARCHAR(100)"
            ))
            conn.commit()
            
        print("➕ 添加 qq_openid 字段...")
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN qq_openid VARCHAR(100)"
            ))
            conn.commit()
            
        # 创建索引
        print("📊 创建索引...")
        with db.engine.connect() as conn:
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX ix_users_wechat_openid ON users (wechat_openid)"
                ))
                conn.commit()
            except Exception as e:
                print(f"   索引可能已存在: {e}")
                
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX ix_users_qq_openid ON users (qq_openid)"
                ))
                conn.commit()
            except Exception as e:
                print(f"   索引可能已存在: {e}")
        
        print("✅ OAuth字段迁移完成!")
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("OAuth字段数据库迁移脚本")
    print("=" * 60)
    
    # 初始化Flask应用以获取数据库上下文
    api = UniversityFlaskAPI()
    
    with api.app.app_context():
        success = migrate_add_oauth_fields()
        
    if success:
        print("\n✅ 迁移成功完成!")
    else:
        print("\n❌ 迁移失败，请检查错误信息")
    
    print("=" * 60)
