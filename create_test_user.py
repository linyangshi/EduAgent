"""
创建测试用户脚本
Create Test User Script
"""

from getpass import getpass
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from flask import Flask
from models.user import db, User, KnowledgeBase
from config.settings import DATABASE_URL, SECRET_KEY

# 创建Flask应用
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = SECRET_KEY

# 初始化数据库
db.init_app(app)

def create_test_user():
    """创建测试用户"""
    with app.app_context():
        # 创建所有表
        db.create_all()

        # 测试账号信息
        test_username = input("用户名: ").strip()
        test_email = input("邮箱: ").strip()
        test_password = getpass("密码: ")
        if not test_username or not test_email or not test_password:
            raise ValueError("用户名、邮箱和密码均必填")
        test_fullname = "测试用户"

        # 检查用户是否已存在
        existing_user = User.query.filter_by(username=test_username).first()
        if existing_user:
            print(f"⚠️  用户 '{test_username}' 已存在")
            print(f"\n账号信息：")
            print(f"  用户名: {test_username}")
            print(f"  邮箱: {test_email}")

            print(f"  ID: {existing_user.id}")
            return

        # 创建新用户
        user = User(
            username=test_username,
            email=test_email,
            full_name=test_fullname,
            is_active=True,
            is_admin=False
        )
        user.set_password(test_password)

        db.session.add(user)
        db.session.commit()

        # 为用户创建一个默认知识库
        kb = KnowledgeBase(
            name="我的第一个知识库",
            description="这是一个测试知识库，可以上传文档或截图进行问答",
            user_id=user.id
        )
        db.session.add(kb)
        db.session.commit()

        print("✅ 测试账号创建成功！\n")
        print("=" * 60)
        print("账号信息：")
        print("=" * 60)
        print(f"  用户名: {test_username}")
        print(f"  邮箱: {test_email}")

        print(f"  姓名: {test_fullname}")
        print(f"  用户ID: {user.id}")
        print(f"  知识库ID: {kb.id}")
        print("=" * 60)
        print("\n💡 使用方法：")
        print("  1. 启动服务: python web_main.py")
        print("  2. 浏览器访问: http://localhost:5029")
        print("  3. 使用刚创建的账号和密码登录")
        print("  4. 进入知识库开始使用截图问答功能")
        print("=" * 60)

if __name__ == "__main__":
    create_test_user()
