// Admin Dashboard JavaScript
// 管理后台功能脚本

const API_BASE = '/api/admin';
let currentAdmin = null;
let currentPage = 1;
const perPage = 20;

// 管理员表单提交
function setupEventListeners() {
    // 用户表单提交
    const userForm = document.getElementById('userForm');
    if (userForm) {
        userForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('User form submitted');

            const userId = document.getElementById('userId').value;
            const username = document.getElementById('userUsername').value.trim();
            const email = document.getElementById('userEmail').value.trim();
            const fullName = document.getElementById('userFullName').value.trim();
            const password = document.getElementById('userPassword').value;
            const isActive = document.getElementById('userActive').value === 'true';
            const isAdmin = document.getElementById('userRole').value === 'true';

            const data = { username, email, full_name: fullName, is_active: isActive, is_admin: isAdmin };
            if (password) {
                data.password = password;
            }

            const token = localStorage.getItem('admin_token');
            const url = userId ? `${API_BASE}/users/${userId}` : `${API_BASE}/users`;
            const method = userId ? 'PUT' : 'POST';

            try {
                const response = await fetch(url, {
                    method: method,
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();
                if (result.success) {
                    alert(result.message);
                    closeUserModal();
                    loadUsers(currentPage);
                    loadStats();
                } else {
                    document.getElementById('userFormError').textContent = result.error || '操作失败';
                }
            } catch (error) {
                console.error('用户操作失败:', error);
                document.getElementById('userFormError').textContent = '网络错误，请重试';
            }
        });
    }

    // 管理员表单提交
    const adminForm = document.getElementById('adminForm');
    if (adminForm) {
        adminForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('Admin form submitted');

            const usernameInput = document.getElementById('adminUsername');
            const username = usernameInput ? usernameInput.value : '';
            const emailInput = document.getElementById('adminEmail');
            const email = emailInput ? emailInput.value : '';
            const password = document.getElementById('adminPassword').value;
            const role = document.getElementById('adminRole').value;


            const data = { username, password, role };
            if (email) {
                data.email = email;
            }

            const token = localStorage.getItem('admin_token');

            try {
                const response = await fetch(`${API_BASE}/admins`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (result.success) {
                    alert(result.message);
                    closeAdminModal();
                    loadAdmins();
                    loadStats();
                } else {
                    document.getElementById('adminFormError').textContent = result.error || '创建失败';
                }
            } catch (error) {
                console.error('创建管理员失败:', error);
                document.getElementById('adminFormError').textContent = '网络错误，请重试: ' + error.message;
            }
        });
    }

    // 积分表单提交
    const pointsForm = document.getElementById('pointsForm');
    if (pointsForm) {
        pointsForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const userId = document.getElementById('pointsUserId').value;
            const action = document.getElementById('pointsAction').value;
            const amount = document.getElementById('pointsAmount').value;
            const reason = document.getElementById('pointsReason').value.trim() || '管理员调整';

            if (!amount || parseInt(amount) < 0) {
                document.getElementById('pointsFormError').textContent = '请输入有效的积分数量';
                return;
            }

            const token = localStorage.getItem('admin_token');

            try {
                const response = await fetch(`${API_BASE}/users/${userId}/points`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        action: action,
                        amount: parseInt(amount),
                        reason: reason
                    })
                });

                const result = await response.json();
                if (result.success) {
                    alert(`积分更新成功！\n原积分: ${result.old_balance}\n现积分: ${result.new_balance}`);
                    closePointsModal();
                    loadUsers(currentPage);
                } else {
                    document.getElementById('pointsFormError').textContent = result.error || '操作失败';
                }
            } catch (error) {
                console.error('更新积分失败:', error);
                document.getElementById('pointsFormError').textContent = '网络错误，请重试';
            }
        });
    }
}

// 切换导航
function switchNav(sectionId) {
    // Update Nav Items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('onclick').includes(`'${sectionId}'`)) {
            item.classList.add('active');
        }
    });

    // Update Sections
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });
    document.getElementById(`section-${sectionId}`).classList.add('active');

    // Update Title
    const titles = {
        'home': '首页',
        'todo': '待办事项',
        'activity': '活动管理',
        'users': '用户管理',
        'admins': '管理员管理'
    };
    document.getElementById('pageTitle').textContent = titles[sectionId] || '管理后台';

    // Load Data
    if (sectionId === 'users') {
        loadUsers();
    } else if (sectionId === 'admins') {
        loadAdmins();
    } else if (sectionId === 'home') {
        loadStats();
    } else if (sectionId === 'todo') {
        loadFeedbacks();
    }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', async () => {
    // 初始化事件监听
    setupEventListeners();

    await checkAuth();

    // 并行加载所有初始数据（优化加载速度）
    await Promise.all([
        loadStats(),
        switchChartType('interactions'),
        loadRevenueChart()
    ]);

    // 如果是高级管理员，显示管理员管理菜单和待办反馈
    if (currentAdmin && currentAdmin.role === 'super_admin') {
        document.getElementById('nav-admins').style.display = 'flex';
        document.getElementById('nav-todo').style.display = 'flex';
    } else {
        document.getElementById('nav-admins').style.display = 'none';
        document.getElementById('nav-todo').style.display = 'none';
    }

    // 默认显示首页，或者根据 URL hash 显示
    switchNav('home');

    // Auto Refresh every 5 minutes (300,000 ms)
    setInterval(() => {
        console.log('Auto refreshing stats...');
        loadStats();
        // Refresh chart if on home tab
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav && activeNav.getAttribute('onclick').includes("'home'")) {
            // Get current chart type? For now just refresh default or current if we tracked it
            // Simple approach: reload current chart
            const chartTitle = document.getElementById('chartTitle').textContent;
            let type = 'interactions';
            if (chartTitle.includes('活跃用户')) type = 'active_users';
            else if (chartTitle.includes('营收')) type = 'revenue';
            switchChartType(type);
        }
    }, 300000); // 5 minutes
});

// 检查认证状态
async function checkAuth() {
    const token = localStorage.getItem('admin_token');
    if (!token) {
        window.location.href = '/admin';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/check`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (!result.authenticated) {
            localStorage.removeItem('admin_token');
            localStorage.removeItem('admin_info');
            window.location.href = '/admin';
            return;
        }

        currentAdmin = result.admin;
        document.getElementById('displayAdminUsername').textContent = currentAdmin.username;
        document.getElementById('displayAdminRole').textContent = currentAdmin.role_display;
    } catch (error) {
        console.error('认证检查失败:', error);
        window.location.href = '/admin';
    }
}

// 退出登录
async function logout() {
    const token = localStorage.getItem('admin_token');
    if (token) {
        try {
            await fetch(`${API_BASE}/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        } catch (error) {
            console.error('退出登录失败:', error);
        }
    }

    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_info');
    window.location.href = '/admin';
}

// 加载统计信息
async function loadStats() {
    const token = localStorage.getItem('admin_token');
    try {
        const response = await fetch(`${API_BASE}/stats`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            document.getElementById('totalUsers').textContent = result.stats.total_users;
            document.getElementById('activeUsers').textContent = result.stats.active_users;
            document.getElementById('totalAdmins').textContent = result.stats.total_admins;
            document.getElementById('pendingCount').textContent = result.stats.pending_feedbacks || 0;
            document.getElementById('processingCount').textContent = result.stats.processing_feedbacks || 0;
            document.getElementById('resolvedCount').textContent = result.stats.resolved_feedbacks || 0;
            // Activity stats
            document.getElementById('activeActivityCount').textContent = result.stats.active_activities || 0;
            document.getElementById('endedActivityCount').textContent = result.stats.ended_activities || 0;
            document.getElementById('currentActivityName').textContent = result.stats.current_activity_name || '-';
        }
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

// 跳转到反馈管理并筛选
function goToFeedback(status) {
    currentFeedbackStatus = status;
    switchNav('todo');
    // Wait for section to render, then apply filter
    setTimeout(() => {
        filterFeedbacks(status);
    }, 100);
}

// 跳转到活动管理
function goToActivity(status) {
    switchNav('activity');
    // TODO: Add activity filtering when Activity management is implemented
}

// 加载用户列表
async function loadUsers(page = 1) {
    const token = localStorage.getItem('admin_token');
    const search = document.getElementById('userSearch')?.value || '';

    try {
        const url = `${API_BASE}/users?page=${page}&per_page=${perPage}${search ? '&search=' + encodeURIComponent(search) : ''}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            displayUsers(result.users, result.page, result.pages);
            currentPage = page;
        }
    } catch (error) {
        console.error('加载用户列表失败:', error);
    }
}

// 显示用户列表
function displayUsers(users, page, totalPages) {
    const container = document.getElementById('usersTableContainer');

    if (users.length === 0) {
        container.innerHTML = '<div class="loading">暂无用户数据</div>';
        return;
    }

    let html = `
        <table>
            <thead>
                <tr>
                    <th style="width: 60px;">序号</th>
                    <th>用户名</th>
                    <th>邮箱</th>
                    <th>全名</th>
                    <th>积分</th>
                    <th>角色</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
    `;

    users.forEach((user, index) => {
        const serialNum = (page - 1) * perPage + index + 1;
        const createdAt = new Date(user.created_at).toLocaleString('zh-CN');
        const statusBadge = user.is_active
            ? '<span class="status-badge status-active">激活</span>'
            : '<span class="status-badge status-inactive">禁用</span>';

        html += `
            <tr>
                <td>${serialNum}</td>
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>${user.full_name || '-'}</td>
                <td><span style="color: #4caf50; font-weight: 600;">${user.points_balance || 0}</span></td>
                <td>${user.is_admin
                    ? '<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">管理员</span>'
                    : '<span style="background: #e0e0e0; color: #333; padding: 4px 8px; border-radius: 4px; font-size: 12px;">普通用户</span>'
                }</td>
                <td>${statusBadge}</td>
                <td>${createdAt}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-success" onclick="showPointsModal(${user.id}, '${user.username}', ${user.points_balance || 0})">积分</button>
                        <button class="btn btn-primary" onclick="editUser(${user.id})">编辑</button>
                        <button class="btn btn-danger" onclick="deleteUser(${user.id}, '${user.username}')">删除</button>
                    </div>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table>';

    // 添加分页
    if (totalPages > 1) {
        html += '<div class="pagination">';
        for (let i = 1; i <= totalPages; i++) {
            html += `<button class="${i === page ? 'active' : ''}" onclick="loadUsers(${i})">${i}</button>`;
        }
        html += '</div>';
    }

    container.innerHTML = html;
}

// 搜索用户
function searchUsers() {
    loadUsers(1);
}

// 显示创建用户模态框
function showCreateUserModal() {
    document.getElementById('userModalTitle').textContent = '添加用户';
    document.getElementById('userForm').reset();
    document.getElementById('userId').value = '';
    document.getElementById('passwordHint').style.display = 'none';
    document.getElementById('userPassword').required = true;
    document.getElementById('userModal').classList.add('active');
}

// 编辑用户
async function editUser(userId) {
    const token = localStorage.getItem('admin_token');

    try {
        const response = await fetch(`${API_BASE}/users/${userId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            const user = result.user;
            document.getElementById('userModalTitle').textContent = '编辑用户';
            document.getElementById('userId').value = user.id;
            document.getElementById('userUsername').value = user.username;
            document.getElementById('userEmail').value = user.email;
            document.getElementById('userFullName').value = user.full_name || '';
            document.getElementById('userPassword').value = '';
            document.getElementById('userPassword').required = false;
            document.getElementById('passwordHint').style.display = 'inline';
            document.getElementById('userActive').value = user.is_active.toString();
            document.getElementById('userRole').value = (user.is_admin || false).toString();
            document.getElementById('userModal').classList.add('active');
        }
    } catch (error) {
        console.error('加载用户信息失败:', error);
        alert('加载用户信息失败');
    }
}

// 删除用户
async function deleteUser(userId, username) {
    if (!confirm(`确定要删除用户 "${username}" 吗？此操作不可撤销！`)) {
        return;
    }

    const token = localStorage.getItem('admin_token');

    try {
        const response = await fetch(`${API_BASE}/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            alert(result.message);
            loadUsers(currentPage);
            loadStats();
        } else {
            alert(result.error || '删除失败');
        }
    } catch (error) {
        console.error('删除用户失败:', error);
        alert('删除用户失败');
    }
}

// 关闭用户模态框
function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
    document.getElementById('userFormError').textContent = '';
}

// 用户表单提交
// 移除重复的 userForm 监听器


// 加载管理员列表
async function loadAdmins() {
    const token = localStorage.getItem('admin_token');

    try {
        const response = await fetch(`${API_BASE}/admins`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            displayAdmins(result.admins);
        }
    } catch (error) {
        console.error('加载管理员列表失败:', error);
    }
}

// 显示管理员列表
function displayAdmins(admins) {
    const container = document.getElementById('adminsTableContainer');

    if (admins.length === 0) {
        container.innerHTML = '<div class="loading">暂无管理员数据</div>';
        return;
    }

    // 排序：高级管理员在前，然后按创建时间降序
    const sortedAdmins = [...admins].sort((a, b) => {
        // 高级管理员优先
        if (a.role === 'super_admin' && b.role !== 'super_admin') return -1;
        if (a.role !== 'super_admin' && b.role === 'super_admin') return 1;
        // 同级别按ID升序（1, 2, 3...）
        return a.id - b.id;
    });

    let html = `
        <table>
            <thead>
                <tr>
                    <th style="width: 60px;">序号</th>
                    <th>用户名</th>
                    <th>邮箱</th>
                    <th>角色</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
    `;

    sortedAdmins.forEach((admin, index) => {
        const createdAt = new Date(admin.created_at).toLocaleString('zh-CN');
        const statusBadge = admin.is_active
            ? '<span class="status-badge status-active">激活</span>'
            : '<span class="status-badge status-inactive">禁用</span>';

        // 角色徽章颜色
        const roleBadge = admin.role === 'super_admin'
            ? '<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">高级管理员</span>'
            : '<span style="background: #e0e0e0; color: #333; padding: 4px 8px; border-radius: 4px; font-size: 12px;">管理员</span>';

        // 只有高级管理员可以删除其他管理员，且不能删除自己和初始高级管理员
        const deleteBtn = (currentAdmin.role === 'super_admin' && admin.username !== 'HFzhouzhou' && admin.id !== currentAdmin.id)
            ? `<button class="btn btn-danger" onclick="deleteAdmin(${admin.id}, '${admin.username}')">删除</button>`
            : '';

        html += `
            <tr>
                <td>${index + 1}</td>
                <td>${admin.username}</td>
                <td>${admin.email || '-'}</td>
                <td>${roleBadge}</td>
                <td>${statusBadge}</td>
                <td>${createdAt}</td>
                <td>
                    <div class="action-buttons">
                        ${deleteBtn}
                    </div>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

// 显示创建管理员模态框
function showCreateAdminModal() {
    document.getElementById('adminForm').reset();
    document.getElementById('adminModal').classList.add('active');
}

// 删除管理员
async function deleteAdmin(adminId, username) {
    if (!confirm(`确定要删除管理员 "${username}" 吗？此操作不可撤销！`)) {
        return;
    }

    const token = localStorage.getItem('admin_token');

    try {
        const response = await fetch(`${API_BASE}/admins/${adminId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();
        if (result.success) {
            alert(result.message);
            loadAdmins();
            loadStats();
        } else {
            alert(result.error || '删除失败');
        }
    } catch (error) {
        console.error('删除管理员失败:', error);
        alert('删除管理员失败');
    }
}

// 关闭管理员模态框
function closeAdminModal() {
    document.getElementById('adminModal').classList.remove('active');
    document.getElementById('adminFormError').textContent = '';
}

// 管理员表单提交
// ==================== 积分管理功能 ====================

// 显示积分管理模态框
function showPointsModal(userId, username, currentPoints) {
    document.getElementById('pointsUserId').value = userId;
    document.getElementById('pointsUsername').value = username;
    document.getElementById('currentPoints').value = currentPoints;
    document.getElementById('pointsAmount').value = '';
    document.getElementById('pointsReason').value = '';
    document.getElementById('pointsAction').value = 'set';
    document.getElementById('pointsFormError').textContent = '';
    document.getElementById('pointsModal').classList.add('active');
}

// 关闭积分管理模态框
function closePointsModal() {
    document.getElementById('pointsModal').classList.remove('active');
    document.getElementById('pointsFormError').textContent = '';
}


// ==================== 反馈管理功能 ====================

let currentFeedbackStatus = 'all';

function filterFeedbacks(status) {
    currentFeedbackStatus = status;
    // Update buttons
    document.querySelectorAll('.status-filters button').forEach(btn => {
        if (btn.textContent.includes(getStatusLabel(status))) {
            // simple check based on click handler would be better but DOM order matches
        }
        // Reset all classes manually or re-render
        btn.classList.remove('active');
        if (btn.getAttribute('onclick').includes(`'${status}'`)) {
            btn.classList.add('active');
        }
    });
    loadFeedbacks(1);
}

function getStatusLabel(status) {
    const map = { 'all': '全部', 'pending': '待处理', 'processing': '处理中', 'resolved': '已处理' };
    return map[status] || status;
}

async function loadFeedbacks(page = 1) {
    const token = localStorage.getItem('admin_token');
    try {
        let url = `${API_BASE}/feedbacks?page=${page}&per_page=${perPage}`;
        if (currentFeedbackStatus !== 'all') {
            url += `&status=${currentFeedbackStatus}`;
        }

        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const result = await response.json();
        if (result.success) {
            displayFeedbacks(result.feedbacks, result.page, result.pages);
        } else {
            document.getElementById('feedbacksTableContainer').innerHTML = `<div class="error-message">${result.error}</div>`;
        }
    } catch (e) {
        console.error(e);
        document.getElementById('feedbacksTableContainer').innerHTML = '<div class="error-message">加载失败</div>';
    }
}

function displayFeedbacks(feedbacks, page, totalPages) {
    const container = document.getElementById('feedbacksTableContainer');
    if (!feedbacks || feedbacks.length === 0) {
        container.innerHTML = '<div class="loading">暂无反馈数据</div>';
        return;
    }

    let html = `
        <table>
            <thead>
                <tr>
                    <th style="width: 50px;">ID</th>
                    <th>用户</th>
                    <th>类型</th>
                    <th style="width: 40%">内容</th>
                    <th>联系方式</th>
                    <th>状态</th>
                    <th>提交时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
    `;

    feedbacks.forEach(fb => {
        const typeMap = { 'suggestion': '✨ 建议', 'bug': '🐛 Bug', 'other': '📝 其他' };
        const statusMap = {
            'pending': '<span class="status-badge" style="background:#fee2e2;color:#b91c1c">待处理</span>',
            'processing': '<span class="status-badge" style="background:#fef3c7;color:#b45309">处理中</span>',
            'resolved': '<span class="status-badge" style="background:#d1fae5;color:#047857">已处理</span>'
        };

        const nextStatusBtn = getNextStatusButton(fb);

        html += `
            <tr>
                <td>${fb.id}</td>
                <td>${fb.username}<br><small style="color:#999">${fb.user_email}</small></td>
                <td>${typeMap[fb.type] || fb.type}</td>
                <td><div style="max-height: 80px; overflow-y: auto; font-size: 13px;">${escapeHtml(fb.content)}</div></td>
                <td>${fb.contact || '-'}</td>
                <td>${statusMap[fb.status] || fb.status}</td>
                <td><small>${new Date(fb.created_at).toLocaleString()}</small></td>
                <td>
                    <div class="action-buttons">
                        ${nextStatusBtn}
                    </div>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table>';

    // Pagination
    if (totalPages > 1) {
        html += '<div class="pagination">';
        for (let i = 1; i <= totalPages; i++) {
            html += `<button class="${i === page ? 'active' : ''}" onclick="loadFeedbacks(${i})">${i}</button>`;
        }
        html += '</div>';
    }

    container.innerHTML = html;
}

function getNextStatusButton(fb) {
    if (fb.status === 'pending') {
        return `<button class="btn btn-sm btn-primary" onclick="updateStatus(${fb.id}, 'processing')">开始处理</button>`;
    } else if (fb.status === 'processing') {
        return `<button class="btn btn-sm btn-success" onclick="updateStatus(${fb.id}, 'resolved')">完成</button>`;
    } else {
        return `<button class="btn btn-sm" onclick="updateStatus(${fb.id}, 'processing')">重开</button>`;
    }
}

async function updateStatus(id, newStatus) {
    const token = localStorage.getItem('admin_token');
    try {
        const response = await fetch(`${API_BASE}/feedbacks/${id}/status`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: newStatus })
        });

        const result = await response.json();
        if (result.success) {
            loadFeedbacks(currentPage); // reload current page
        } else {
            alert(result.error || '更新失败');
        }
    } catch (e) {
        console.error(e);
        alert('网络错误');
    }
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ==================== 图表功能 ====================

let statsChart = null;
let currentChartType = 'interactions';

async function switchChartType(type) {
    currentChartType = type;
    // Update buttons
    document.querySelectorAll('.chart-controls .btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.getElementById(`btn-chart-${type === 'interactions' ? 'interactions' : 'users'}`);
    if (btn) btn.classList.add('active');

    const token = localStorage.getItem('admin_token');
    const daysSelect = document.getElementById('statsChartDays');
    const days = daysSelect ? daysSelect.value : 7;
    try {
        const response = await fetch(`${API_BASE}/stats/chart?type=${type}&days=${days}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const result = await response.json();

        if (result.success) {
            renderChart(result.labels, result.data, type);
        }
    } catch (e) {
        console.error("Chart fetch error", e);
    }
}

function renderChart(labels, data, type) {
    const canvas = document.getElementById('statsChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const label = type === 'interactions' ? 'AI 交互次数' : '日活跃用户';
    const color = type === 'interactions' ? '#1677ff' : '#52c41a'; // Blue or Green

    if (statsChart) {
        statsChart.destroy();
    }

    statsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                borderColor: color,
                backgroundColor: color + '20', // 20% opacity using hex alpha
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    },
                    grid: {
                        borderDash: [2, 4]
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// 每日流水图表
let revenueChart = null;

async function loadRevenueChart() {
    const token = localStorage.getItem('admin_token');
    const daysSelect = document.getElementById('revenueChartDays');
    const days = daysSelect ? daysSelect.value : 7;
    try {
        const response = await fetch(`${API_BASE}/stats/chart?type=revenue&days=${days}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const result = await response.json();

        if (result.success) {
            renderRevenueChart(result.labels, result.data);
        }
    } catch (e) {
        console.error("Revenue chart fetch error", e);
    }
}

function renderRevenueChart(labels, data) {
    const canvas = document.getElementById('revenueChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const color = '#f5222d'; // Red for money

    if (revenueChart) {
        revenueChart.destroy();
    }

    revenueChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '每日流水 (元)',
                data: data,
                borderColor: color,
                backgroundColor: color + '20',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            var label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += '¥' + context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function (value, index, values) {
                            return '¥' + value;
                        }
                    },
                    grid: {
                        borderDash: [2, 4]
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}
