"""
数据库迁移脚本 - 为用户会话表添加设备信息字段
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from interface.flask_app import UniversityFlaskAPI
from models.user import db
from sqlalchemy import text

def migrate_database():
    """执行数据库迁移"""
    
    # 初始化Flask应用
    print("📦 初始化Flask应用...")
    flask_api = UniversityFlaskAPI()
    app = flask_api.app
    
    with app.app_context():
        print("\n🔍 检查数据库迁移需求...")
        
        # 获取当前表结构
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('user_sessions')]
        
        print(f"当前表字段: {', '.join(columns)}")
        
        # 需要添加的新字段
        new_columns = {
            'device_name': 'VARCHAR(200)',
            'device_fingerprint': 'VARCHAR(32)',
            'device_type': 'VARCHAR(50)',
            'browser_name': 'VARCHAR(50)',
            'os_name': 'VARCHAR(50)',
            'last_used_at': 'DATETIME'
        }
        
        # 检查并添加缺失的字段
        migrations_needed = []
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                migrations_needed.append((col_name, col_type))
        
        if not migrations_needed:
            print("\n✅ 数据库结构已是最新，无需迁移")
            return
        
        print(f"\n📝 需要添加 {len(migrations_needed)} 个字段:")
        for col_name, col_type in migrations_needed:
            print(f"  - {col_name} ({col_type})")
        
        print("\n🔧 开始执行迁移...")
        
        try:
            # 逐个添加字段
            for col_name, col_type in migrations_needed:
                # 构建SQL语句（支持不同数据库）
                if 'sqlite' in str(db.engine.url):
                    # SQLite
                    sql = f"ALTER TABLE user_sessions ADD COLUMN {col_name} {col_type}"
                else:
                    # MySQL/PostgreSQL
                    sql = f"ALTER TABLE user_sessions ADD COLUMN {col_name} {col_type}"
                
                print(f"  执行: {sql}")
                db.session.execute(text(sql))
            
            # 为device_fingerprint字段添加索引
            if 'device_fingerprint' in [col for col, _ in migrations_needed]:
                try:
                    if 'sqlite' in str(db.engine.url):
                        index_sql = "CREATE INDEX IF NOT EXISTS idx_device_fingerprint ON user_sessions(device_fingerprint)"
                    else:
                        index_sql = "CREATE INDEX idx_device_fingerprint ON user_sessions(device_fingerprint)"
                    
                    print(f"  执行: {index_sql}")
                    db.session.execute(text(index_sql))
                except Exception as e:
                    print(f"  ⚠️  创建索引时出现警告（可能已存在）: {e}")
            
            # 提交更改
            db.session.commit()
            
            print("\n✅ 数据库迁移完成！")
            print("\n📋 迁移后的数据库结构:")
            
            # 重新获取表结构
            inspector = db.inspect(db.engine)
            columns_after = inspector.get_columns('user_sessions')
            
            for col in columns_after:
                print(f"  - {col['name']:25} {col['type']}")
            
            # 使用设备检测工具更新现有会话的设备信息
            print("\n🔄 更新现有会话的设备信息...")
            from models.user import UserSession
            from utils.device_detector import DeviceDetector
            from datetime import datetime
            
            sessions = UserSession.query.filter_by(is_active=True).all()
            print(f"  找到 {len(sessions)} 个活跃会话")
            
            updated_count = 0
            for session in sessions:
                if session.user_agent and not session.device_name:
                    device_info = DeviceDetector.parse_device_info(
                        session.user_agent, 
                        session.ip_address
                    )
                    
                    session.device_name = device_info['device_name']
                    session.device_fingerprint = device_info['device_fingerprint']
                    session.device_type = device_info['device_type']
                    session.browser_name = device_info['browser_name']
                    session.os_name = device_info['os_name']
                    session.last_used_at = session.created_at
                    
                    updated_count += 1
            
            if updated_count > 0:
                db.session.commit()
                print(f"  ✅ 已更新 {updated_count} 个会话的设备信息")
            else:
                print("  ℹ️  没有需要更新的会话")
            
            print("\n🎉 所有迁移操作已完成！")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 迁移失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    print("=" * 60)
    print("数据库迁移工具 - 用户会话设备信息")
    print("=" * 60)
    migrate_database()

