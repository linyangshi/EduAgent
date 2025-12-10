"""
数据库迁移脚本 - 添加商城相关字段和表
Database Migration Script - Add Shop-related Fields and Tables
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from interface.flask_app import UniversityFlaskAPI
from models.user import db, User
from models.shop import RechargeOrder, PointsTransaction

def migrate_database():
    """执行数据库迁移"""
    print("🔄 开始数据库迁移...")
    
    # 创建应用实例
    api = UniversityFlaskAPI()
    
    with api.app.app_context():
        # 检查是否需要添加points_balance字段
        try:
            # 尝试查询一个用户来测试字段是否存在
            user = User.query.first()
            if user:
                _ = user.points_balance
                print("✅ points_balance 字段已存在")
        except Exception:
            # 字段不存在，需要添加
            print("⚠️  points_balance 字段不存在，正在添加...")
            db.session.execute(db.text('ALTER TABLE users ADD COLUMN points_balance INTEGER DEFAULT 0 NOT NULL'))
            db.session.commit()
            print("✅ points_balance 字段添加成功")
        
        # 创建商城相关表
        print("📊 创建商城相关表...")
        db.create_all()
        print("✅ 所有表创建/更新成功")
        
        # 验证所有现有用户都有积分字段
        print("🔍 验证用户积分字段...")
        users = User.query.all()
        for user in users:
            if not hasattr(user, 'points_balance') or user.points_balance is None:
                user.points_balance = 0
        db.session.commit()
        print(f"✅ 已验证 {len(users)} 个用户的积分字段")
    
    print("🎉 数据库迁移完成！")

if __name__ == '__main__':
    migrate_database()
