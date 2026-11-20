/**
 * 个人中心页面脚本
 * Profile Page Script
 */

let cropper = null;
let currentUser = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', async () => {
    if (!document.getElementById('profile-section')) return;

    await initProfilePage();
});

/**
 * 初始化个人中心页面
 */
async function initProfilePage() {
    // 初始化导航切换
    initSectionSwitching();

    // 加载用户资料
    await loadUserProfile();

    // 初始化头像上传
    initAvatarUpload();

    // 绑定事件
    bindProfileEvents();

    // 加载会话列表
    await loadSessions();

    // 初始化OAuth绑定
    initOAuthBindings();
}

/**
 * 初始化导航切换
 */
function initSectionSwitching() {
    const navItems = document.querySelectorAll('.sidebar-nav-item');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const sectionName = item.getAttribute('data-section');

            // 切换激活状态
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            // 切换内容区域
            document.querySelectorAll('.section').forEach(section => {
                section.classList.remove('active');
            });

            const targetSection = document.getElementById(`${sectionName}-section`);
            if (targetSection) {
                targetSection.classList.add('active');

                // 如果切换到会话列表，重新加载
                if (sectionName === 'sessions') {
                    loadSessions();
                }
            }
        });
    });
}

/**
 * 加载用户资料
 */
async function loadUserProfile() {
    try {
        if (window.authCheck) {
            const isAuth = await window.authCheck.checkAuth();
            if (!isAuth) {
                window.location.href = '/login';
                return;
            }
        }
        
        const token = sessionStorage.getItem('auth_token');
        if (!token) {
            window.location.href = '/login';
            return;
        }

        const response = await fetch('/api/auth/profile', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success && data.user) {
                currentUser = data.user;
                fillUserProfile(data.user);
            }
        } else if (response.status === 401) {
            sessionStorage.removeItem('auth_token');
            window.location.href = '/login';
        }
    } catch (error) {
        console.error('加载用户资料失败:', error);
        showError('加载用户资料失败，请刷新页面重试');
    }
}

/**
 * 填充用户资料到表单
 */
function fillUserProfile(user) {
    document.getElementById('username').value = user.username || '';
    document.getElementById('email').value = user.email || '';
    document.getElementById('full_name').value = user.full_name || '';

    // 更新头像显示
    updateAvatarDisplay(user);
}

/**
 * 更新头像显示
 */
function updateAvatarDisplay(user) {
    const avatarPreview = document.getElementById('avatar-preview');

    if (!user || !avatarPreview) return;

    // 获取首字母作为回退
    const firstLetter = user.username ? user.username.charAt(0).toUpperCase() : '?';

    // 显示首字母的函数
    const showInitial = () => {
        avatarPreview.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        avatarPreview.innerHTML = `<span class="avatar-placeholder" style="color: white; font-size: 2rem; font-weight: 600;">${firstLetter}</span>`;
    };

    if (user.avatar_url) {
        // 有头像URL：尝试加载图片
        const img = new Image();
        img.onload = function () {
            // 图片加载成功
            avatarPreview.style.background = 'none';
            avatarPreview.innerHTML = `<img src="${user.avatar_url}" alt="${user.username}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
        };
        img.onerror = function () {
            // 图片加载失败，显示首字母
            showInitial();
        };
        img.src = user.avatar_url;
    } else {
        // 无头像URL：直接显示首字母
        showInitial();
    }
}

/**
 * 初始化头像上传
 */
function initAvatarUpload() {
    const uploadBtn = document.getElementById('uploadAvatarBtn');
    const avatarInput = document.getElementById('avatar-input');
    const cropModal = document.getElementById('avatar-crop-modal');
    const cropImage = document.getElementById('crop-image');
    const confirmCropBtn = document.getElementById('confirmCropBtn');
    const cancelCropBtn = document.getElementById('cancelCropBtn');
    const closeCropModal = document.getElementById('closeCropModal');

    // 点击上传按钮
    uploadBtn.addEventListener('click', () => {
        avatarInput.click();
    });

    // 选择文件后
    avatarInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // 验证文件
        if (!file.type.startsWith('image/')) {
            showError('请选择图片文件');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showError('图片大小不能超过 5MB');
            return;
        }

        // 显示裁剪对话框
        const reader = new FileReader();
        reader.onload = (event) => {
            cropImage.src = event.target.result;
            cropModal.showModal();

            // 初始化Cropper
            if (cropper) {
                cropper.destroy();
            }

            cropper = new Cropper(cropImage, {
                aspectRatio: 1,
                viewMode: 1,
                dragMode: 'move',
                autoCropArea: 0.8,
                restore: false,
                guides: true,
                center: true,
                highlight: false,
                cropBoxMovable: true,
                cropBoxResizable: true,
                toggleDragModeOnDblclick: false
            });
        };
        reader.readAsDataURL(file);
    });

    // 确认裁剪
    confirmCropBtn.addEventListener('click', async () => {
        if (!cropper) return;

        // 获取裁剪后的canvas
        const canvas = cropper.getCroppedCanvas({
            width: 200,
            height: 200,
            imageSmoothingQuality: 'high'
        });

        // 转换为blob
        canvas.toBlob(async (blob) => {
            await uploadAvatar(blob);
            cropModal.close();
            cropper.destroy();
            cropper = null;
            avatarInput.value = '';
        }, 'image/jpeg', 0.9);
    });

    // 取消裁剪
    const closeModal = () => {
        cropModal.close();
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
        avatarInput.value = '';
    };

    cancelCropBtn.addEventListener('click', closeModal);
    closeCropModal.addEventListener('click', closeModal);
}

/**
 * 上传头像
 */
async function uploadAvatar(blob) {
    try {
        const token = sessionStorage.getItem('auth_token');
        const formData = new FormData();
        formData.append('avatar', blob, 'avatar.jpg');

        const confirmBtn = document.getElementById('confirmCropBtn');
        const confirmBtnText = document.getElementById('confirmBtnText');
        const originalText = confirmBtnText.textContent;

        confirmBtn.disabled = true;
        confirmBtnText.textContent = '上传中...';

        const response = await fetch('/api/auth/upload-avatar', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // 更新头像显示
            currentUser.avatar_url = data.avatar_url;
            updateAvatarDisplay(currentUser);

            // 刷新认证状态（更新全局用户信息）
            if (window.authCheck) {
                await window.authCheck.checkAuth();
            }

            showSuccess('头像上传成功');
        } else {
            showError(data.error || '头像上传失败');
        }

        confirmBtn.disabled = false;
        confirmBtnText.textContent = originalText;

    } catch (error) {
        console.error('上传头像失败:', error);
        showError('上传头像失败，请重试');
    }
}

/**
 * 绑定事件
 */
function bindProfileEvents() {
    // 保存资料
    document.getElementById('saveProfileBtn').addEventListener('click', handleSaveProfile);

    // 修改密码
    document.getElementById('changePasswordBtn').addEventListener('click', handleChangePassword);

    // 退出登录
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }
}

/**
 * 保存个人资料
 */
async function handleSaveProfile() {
    try {
        const token = sessionStorage.getItem('auth_token');
        const fullName = document.getElementById('full_name').value.trim();

        const btn = document.getElementById('saveProfileBtn');
        btn.disabled = true;
        btn.innerHTML = '<div class="loading" style="width: 16px; height: 16px; border: 2px solid white; border-top-color: transparent; border-radius: 50%;"></div> 保存中...';

        const response = await fetch('/api/auth/profile', {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ full_name: fullName })
        });

        const data = await response.json();

        if (data.success) {
            currentUser = data.user;
            showSuccess('个人信息已成功保存');

            // 刷新认证状态
            if (window.authCheck) {
                await window.authCheck.checkAuth();
            }
        } else {
            showError(data.error || '保存失败');
        }

        btn.disabled = false;
        btn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
                <polyline points="17 21 17 13 7 13 7 21"></polyline>
                <polyline points="7 3 7 8 15 8"></polyline>
            </svg>
            保存更改
        `;

    } catch (error) {
        console.error('保存资料失败:', error);
        showError('保存失败，请重试');
    }
}

/**
 * 修改密码
 */
async function handleChangePassword() {
    try {
        const oldPassword = document.getElementById('old_password').value;
        const newPassword = document.getElementById('new_password').value;
        const confirmPassword = document.getElementById('confirm_password').value;

        // 验证
        if (!oldPassword || !newPassword || !confirmPassword) {
            showError('请填写所有密码字段');
            return;
        }

        if (newPassword !== confirmPassword) {
            showError('两次输入的新密码不一致');
            return;
        }

        if (newPassword.length < 8) {
            showError('新密码长度至少8位');
            return;
        }

        const token = sessionStorage.getItem('auth_token');
        const btn = document.getElementById('changePasswordBtn');
        btn.disabled = true;
        btn.innerHTML = '<div class="loading" style="width: 16px; height: 16px; border: 2px solid white; border-top-color: transparent; border-radius: 50%;"></div> 更新中...';

        const response = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('password-success').style.display = 'block';
            document.getElementById('old_password').value = '';
            document.getElementById('new_password').value = '';
            document.getElementById('confirm_password').value = '';

            // 3秒后跳转到登录页
            setTimeout(() => {
                sessionStorage.removeItem('auth_token');
                window.location.href = '/login';
            }, 3000);
        } else {
            showError(data.error || '密码修改失败');
            btn.disabled = false;
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
                更新密码
            `;
        }

    } catch (error) {
        console.error('修改密码失败:', error);
        showError('修改密码失败，请重试');
    }
}

/**
 * 加载会话列表
 */
async function loadSessions() {
    try {
        const token = sessionStorage.getItem('auth_token');
        const response = await fetch('/api/auth/sessions', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success && data.sessions) {
                renderSessions(data.sessions);
            }
        }
    } catch (error) {
        console.error('加载会话列表失败:', error);
    }
}

/**
 * 渲染会话列表
 */
function renderSessions(sessions) {
    const sessionsList = document.getElementById('sessionsList');

    if (!sessions || sessions.length === 0) {
        sessionsList.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #6b7280;">
                <svg style="width: 48px; height: 48px; margin: 0 auto 16px; opacity: 0.5;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                    <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <p>暂无登录设备</p>
            </div>
        `;
        return;
    }

    sessionsList.innerHTML = sessions.map(session => `
        <div class="session-item">
            <div class="session-info">
                <div class="session-device">
                    <svg style="width: 20px; height: 20px; margin-right: 8px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        ${getDeviceIcon(session.device_type)}
                    </svg>
                    ${session.device_name || '未知设备'}
                    ${session.is_current ? '<span class="session-current-badge">当前设备</span>' : ''}
                </div>
                <div class="session-details">
                    <div>${session.browser_name || ''} · ${session.os_name || ''}</div>
                    <div>IP: ${session.ip_address || '未知'}</div>
                    <div>最后活动: ${formatDate(session.last_used_at)}</div>
                </div>
            </div>
            <div class="session-actions">
                ${!session.is_current ? `
                    <button class="btn btn-danger" onclick="revokeSession(${session.id})">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        移除
                    </button>
                ` : ''}
            </div>
        </div>
    `).join('');
}

/**
 * 获取设备图标
 */
function getDeviceIcon(deviceType) {
    const icons = {
        mobile: '<rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect><line x1="12" y1="18" x2="12.01" y2="18"></line>',
        tablet: '<rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect><line x1="12" y1="18" x2="12.01" y2="18"></line>',
        desktop: '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line>'
    };
    return icons[deviceType] || icons.desktop;
}

/**
 * 撤销会话
 */
async function revokeSession(sessionId) {
    if (!confirm('确定要移除此设备的登录吗？')) return;

    try {
        const token = sessionStorage.getItem('auth_token');
        const response = await fetch(`/api/auth/sessions/${sessionId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (data.success) {
            showSuccess('设备已移除');
            await loadSessions();
        } else {
            showError(data.error || '移除失败');
        }
    } catch (error) {
        console.error('撤销会话失败:', error);
        showError('操作失败，请重试');
    }
}

// 全局函数，供HTML调用
window.revokeSession = revokeSession;

/**
 * 格式化日期
 */
function formatDate(dateString) {
    if (!dateString) return '未知';

    const date = new Date(dateString);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}天前`;

    return date.toLocaleDateString('zh-CN');
}

/**
 * 显示成功消息
 */
function showSuccess(message) {
    const hint = document.getElementById('profile-save-hint');
    if (hint) {
        hint.textContent = message;
        hint.style.display = 'block';
        setTimeout(() => {
            hint.style.display = 'none';
        }, 3000);
    }
}

/**
 * 显示错误消息
 */
function showError(message) {
    alert(message);
}

/**
 * 处理退出登录
 */
async function handleLogout() {
    if (!confirm('确定要退出登录吗？')) return;

    try {
        const token = sessionStorage.getItem('auth_token');

        // 调用退出登录API
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        // 清除本地存储
        sessionStorage.removeItem('auth_token');
        localStorage.removeItem('remember_me');

        // 跳转到登录页
        window.location.href = '/login';

    } catch (error) {
        console.error('退出登录失败:', error);
        // 即使API调用失败，也清除本地token并跳转
        sessionStorage.removeItem('auth_token');
        localStorage.removeItem('remember_me');
        window.location.href = '/login';
    }
}

/**
 * 初始化OAuth绑定
 */
function initOAuthBindings() {
    if (!currentUser) return;

    // 更新微信绑定状态
    const wechatStatus = document.getElementById('wechat-status');
    const wechatBtn = document.getElementById('wechat-bind-btn');

    if (currentUser.wechat_bound) {
        wechatStatus.textContent = '已绑定';
        wechatStatus.style.color = '#059669';
        wechatBtn.textContent = '解绑';
        wechatBtn.classList.remove('btn-primary');
        wechatBtn.classList.add('btn-secondary');
        wechatBtn.onclick = () => handleUnbind('wechat');
    } else {
        wechatStatus.textContent = '未绑定';
        wechatStatus.style.color = '#6b7280';
        wechatBtn.textContent = '绑定';
        wechatBtn.classList.remove('btn-secondary');
        wechatBtn.classList.add('btn-primary');
        wechatBtn.onclick = () => handleBind('wechat');
    }

    // 更新QQ绑定状态
    const qqStatus = document.getElementById('qq-status');
    const qqBtn = document.getElementById('qq-bind-btn');

    if (currentUser.qq_bound) {
        qqStatus.textContent = '已绑定';
        qqStatus.style.color = '#059669';
        qqBtn.textContent = '解绑';
        qqBtn.classList.remove('btn-primary');
        qqBtn.classList.add('btn-secondary');
        qqBtn.onclick = () => handleUnbind('qq');
    } else {
        qqStatus.textContent = '未绑定';
        qqStatus.style.color = '#6b7280';
        qqBtn.textContent = '绑定';
        qqBtn.classList.remove('btn-secondary');
        qqBtn.classList.add('btn-primary');
        qqBtn.onclick = () => handleBind('qq');
    }
}

/**
 * 处理OAuth绑定
 */
async function handleBind(platform) {
    const platformName = platform === 'wechat' ? '微信' : 'QQ';

    if (!confirm(`将跳转到${platformName}进行账号绑定，是否继续？`)) {
        return;
    }

    // 直接跳转到OAuth授权页面
    window.location.href = `/auth/${platform}?action=bind`;
}

/**
 * 处理OAuth解绑
 */
async function handleUnbind(platform) {
    const platformName = platform === 'wechat' ? '微信' : 'QQ';

    if (!confirm(`确定要解绑${platformName}账号吗？`)) {
        return;
    }

    try {
        const token = sessionStorage.getItem('auth_token');
        const response = await fetch(`/api/unbind/${platform}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            showSuccess(`${platformName}解绑成功`);

            // 重新加载用户资料
            await loadUserProfile();
            initOAuthBindings();
        } else {
            showError(data.message || `${platformName}解绑失败`);
        }
    } catch (error) {
        console.error(`${platformName}解绑失败:`, error);
        showError('操作失败，请重试');
    }
}

