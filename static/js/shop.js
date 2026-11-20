/**
 * 商城页面逻辑
 * Shop Page Logic - Points Recharge and Management
 */

// 全局变量
let selectedOption = null;
let selectedPaymentMethod = 'alipay';

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function () {
    // 检查是否在商城页面
    const shopSection = document.getElementById('shop-section');
    if (!shopSection) return;

    // 加载商城数据
    loadPointsBalance();
    loadRechargeOptions();

    // 绑定事件
    bindShopEvents();
});

/**
 * 加载积分余额
 */
async function loadPointsBalance() {
    try {
        const response = await fetch('/api/shop/points-balance', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const data = await response.json();
        if (data.success) {
            document.getElementById('currentPoints').textContent = data.points_balance;
        }
    } catch (error) {
        console.error('加载积分余额失败:', error);
    }
}

/**
 * 加载充值档位
 */
async function loadRechargeOptions() {
    try {
        const response = await fetch('/api/shop/recharge-options');
        const data = await response.json();

        if (data.success) {
            renderRechargeOptions(data.options);
        }
    } catch (error) {
        console.error('加载充值档位失败:', error);
    }
}

/**
 * 渲染充值档位
 */
function renderRechargeOptions(options) {
    const container = document.getElementById('rechargeOptions');
    container.innerHTML = '';

    options.forEach(option => {
        const btn = document.createElement('button');
        btn.className = 'recharge-option-btn';
        btn.dataset.optionId = option.id;
        btn.dataset.amount = option.amount_rmb;
        btn.dataset.points = option.points;

        btn.innerHTML = `
            ${option.popular ? '<span class="popular-tag">推荐</span>' : ''}
            <div class="recharge-amount">¥${option.amount_rmb}</div>
            <div class="recharge-points">${option.points} 积分</div>
        `;

        btn.addEventListener('click', () => selectRechargeOption(option, btn));
        container.appendChild(btn);
    });
}

/**
 * 选择充值档位
 */
function selectRechargeOption(option, btn) {
    // 移除之前的选中状态
    document.querySelectorAll('.recharge-option-btn').forEach(b => b.classList.remove('active'));

    // 设置当前选中
    btn.classList.add('active');
    selectedOption = option;

    // 更新充值按钮
    const rechargeBtn = document.getElementById('rechargeBtn');
    const rechargeBtnText = document.getElementById('rechargeBtnText');
    rechargeBtn.disabled = false;
    rechargeBtnText.textContent = `充值 ¥${option.amount_rmb} (${option.points} 积分)`;
}

/**
 * 绑定商城页面事件
 */
function bindShopEvents() {
    // 支付方式选择
    document.querySelectorAll('.payment-method-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.payment-method-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            selectedPaymentMethod = this.dataset.method;
        });
    });

    // 充值按钮
    const rechargeBtn = document.getElementById('rechargeBtn');
    if (rechargeBtn) {
        rechargeBtn.addEventListener('click', handleRecharge);
    }

    // 标签切换
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const tab = this.dataset.tab;
            switchTab(tab);
        });
    });

    // 监听section切换，加载对应数据
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.target.id === 'shop-section' && mutation.target.classList.contains('active')) {
                loadShopData();
            }
        });
    });

    const shopSection = document.getElementById('shop-section');
    if (shopSection) {
        observer.observe(shopSection, { attributes: true, attributeFilter: ['class'] });
    }
}

/**
 * 处理充值
 */
async function handleRecharge() {
    alert('当前未开放充值');
    return;
}

/**
 * 显示支付对话框
 */
function showPaymentDialog(order, payParams) {
    // 由于支付接口未对接，显示模拟支付选项
    const message = `订单创建成功！\n\n订单号: ${order.order_no}\n金额: ¥${order.amount_rmb}\n积分: ${order.points}\n\n${payParams.message}\n\n是否使用模拟支付进行测试？`;

    if (confirm(message)) {
        simulatePayment(order.order_no);
    } else {
        // 刷新订单列表
        loadOrders();
    }
}

/**
 * 模拟支付
 */
async function simulatePayment(orderNo) {
    try {
        const response = await fetch(`/api/shop/simulate-payment/${orderNo}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const data = await response.json();

        if (data.success) {
            // 显示成功消息
            const successMsg = document.getElementById('recharge-success');
            successMsg.style.display = 'block';
            successMsg.textContent = `充值成功！当前积分: ${data.new_balance}`;

            setTimeout(() => {
                successMsg.style.display = 'none';
            }, 3000);

            // 刷新数据
            loadPointsBalance();
            loadOrders();
            loadTransactions();

            // 取消选中
            document.querySelectorAll('.recharge-option-btn').forEach(b => b.classList.remove('active'));
            selectedOption = null;
            const rechargeBtn = document.getElementById('rechargeBtn');
            rechargeBtn.disabled = true;
            document.getElementById('rechargeBtnText').textContent = '请选择充值档位';
        } else {
            alert(data.error || '支付失败');
        }
    } catch (error) {
        console.error('模拟支付失败:', error);
        alert('支付失败，请稍后重试');
    }
}

/**
 * 切换标签
 */
function switchTab(tab) {
    // 更新按钮状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.dataset.tab === tab) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // 更新内容显示
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    if (tab === 'orders') {
        document.getElementById('ordersTab').classList.add('active');
        loadOrders();
    } else if (tab === 'transactions') {
        document.getElementById('transactionsTab').classList.add('active');
        loadTransactions();
    }
}

/**
 * 加载商城数据（当切换到商城页面时）
 */
function loadShopData() {
    loadPointsBalance();
    loadOrders();
}

/**
 * 加载充值订单
 */
async function loadOrders() {
    try {
        const response = await fetch('/api/shop/orders?per_page=10', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const data = await response.json();

        if (data.success) {
            renderOrders(data.orders);
        }
    } catch (error) {
        console.error('加载订单失败:', error);
    }
}

/**
 * 渲染充值订单
 */
function renderOrders(orders) {
    const container = document.getElementById('ordersList');

    if (!orders || orders.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 40px 0;">暂无充值订单</p>';
        return;
    }

    container.innerHTML = orders.map(order => {
        const statusMap = {
            'pending': '待支付',
            'paid': '已支付',
            'failed': '支付失败',
            'cancelled': '已取消',
            'expired': '已过期'
        };

        const payMethodMap = {
            'alipay': '支付宝',
            'wechat': '微信支付'
        };

        // 待支付订单显示操作按钮
        const actionButtons = order.status === 'pending' ? `
            <div class="order-actions">
                <button class="action-btn pay-btn" onclick="continuePayment('${order.order_no}')">继续支付</button>
                <button class="action-btn cancel-btn" onclick="cancelOrder('${order.order_no}')">取消订单</button>
            </div>
        ` : '';

        return `
            <div class="record-item">
                <div class="record-info">
                    <div class="record-title">充值 ¥${order.amount_rmb}</div>
                    <div class="record-meta">
                        <span>订单号: ${order.order_no}</span>
                        <span>${payMethodMap[order.payment_method] || '未知'}</span>
                        <span>${formatDate(order.created_at)}</span>
                    </div>
                    ${actionButtons}
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div class="record-amount positive">+${order.points} 积分</div>
                    <span class="status-badge status-${order.status}">${statusMap[order.status]}</span>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * 继续支付
 */
async function continuePayment(orderNo) {
    if (confirm('确定要继续支付该订单吗？')) {
        await simulatePayment(orderNo);
    }
}

/**
 * 取消订单
 */
async function cancelOrder(orderNo) {
    if (!confirm('确定要取消该订单吗？取消后无法恢复。')) {
        return;
    }

    try {
        const response = await fetch(`/api/shop/cancel-order/${orderNo}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const data = await response.json();

        if (data.success) {
            alert('订单已取消');
            loadOrders();
        } else {
            alert(data.error || '取消订单失败');
        }
    } catch (error) {
        console.error('取消订单失败:', error);
        alert('取消订单失败，请稍后重试');
    }
}

/**
 * 加载积分流水
 */
async function loadTransactions() {
    try {
        const response = await fetch('/api/shop/transactions?per_page=20', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });

        const data = await response.json();

        if (data.success) {
            renderTransactions(data.transactions);
        }
    } catch (error) {
        console.error('加载积分流水失败:', error);
    }
}

/**
 * 渲染积分流水
 */
function renderTransactions(transactions) {
    const container = document.getElementById('transactionsList');

    if (!transactions || transactions.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 40px 0;">暂无积分流水</p>';
        return;
    }

    container.innerHTML = transactions.map(tx => {
        const typeMap = {
            'recharge': '充值',
            'consume': '消费',
            'refund': '退款',
            'gift': '赠送',
            'admin_adjust': '调整'
        };

        const isPositive = tx.change_amount > 0;

        return `
            <div class="record-item">
                <div class="record-info">
                    <div class="record-title">${typeMap[tx.transaction_type] || tx.transaction_type}</div>
                    <div class="record-meta">
                        <span>${tx.description || ''}</span>
                        <span>${formatDate(tx.created_at)}</span>
                    </div>
                </div>
                <div style="text-align: right;">
                    <div class="record-amount ${isPositive ? 'positive' : 'negative'}">
                        ${isPositive ? '+' : ''}${tx.change_amount}
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">
                        余额: ${tx.balance_after}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * 格式化日期
 */
function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const formatter = new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Shanghai'
    });
    return formatter.format(date);
}
