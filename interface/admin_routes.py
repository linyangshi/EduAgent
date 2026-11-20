"""
管理员路由
Admin Routes - 后台管理系统API
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from models.admin import Admin, AdminSession, db
from models.user import User
from datetime import datetime, timedelta


# 创建管理员蓝图
admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# ==================== 权限装饰器 ====================

def require_admin_auth(f):
    """管理员认证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': '缺少认证令牌'}), 401
        
        try:
            token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
        except IndexError:
            return jsonify({'error': '认证令牌格式错误'}), 401
        
        # 验证token
        admin = Admin.verify_token(token)
        if not admin:
            return jsonify({'error': '认证令牌无效或已过期'}), 401
        
        if not admin.is_active:
            return jsonify({'error': '账户已被禁用'}), 403
        
        # 将管理员信息添加到请求上下文
        request.current_admin = admin
        return f(*args, **kwargs)
    
    return decorated_function


def require_super_admin(f):
    """高级管理员权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = getattr(request, 'current_admin', None)
        if not admin:
            return jsonify({'error': '请先登录'}), 401
        
        if not admin.is_super_admin():
            return jsonify({'error': '需要高级管理员权限'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


# ==================== 认证路由 ====================

@admin_bp.route('/login', methods=['POST'])
def login():
    """管理员登录"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400
        
        # 查找管理员
        admin = Admin.query.filter_by(username=username).first()
        if not admin or not admin.check_password(password):
            return jsonify({'error': '用户名或密码错误'}), 401
        
        if not admin.is_active:
            return jsonify({'error': '账户已被禁用'}), 403
        
        # 更新最后登录时间
        admin.last_login = datetime.utcnow()
        db.session.commit()
        
        # 生成token
        token = admin.generate_token()
        
        return jsonify({
            'success': True,
            'message': '登录成功',
            'token': token,
            'admin': admin.to_dict()
        })
        
    except Exception as e:
        return jsonify({'error': f'登录失败: {str(e)}'}), 500


@admin_bp.route('/logout', methods=['POST'])
@require_admin_auth
def logout():
    """管理员登出"""
    return jsonify({
        'success': True,
        'message': '登出成功'
    })


@admin_bp.route('/check', methods=['GET'])
def check_auth():
    """检查认证状态"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'authenticated': False}), 200
        
        token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
        admin = Admin.verify_token(token)
        
        if admin and admin.is_active:
            return jsonify({
                'authenticated': True,
                'admin': admin.to_dict()
            }), 200
        else:
            return jsonify({'authenticated': False}), 200
    
    except Exception:
        return jsonify({'authenticated': False}), 200


# ==================== 用户管理路由 ====================

@admin_bp.route('/users', methods=['GET'])
@require_admin_auth
def get_users():
    """获取用户列表（分页）"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        # 构建查询
        query = User.query
        if search:
            query = query.filter(
                (User.username.like(f'%{search}%')) |
                (User.email.like(f'%{search}%')) |
                (User.full_name.like(f'%{search}%'))
            )
        
        # 分页
        pagination = query.order_by(User.is_admin.desc(), User.id.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'success': True,
            'users': [user.to_dict() for user in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({'error': f'获取用户列表失败: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@require_admin_auth
def get_user(user_id):
    """获取单个用户详情"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        return jsonify({'error': f'获取用户详情失败: {str(e)}'}), 500


@admin_bp.route('/users', methods=['POST'])
@require_admin_auth
def create_user():
    """创建新用户"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip()
        
        if not username or not email or not password:
            return jsonify({'error': '用户名、邮箱和密码不能为空'}), 400
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用户名已存在'}), 400
        
        # 检查邮箱是否已存在
        if User.query.filter_by(email=email).first():
            return jsonify({'error': '邮箱已被注册'}), 400
        
        # 创建用户
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            is_active=True
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '用户创建成功',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'创建用户失败: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_admin_auth
def update_user(user_id):
    """更新用户信息"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        # 更新用户名
        if 'username' in data:
            new_username = data['username'].strip()
            if new_username != user.username:
                if User.query.filter_by(username=new_username).first():
                    return jsonify({'error': '用户名已存在'}), 400
                user.username = new_username
        
        # 更新邮箱
        if 'email' in data:
            new_email = data['email'].strip()
            if new_email != user.email:
                if User.query.filter_by(email=new_email).first():
                    return jsonify({'error': '邮箱已被注册'}), 400
                user.email = new_email
        
        # 更新全名
        if 'full_name' in data:
            user.full_name = data['full_name'].strip()
        
        # 更新密码
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        # 更新激活状态
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
        
        # 更新管理员状态
        if 'is_admin' in data:
            user.is_admin = bool(data['is_admin'])
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '用户更新成功',
            'user': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'更新用户失败: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@require_admin_auth
def delete_user(user_id):
    """删除用户"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'用户 {username} 已删除'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'删除用户失败: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/points', methods=['POST'])
@require_admin_auth
def update_user_points(user_id):
    """管理用户积分 - 支持设置或增减积分"""
    try:
        from models.shop import add_points_to_user
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        action = data.get('action', 'set')  # set / add / subtract
        amount = data.get('amount', 0)
        reason = data.get('reason', '管理员调整')
        
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({'error': '积分数量必须为整数'}), 400
        
        old_balance = user.points_balance
        
        if action == 'set':
            if amount < 0:
                return jsonify({'error': '积分不能为负数'}), 400
            # 设置为指定值
            change = amount - old_balance
            if change != 0:
                add_points_to_user(
                    user=user,
                    points=change,
                    transaction_type='admin_adjust',
                    description=f'{reason}（设置为 {amount}）'
                )
            else:
                # 无变化
                pass
        elif action == 'add':
            if amount <= 0:
                return jsonify({'error': '增加的积分必须大于0'}), 400
            add_points_to_user(
                user=user,
                points=amount,
                transaction_type='admin_adjust',
                description=f'{reason}（增加 {amount}）'
            )
        elif action == 'subtract':
            if amount <= 0:
                return jsonify({'error': '扣减的积分必须大于0'}), 400
            if user.points_balance < amount:
                return jsonify({'error': f'用户积分不足，当前积分: {user.points_balance}'}), 400
            add_points_to_user(
                user=user,
                points=-amount,
                transaction_type='admin_adjust',
                description=f'{reason}（扣减 {amount}）'
            )
        else:
            return jsonify({'error': '无效的操作类型'}), 400
        
        # 重新获取用户以确保积分是最新的
        db.session.refresh(user)
        
        return jsonify({
            'success': True,
            'message': f'用户积分已更新',
            'old_balance': old_balance,
            'new_balance': user.points_balance,
            'user': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'更新积分失败: {str(e)}'}), 500


# ==================== 管理员管理路由（仅高级管理员）====================

@admin_bp.route('/admins', methods=['GET'])
@require_admin_auth
def get_admins():
    """获取管理员列表"""
    try:
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'admins': [admin.to_dict() for admin in admins]
        })
        
    except Exception as e:
        return jsonify({'error': f'获取管理员列表失败: {str(e)}'}), 500


@admin_bp.route('/admins', methods=['POST'])
@require_admin_auth
@require_super_admin
def create_admin():
    """创建新管理员（仅高级管理员）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        role = data.get('role', 'admin')
        
        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400
        
        if role not in [Admin.ROLE_SUPER_ADMIN, Admin.ROLE_ADMIN]:
            return jsonify({'error': '无效的角色'}), 400
        
        # 检查用户名是否已存在
        if Admin.query.filter_by(username=username).first():
            return jsonify({'error': '管理员用户名已存在'}), 400
        
        # 创建管理员
        admin = Admin(
            username=username,
            email=email,
            role=role,
            is_active=True,
            created_by=request.current_admin.id
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '管理员创建成功',
            'admin': admin.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'创建管理员失败: {str(e)}'}), 500


@admin_bp.route('/admins/<int:admin_id>', methods=['DELETE'])
@require_admin_auth
@require_super_admin
def delete_admin(admin_id):
    """删除管理员（仅高级管理员）"""
    try:
        admin = Admin.query.get(admin_id)
        if not admin:
            return jsonify({'error': '管理员不存在'}), 404
        
        # 不能删除自己
        if admin.id == request.current_admin.id:
            return jsonify({'error': '不能删除自己'}), 400
        
        # 不能删除初始高级管理员
        if admin.is_super_admin() and admin.created_by is None:
            return jsonify({'error': '不能删除初始高级管理员'}), 400
        
        username = admin.username
        db.session.delete(admin)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'管理员 {username} 已删除'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'删除管理员失败: {str(e)}'}), 500


# ==================== 统计信息 ====================

@admin_bp.route('/stats', methods=['GET'])
@require_admin_auth
def get_stats():
    """获取统计信息"""
    try:
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_admins = Admin.query.count()
        
        # Count pending feedbacks
        from models.feedback import Feedback
        pending_feedbacks = Feedback.query.filter_by(status='pending').count()
        processing_feedbacks = Feedback.query.filter_by(status='processing').count()
        resolved_feedbacks = Feedback.query.filter_by(status='resolved').count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'total_admins': total_admins,
                'pending_feedbacks': pending_feedbacks,
                'processing_feedbacks': processing_feedbacks,
                'resolved_feedbacks': resolved_feedbacks,
                # Activity stats placeholders - update when Activity model is implemented
                'active_activities': 0,
                'ended_activities': 0,
                'current_activity_name': '暂无活动'
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500

# ==================== 反馈管理路由（仅高级管理员）====================

@admin_bp.route('/feedbacks', methods=['GET'])
@require_admin_auth
@require_super_admin
def get_feedbacks():
    """获取所有反馈列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status', 'all')
        
        from models.feedback import Feedback
        
        query = Feedback.query
        
        if status != 'all':
            query = query.filter_by(status=status)
            
        pagination = query.order_by(Feedback.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # 获取关联用户信息
        feedbacks_data = []
        for fb in pagination.items:
            data = fb.to_dict()
            user = User.query.get(fb.user_id)
            if user:
                data['username'] = user.username
                data['user_email'] = user.email
            else:
                data['username'] = 'Unknown'
                data['user_email'] = ''
            feedbacks_data.append(data)
            
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({'error': f'获取反馈列表失败: {str(e)}'}), 500


@admin_bp.route('/feedbacks/<int:feedback_id>/status', methods=['PUT'])
@require_admin_auth
@require_super_admin
def update_feedback_status(feedback_id):
    """更新反馈状态"""
    try:
        from models.feedback import Feedback
        
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return jsonify({'error': '反馈未找到'}), 404
            
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['pending', 'processing', 'resolved']:
            return jsonify({'error': '无效的状态'}), 400
            
        feedback.status = status
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '状态更新成功'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'更新状态失败: {str(e)}'}), 500


@admin_bp.route('/stats/chart', methods=['GET'])
@require_admin_auth
def get_stats_chart():
    """获取统计图表数据 - 优化版本，使用单次聚合查询"""
    try:
        chart_type = request.args.get('type', 'interactions')
        days = request.args.get('days', 7, type=int)
        
        from models.conversation import ConversationMessage
        from models.user import UserSession
        from models.shop import RechargeOrder
        from sqlalchemy import func, cast, Date
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days-1)
        start_date = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
        
        # Build date labels for the range
        labels = []
        date_map = {}  # For quick lookup
        current = start_date
        while current <= end_date:
            day_str = current.strftime('%m-%d')
            date_key = current.strftime('%Y-%m-%d')
            labels.append(day_str)
            date_map[date_key] = 0  # Initialize with 0
            current += timedelta(days=1)
        
        # Single aggregated query based on chart type
        if chart_type == 'interactions':
            # Query llm_calls table for ALL AI interactions (not just chat)
            from sqlalchemy import text
            
            # SQLite Timezone Adjustment: Add 8 hours for Beijing Time
            results = db.session.execute(text("""
                SELECT DATE(created_at, '+8 hours') as day, COUNT(*) as cnt
                FROM llm_calls
                WHERE DATE(created_at, '+8 hours') >= :start_date_str
                GROUP BY DATE(created_at, '+8 hours')
                ORDER BY day
            """), {'start_date_str': start_date.strftime('%Y-%m-%d')}).fetchall()
            
            for row in results:
                date_key = str(row[0])  # row[0] is the date string
                if date_key in date_map:
                    date_map[date_key] = row[1]
                    
        elif chart_type == 'active_users':
            # Group by date, count distinct users
            results = db.session.query(
                func.date(UserSession.last_used_at).label('day'),
                func.count(func.distinct(UserSession.user_id)).label('cnt')
            ).filter(
                UserSession.last_used_at >= start_date
            ).group_by(
                func.date(UserSession.last_used_at)
            ).all()
            
            for row in results:
                date_key = str(row.day)
                if date_key in date_map:
                    date_map[date_key] = row.cnt
                    
        elif chart_type == 'revenue':
            # Group by date, sum revenue
            results = db.session.query(
                func.date(RechargeOrder.paid_at).label('day'),
                func.sum(RechargeOrder.amount_rmb).label('total')
            ).filter(
                RechargeOrder.status == 'paid',
                RechargeOrder.paid_at >= start_date
            ).group_by(
                func.date(RechargeOrder.paid_at)
            ).all()
            
            for row in results:
                date_key = str(row.day)
                if date_key in date_map:
                    # amount_rmb is already in yuan (not cents)
                    date_map[date_key] = float(row.total or 0)
        
        # Build data array in order
        data = []
        current = start_date
        while current <= end_date:
            date_key = current.strftime('%Y-%m-%d')
            data.append(date_map.get(date_key, 0))
            current += timedelta(days=1)
            
        return jsonify({
            'success': True,
            'labels': labels,
            'data': data,
            'type': chart_type
        })
        
    except Exception as e:
        return jsonify({'error': f'获取图表数据失败: {str(e)}'}), 500
