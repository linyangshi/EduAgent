from flask import Blueprint, request, jsonify, render_template
from models.feedback import Feedback
from models.user import db
from interface.auth_middleware import require_auth
from flask_login import current_user

feedback_bp = Blueprint('feedback', __name__)

@feedback_bp.route('/feedback')
@require_auth
def feedback_page():
    """Render the feedback page - Auto detect mobile"""
    ua = request.headers.get('User-Agent', '').lower()
    mobile_keywords = ['mobile', 'iphone', 'android', 'mobi']
    is_mobile = any(k in ua for k in mobile_keywords)
    
    template = 'mobile_feedback.html' if is_mobile else 'feedback.html'
    return render_template(template, current_user=current_user)

@feedback_bp.route('/api/feedback', methods=['POST'])
@require_auth
def submit_feedback():
    """Submit feedback API"""
    try:
        data = request.get_json()
        
        # Validate
        if not data.get('content'):
            return jsonify({'error': '反馈内容不能为空'}), 400
            
        feedback_type = data.get('type', 'other')
        content = data.get('content')
        contact = data.get('contact')
        
        # Create feedback
        feedback = Feedback(
            user_id=current_user.id,
            type=feedback_type,
            content=content,
            contact=contact
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '感谢您的反馈！'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@feedback_bp.route('/api/feedback/history', methods=['GET'])
@require_auth
def get_feedback_history():
    """Get current user's feedback history"""
    try:
        feedbacks = Feedback.query.filter_by(user_id=current_user.id)\
            .order_by(Feedback.created_at.desc())\
            .limit(20).all()
            
        return jsonify({
            'success': True,
            'feedbacks': [f.to_dict() for f in feedbacks]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
