"""
对话历史模型
Conversation History Models
"""

from datetime import datetime, timezone
from models.user import db


class Conversation(db.Model):
    """对话会话模型"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    kb_id = db.Column(db.Integer, db.ForeignKey('knowledge_bases.id'), nullable=True, index=True)
    title = db.Column(db.String(100), nullable=False, default='新对话')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 关联
    messages = db.relationship('ConversationMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan', order_by='ConversationMessage.created_at')
    user = db.relationship('User', backref=db.backref('conversations', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Conversation {self.id}: {self.title}>'
    
    def to_dict(self, include_messages=False):
        """转换为字典"""
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': self.messages.count()
        }
        if include_messages:
            result['messages'] = [msg.to_dict() for msg in self.messages.all()]
        return result


class ConversationMessage(db.Model):
    """对话消息模型"""
    __tablename__ = 'conversation_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='completed', nullable=False) # 'processing', 'completed', 'error'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    def __repr__(self):
        return f'<Message {self.id}: {self.role}>'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'model_used': self.model_used,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
