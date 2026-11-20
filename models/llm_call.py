"""LLM Call tracking models"""

from datetime import datetime
from models.user import db

class LLMCall(db.Model):
    """LLM调用记录模型"""
    __tablename__ = 'llm_calls'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    feature = db.Column(db.String(50), nullable=False) # 'chat', 'kb', 'v5_generation', 'ai_editor', 'blackboard'
    model_name = db.Column(db.String(50), nullable=True)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    api_provider = db.Column(db.String(50), default='qwen')
    request_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'feature': self.feature,
            'model_name': self.model_name,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'api_provider': self.api_provider,
            'created_at': self.created_at.isoformat()
        }

def get_llm_call_stats(start_date, chart_type='total'):
    """
    获取LLM调用统计 (保持向前兼容)
    """
    from sqlalchemy import text
    
    if chart_type == 'total':
        query = text("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM llm_calls
            WHERE created_at >= :start_date
            GROUP BY DATE(created_at)
            ORDER BY day
        """)
    else:
        query = text("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM llm_calls
            WHERE created_at >= :start_date AND feature = :feature
            GROUP BY DATE(created_at)
            ORDER BY day
        """)
    
    result = db.session.execute(query, {'start_date': start_date, 'feature': chart_type if chart_type != 'total' else None})
    return [(row[0], row[1]) for row in result]
