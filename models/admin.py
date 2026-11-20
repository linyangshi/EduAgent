"""
管理员模型
Admin Model - 独立于普通用户的管理员表
"""

import os
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from config.settings import SECRET_KEY
from models.user import db


class Admin(db.Model):
    """管理员模型 - 独立于普通用户"""
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')  # 'super_admin' 或 'admin'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = db.Column(db.Integer, nullable=True)  # 创建此管理员的高级管理员ID
    last_login = db.Column(db.DateTime, nullable=True)
    
    # 角色常量
    ROLE_SUPER_ADMIN = 'super_admin'
    ROLE_ADMIN = 'admin'
    
    def __repr__(self):
        return f'<Admin {self.username} ({self.role})>'
    
    def set_password(self, password):
        """设置密码 - 使用pbkdf2_sha256以兼容Python 3.13"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)
    
    def is_super_admin(self):
        """是否为高级管理员"""
        return self.role == self.ROLE_SUPER_ADMIN
    
    def generate_token(self, expires_in=3600 * 8):
        """生成JWT令牌 - 默认8小时有效"""
        payload = {
            'admin_id': self.id,
            'username': self.username,
            'role': self.role,
            'exp': datetime.now(timezone.utc).timestamp() + expires_in
        }
        return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    
    @staticmethod
    def verify_token(token):
        """验证JWT令牌"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            admin_id = payload.get('admin_id')
            if admin_id:
                return Admin.query.get(admin_id)
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        return None
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'role_display': '高级管理员' if self.role == self.ROLE_SUPER_ADMIN else '管理员',
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_by': self.created_by
        }


class AdminSession(db.Model):
    """管理员会话模型"""
    __tablename__ = 'admin_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)
    session_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_used_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def is_expired(self):
        """检查会话是否过期"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'ip_address': self.ip_address,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None
        }


def init_super_admin(app):
    """按部署者提供的凭据创建首个高级管理员。"""
    username = os.getenv("EDUAGENT_ADMIN_USERNAME", "").strip()
    email = os.getenv("EDUAGENT_ADMIN_EMAIL", "").strip()
    password = os.getenv("EDUAGENT_ADMIN_PASSWORD", "")
    if not any((username, email, password)):
        return
    if not all((username, email, password)):
        raise ValueError("Set EDUAGENT_ADMIN_USERNAME, EDUAGENT_ADMIN_EMAIL and EDUAGENT_ADMIN_PASSWORD together")
    with app.app_context():
        if Admin.query.filter_by(role=Admin.ROLE_SUPER_ADMIN).first():
            return
        admin = Admin(username=username, email=email, role=Admin.ROLE_SUPER_ADMIN, is_active=True)
        admin.set_password(password)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if not Admin.query.filter_by(username=username, role=Admin.ROLE_SUPER_ADMIN).first():
                raise
