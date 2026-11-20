"""
商城API路由
Shop API Routes - Recharge and Points Management
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from datetime import datetime, timezone, timedelta

from models.user import db, User
from models.shop import (
    RechargeOrder, PointsTransaction, RECHARGE_OPTIONS,
    generate_order_no, add_points_to_user
)
from interface.auth_middleware import require_auth

shop_bp = Blueprint('shop', __name__, url_prefix='/api/shop')


@shop_bp.route('/recharge-options', methods=['GET'])
def get_recharge_options():
    """获取充值档位列表"""
    return jsonify({
        'success': True,
        'options': RECHARGE_OPTIONS,
        'exchange_rate': '1 RMB = 10 积分'
    })


@shop_bp.route('/points-balance', methods=['GET'])
@require_auth
def get_points_balance():
    """获取当前用户积分余额"""
    user = User.query.get(current_user.id)
    return jsonify({
        'success': True,
        'points_balance': user.points_balance,
        'username': user.username
    })


@shop_bp.route('/create-order', methods=['POST'])
@require_auth
def create_order():
    """创建充值订单"""
    try:
        data = request.get_json()
        option_id = data.get('option_id')
        payment_method = data.get('payment_method')  # alipay / wechat
        
        if not option_id:
            return jsonify({'success': False, 'error': '请选择充值档位'}), 400
        
        if payment_method not in ['alipay', 'wechat']:
            return jsonify({'success': False, 'error': '请选择支付方式'}), 400
        
        # 查找充值档位
        option = next((o for o in RECHARGE_OPTIONS if o['id'] == option_id), None)
        if not option:
            return jsonify({'success': False, 'error': '无效的充值档位'}), 400
        
        # 创建订单
        order = RechargeOrder(
            user_id=current_user.id,
            order_no=generate_order_no(),
            amount_rmb=option['amount_rmb'],
            points=option['points'],
            payment_method=payment_method,
            status='pending',
            expired_at=datetime.now(timezone.utc) + timedelta(minutes=30)  # 30分钟后过期
        )
        
        db.session.add(order)
        db.session.commit()
        
        # 生成支付参数（预留接口，暂时返回模拟数据）
        pay_params = generate_pay_params(order, payment_method)
        
        return jsonify({
            'success': True,
            'order': order.to_dict(),
            'pay_params': pay_params,
            'message': '订单创建成功，请完成支付'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'创建订单失败: {str(e)}'}), 500


@shop_bp.route('/order-status/<order_no>', methods=['GET'])
@require_auth
def get_order_status(order_no):
    """查询订单状态"""
    order = RechargeOrder.query.filter_by(
        order_no=order_no,
        user_id=current_user.id
    ).first()
    
    if not order:
        return jsonify({'success': False, 'error': '订单不存在'}), 404
    
    # 检查是否过期
    if order.status == 'pending' and order.is_expired():
        order.status = 'expired'
        db.session.commit()
    
    return jsonify({
        'success': True,
        'order': order.to_dict()
    })


@shop_bp.route('/orders', methods=['GET'])
@require_auth
def get_orders():
    """获取用户的充值订单列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    orders = RechargeOrder.query.filter_by(
        user_id=current_user.id
    ).order_by(RechargeOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'success': True,
        'orders': [o.to_dict() for o in orders.items],
        'total': orders.total,
        'pages': orders.pages,
        'current_page': page
    })


@shop_bp.route('/transactions', methods=['GET'])
@require_auth
def get_transactions():
    """获取积分流水记录"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    transactions = PointsTransaction.query.filter_by(
        user_id=current_user.id
    ).order_by(PointsTransaction.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'success': True,
        'transactions': [t.to_dict() for t in transactions.items],
        'total': transactions.total,
        'pages': transactions.pages,
        'current_page': page
    })


@shop_bp.route('/cancel-order/<order_no>', methods=['POST'])
@require_auth
def cancel_order(order_no):
    """取消订单"""
    order = RechargeOrder.query.filter_by(
        order_no=order_no,
        user_id=current_user.id
    ).first()
    
    if not order:
        return jsonify({'success': False, 'error': '订单不存在'}), 404
    
    if order.status != 'pending':
        return jsonify({'success': False, 'error': f'订单状态为【{order.status}】，无法取消'}), 400
    
    order.status = 'cancelled'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '订单已取消',
        'order': order.to_dict()
    })


# ===== 支付回调接口（预留） =====

@shop_bp.route('/payment/alipay/notify', methods=['POST'])
def alipay_notify():
    """
    支付宝异步回调通知（预留接口）
    
    实际对接时需要：
    1. 验证签名
    2. 验证订单金额
    3. 更新订单状态
    4. 增加用户积分
    """
    # TODO: 实现支付宝回调验证逻辑
    return 'success'


@shop_bp.route('/payment/wechat/notify', methods=['POST'])
def wechat_notify():
    """
    微信支付异步回调通知（预留接口）
    
    实际对接时需要：
    1. 验证签名
    2. 验证订单金额
    3. 更新订单状态
    4. 增加用户积分
    """
    # TODO: 实现微信支付回调验证逻辑
    return '<xml><return_code><![CDATA[SUCCESS]]></return_code></xml>'


@shop_bp.route('/simulate-payment/<order_no>', methods=['POST'])
@require_auth
def simulate_payment(order_no):
    """
    模拟支付成功（仅用于测试）
    仅在 Flask TESTING 模式可用
    """
    if not current_app.testing:
        return jsonify({'success': False, 'error': '模拟支付仅可用于测试'}), 403
    order = RechargeOrder.query.filter_by(
        order_no=order_no,
        user_id=current_user.id
    ).first()
    
    if not order:
        return jsonify({'success': False, 'error': '订单不存在'}), 404
    
    if order.status != 'pending':
        return jsonify({'success': False, 'error': f'订单状态异常: {order.status}'}), 400
    
    if order.is_expired():
        order.status = 'expired'
        db.session.commit()
        return jsonify({'success': False, 'error': '订单已过期'}), 400
    
    # 标记订单为已支付
    order.mark_as_paid(trade_no=f'SIMULATE_{order.order_no}')
    
    # 增加用户积分
    user = User.query.get(current_user.id)
    add_points_to_user(
        user=user,
        points=order.points,
        transaction_type='recharge',
        description=f'充值 {order.amount_rmb} 元，获得 {order.points} 积分',
        related_order=order
    )
    
    return jsonify({
        'success': True,
        'message': '支付成功',
        'order': order.to_dict(),
        'new_balance': user.points_balance
    })


# ===== 辅助函数 =====

def generate_pay_params(order, payment_method):
    """
    生成支付参数（预留接口）
    
    实际对接时需要：
    1. 调用支付宝/微信支付API
    2. 返回支付链接或支付参数
    """
    if payment_method == 'alipay':
        return {
            'method': 'alipay',
            'pay_url': None,  # 实际对接时返回支付宝支付链接
            'qr_code': None,  # 或返回二维码内容
            'message': '支付宝支付接口暂未对接，请使用模拟支付测试'
        }
    elif payment_method == 'wechat':
        return {
            'method': 'wechat',
            'pay_url': None,
            'qr_code': None,
            'message': '微信支付接口暂未对接，请使用模拟支付测试'
        }
    return {}
