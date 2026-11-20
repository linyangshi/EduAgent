"""Utility for logging LLM API calls to database"""

from datetime import datetime


def log_llm_call(
    user_id=None,
    feature='unknown',
    model_name=None,
    input_tokens=0,
    output_tokens=0,
    api_provider='qwen',
    request_id=None
):
    """
    统一的LLM调用日志记录函数 (使用直接SQLite连接，最可靠)
    
    Args:
        user_id: 用户ID (可选，某些系统调用可能没有用户)
        feature: 功能名称 ('chat', 'v5_generation', 'ai_editor', 'blackboard', etc)
        model_name: 模型名称 ('qwen-plus', 'qwen-turbo', 'qwen-vl-plus', etc)
        input_tokens: 输入token数
        output_tokens: 输出token数
        api_provider: API提供商 ('qwen', 'openai', 'fireworks', etc)
        request_id: 关联的请求ID (可选)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import sqlite3
        import os
        
        # 获取数据库路径
        db_path = os.path.join(os.path.dirname(__file__), '..', 'eduagent.db')
        db_path = os.path.abspath(db_path)
        
        # Ensure values are not None
        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        total_tokens = input_tokens + output_tokens
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO llm_calls 
            (user_id, feature, model_name, input_tokens, output_tokens, total_tokens, api_provider, request_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, feature, model_name, input_tokens, output_tokens, total_tokens, api_provider, request_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        # Don't let logging failure break the application, but print it
        print(f"⚠️  LLM Logging Error: {e}")
        return False


def log_llm_call_async(
    user_id=None,
    feature='unknown',
    model_name=None,
    input_tokens=0,
    output_tokens=0,
    api_provider='qwen',
    request_id=None
):
    """
    异步版本的LLM调用日志记录（不阻塞主流程）
    适用于对性能敏感的场景
    """
    import threading
    
    def _log_in_thread():
        log_llm_call(
            user_id=user_id,
            feature=feature,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            api_provider=api_provider,
            request_id=request_id
        )
    
    thread = threading.Thread(target=_log_in_thread, daemon=True)
    thread.start()


def get_user_llm_stats(user_id, days=30):
    """
    获取用户的LLM使用统计
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    try:
        from models.llm_call import LLMCall
        from models.user import db
    except ImportError:
        return {'total_calls': 0, 'total_tokens': 0, 'features': {}}
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # 总调用次数
    try:
        total_calls = LLMCall.query.filter(
            LLMCall.user_id == user_id,
            LLMCall.created_at >= start_date
        ).count()
        
        # 按功能分组统计
        feature_stats = db.session.query(
            LLMCall.feature,
            func.count(LLMCall.id).label('count'),
            func.sum(LLMCall.total_tokens).label('tokens')
        ).filter(
            LLMCall.user_id == user_id,
            LLMCall.created_at >= start_date
        ).group_by(LLMCall.feature).all()
        
        feature_breakdown = {
            row.feature: {
                'count': row.count,
                'tokens': row.tokens or 0
            }
            for row in feature_stats
        }
        
        # 总token数
        total_tokens = db.session.query(
            func.sum(LLMCall.total_tokens)
        ).filter(
            LLMCall.user_id == user_id,
            LLMCall.created_at >= start_date
        ).scalar() or 0
        
        return {
            'total_calls': total_calls,
            'total_tokens': total_tokens,
            'features': feature_breakdown,
            'period_days': days
        }
    except Exception as e:
        print(f"⚠️  Error fetching LLM stats: {e}")
        return {'total_calls': 0, 'total_tokens': 0, 'features': {}}
