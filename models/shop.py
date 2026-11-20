"""
商城模型
Shop Models - RechargeOrder and PointsTransaction
"""

from datetime import datetime, timezone, timedelta
from models.user import db
import uuid


# 充值档位配置
RECHARGE_OPTIONS = [
    {'id': 1, 'amount_rmb': 1, 'points': 10, 'label': '1元', 'popular': False},
    {'id': 2, 'amount_rmb': 6, 'points': 60, 'label': '6元', 'popular': False},
    {'id': 3, 'amount_rmb': 30, 'points': 300, 'label': '30元', 'popular': True},
    {'id': 4, 'amount_rmb': 68, 'points': 680, 'label': '68元', 'popular': False},
    {'id': 5, 'amount_rmb': 198, 'points': 1980, 'label': '198元', 'popular': True},
    {'id': 6, 'amount_rmb': 328, 'points': 3280, 'label': '328元', 'popular': False},
    {'id': 7, 'amount_rmb': 648, 'points': 6480, 'label': '648元', 'popular': False},
]


def generate_order_no():
    """生成订单号: 时间戳 + 随机字符"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = uuid.uuid4().hex[:8].upper()
    return f"RC{timestamp}{random_suffix}"


class RechargeOrder(db.Model):
    """充值订单模型"""
    __tablename__ = 'recharge_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    order_no = db.Column(db.String(50), unique=True, nullable=False, index=True)
    amount_rmb = db.Column(db.Integer, nullable=False)  # 充值金额（单位：分）
    points = db.Column(db.Integer, nullable=False)  # 对应积分数
    payment_method = db.Column(db.String(20), nullable=True)  # alipay / wechat / None
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending / paid / failed / cancelled / expired
    
    # 支付相关
    trade_no = db.Column(db.String(100), nullable=True)  # 第三方支付平台交易号
    pay_url = db.Column(db.String(500), nullable=True)  # 支付链接（暂存）
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    expired_at = db.Column(db.DateTime, nullable=True)  # 订单过期时间
    
    # 关联
    user = db.relationship('User', backref=db.backref('recharge_orders', lazy='dynamic', cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<RechargeOrder {self.order_no}>'
    
    def is_expired(self):
        """检查订单是否已过期"""
        if self.expired_at:
            # 确保两个datetime都是timezone-aware的
            now = datetime.now(timezone.utc)
            expired = self.expired_at
            if expired.tzinfo is None:
                # 如果expired_at是naive的，假设它是UTC
                expired = expired.replace(tzinfo=timezone.utc)
            return now > expired
        return False
    
    def mark_as_paid(self, trade_no=None):
        """标记订单为已支付"""
        self.status = 'paid'
        self.paid_at = datetime.now(timezone.utc)
        if trade_no:
            self.trade_no = trade_no
        db.session.commit()
    
    def to_dict(self):
        """转换为字典"""
        beijing_tz = timezone(timedelta(hours=8))
        
        def to_beijing(dt):
            if dt is None:
                return None
            # If naive, assume it's UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(beijing_tz).strftime('%Y/%m/%d %H:%M')
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'order_no': self.order_no,
            'amount_rmb': self.amount_rmb,
            'points': self.points,
            'payment_method': self.payment_method,
            'status': self.status,
            'trade_no': self.trade_no,
            'created_at': to_beijing(self.created_at),
            'paid_at': to_beijing(self.paid_at),
            'expired_at': to_beijing(self.expired_at),
        }


class PointsTransaction(db.Model):
    """积分流水模型"""
    __tablename__ = 'points_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    change_amount = db.Column(db.Integer, nullable=False)  # 变动积分（正为增加，负为扣减）
    balance_after = db.Column(db.Integer, nullable=False)  # 变动后余额
    transaction_type = db.Column(db.String(20), nullable=False)  # recharge / consume / refund / gift / admin_adjust
    description = db.Column(db.String(200), nullable=True)  # 描述
    related_order_id = db.Column(db.Integer, db.ForeignKey('recharge_orders.id'), nullable=True)  # 关联订单ID
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 关联
    user = db.relationship('User', backref=db.backref('points_transactions', lazy='dynamic', cascade='all, delete-orphan'))
    related_order = db.relationship('RechargeOrder', backref=db.backref('transactions', lazy='dynamic'))
    
    def __repr__(self):
        return f'<PointsTransaction {self.id}: {self.change_amount}>'
    
    def to_dict(self):
        """转换为字典"""
        beijing_tz = timezone(timedelta(hours=8))
        
        def to_beijing(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(beijing_tz).strftime('%Y/%m/%d %H:%M')
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'change_amount': self.change_amount,
            'balance_after': self.balance_after,
            'transaction_type': self.transaction_type,
            'description': self.description,
            'related_order_id': self.related_order_id,
            'created_at': to_beijing(self.created_at),
        }


def add_points_to_user(user, points, transaction_type, description, related_order=None):
    """
    给用户增加积分并记录流水
    
    Args:
        user: User对象
        points: 积分数量（正数增加，负数扣减）
        transaction_type: 交易类型
        description: 描述
        related_order: 关联的充值订单（可选）
    
    Returns:
        PointsTransaction: 创建的流水记录
    """
    # 更新用户积分余额
    user.points_balance += points
    
    # 创建流水记录
    transaction = PointsTransaction(
        user_id=user.id,
        change_amount=points,
        balance_after=user.points_balance,
        transaction_type=transaction_type,
        description=description,
        related_order_id=related_order.id if related_order else None
    )
    
    db.session.add(transaction)
    db.session.commit()
    
    return transaction
