/**
 * 前端认证检查模块
 * 用于检测用户登录状态并在需要时显示登录提示
 */

class AuthCheck {
    constructor() {
        this.isAuthenticated = false;
        this.user = null;
        this.checkInProgress = false;
    }

    /**
     * 检查用户是否已登录
     * @returns {Promise<boolean>} 是否已登录
     */
    async checkAuth() {
        if (this.checkInProgress) {
            // 等待正在进行的检查完成
            await new Promise(resolve => {
                const interval = setInterval(() => {
                    if (!this.checkInProgress) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 100);
            });
            return this.isAuthenticated;
        }

        this.checkInProgress = true;

        try {
            let token = sessionStorage.getItem('auth_token');
            
            // 如果 token 缺失，尝试从后端的 Flask Session 中恢复
            if (!token) {
                console.log('🔄 AuthCheck: 尝试通过 /api/auth/recover-token 恢复 Token...');
                try {
                    const recRes = await fetch('/api/auth/recover-token', { method: 'POST', headers: {'Content-Type': 'application/json'} });
                    if (recRes.ok) {
                        const recData = await recRes.json();
                        if (recData.success && recData.token) {
                            sessionStorage.setItem('auth_token', recData.token);
                            token = recData.token;
                            if (recData.user) {
                                sessionStorage.setItem('username', recData.user.username);
                                if (recData.user.avatar_url) sessionStorage.setItem('avatar_url', recData.user.avatar_url);
                            }
                            console.log('✅ AuthCheck: Token 恢复成功!');
                        }
                    }
                } catch (e) {
                    console.error('AuthCheck: Token 恢复请求失败', e);
                }
            }

            if (!token) {
                this.isAuthenticated = false;
                this.user = null;
                this.checkInProgress = false;
                return false;
            }

            const response = await fetch('/api/auth/check', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.isAuthenticated = data.authenticated || false;
                this.user = data.user || null;
                this.checkInProgress = false;
                return this.isAuthenticated;
            } else {
                this.isAuthenticated = false;
                this.user = null;
                sessionStorage.removeItem('auth_token');
                this.checkInProgress = false;
                return false;
            }
        } catch (error) {
            console.error('认证检查失败:', error);
            this.isAuthenticated = false;
            this.user = null;
            this.checkInProgress = false;
            return false;
        }
    }

    /**
     * 显示登录提示弹窗
     * @param {string} message - 提示信息
     */
    showLoginPrompt(message = '请先登录后再使用此功能') {
        // 移除已存在的提示框
        const existingPrompt = document.getElementById('auth-prompt-overlay');
        if (existingPrompt) {
            existingPrompt.remove();
        }

        // 创建遮罩层
        const overlay = document.createElement('div');
        overlay.id = 'auth-prompt-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            right: 0;
            bottom: 0;
            left: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 80px;
            z-index: 10000;
            animation: fadeIn 0.2s ease-out;
        `;

        // 创建提示框
        const promptBox = document.createElement('div');
        promptBox.style.cssText = `
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 32px;
            max-width: 420px;
            width: 90%;
            text-align: center;
            animation: slideDown 0.3s ease-out;
        `;

        // 图标
        const icon = document.createElement('div');
        icon.innerHTML = `
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" style="margin: 0 auto 20px;">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6M12 16h.01"/>
            </svg>
        `;

        // 标题
        const title = document.createElement('h3');
        title.textContent = '需要登录';
        title.style.cssText = `
            margin: 0 0 16px 0;
            font-size: 24px;
            font-weight: 600;
            color: #1f2937;
        `;

        // 消息
        const messageEl = document.createElement('p');
        messageEl.textContent = message;
        messageEl.style.cssText = `
            margin: 0 0 32px 0;
            font-size: 16px;
            color: #6b7280;
            line-height: 1.6;
        `;

        // 按钮容器
        const buttonContainer = document.createElement('div');
        buttonContainer.style.cssText = `
            display: flex;
            gap: 12px;
            justify-content: center;
        `;

        // 登录按钮
        const loginButton = document.createElement('button');
        loginButton.textContent = '立即登录';
        loginButton.style.cssText = `
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 32px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;
        loginButton.onmouseover = () => {
            loginButton.style.background = '#2563eb';
            loginButton.style.transform = 'translateY(-1px)';
            loginButton.style.boxShadow = '0 4px 12px rgba(59, 130, 246, 0.4)';
        };
        loginButton.onmouseout = () => {
            loginButton.style.background = '#3b82f6';
            loginButton.style.transform = 'translateY(0)';
            loginButton.style.boxShadow = 'none';
        };
        loginButton.onclick = () => {
            // 保存当前页面URL，登录后返回
            localStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
            window.location.href = '/login';
        };

        // 注册按钮
        const registerButton = document.createElement('button');
        registerButton.textContent = '注册账号';
        registerButton.style.cssText = `
            background: white;
            color: #3b82f6;
            border: 2px solid #3b82f6;
            border-radius: 8px;
            padding: 12px 32px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        `;
        registerButton.onmouseover = () => {
            registerButton.style.background = '#eff6ff';
            registerButton.style.transform = 'translateY(-1px)';
        };
        registerButton.onmouseout = () => {
            registerButton.style.background = 'white';
            registerButton.style.transform = 'translateY(0)';
        };
        registerButton.onclick = () => {
            localStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
            window.location.href = '/register';
        };

        // 组装
        buttonContainer.appendChild(loginButton);
        buttonContainer.appendChild(registerButton);
        promptBox.appendChild(icon);
        promptBox.appendChild(title);
        promptBox.appendChild(messageEl);
        promptBox.appendChild(buttonContainer);
        overlay.appendChild(promptBox);

        // 点击遮罩层关闭（可选，但为了强制登录，暂时禁用）
        // overlay.onclick = (e) => {
        //     if (e.target === overlay) {
        //         overlay.remove();
        //     }
        // };

        // 添加CSS动画
        const style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes slideDown {
                from {
                    opacity: 0;
                    transform: translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        `;
        document.head.appendChild(style);

        document.body.appendChild(overlay);
    }

    /**
     * 在右上角显示简短提示
     * @param {string} message - 提示信息
     */
    showTopNotification(message = '请先登录') {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #3b82f6;
            color: white;
            padding: 16px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10001;
            font-size: 14px;
            font-weight: 500;
            animation: slideInRight 0.3s ease-out;
            cursor: pointer;
        `;
        notification.textContent = message;

        // 点击后跳转到登录页
        notification.onclick = () => {
            localStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
            window.location.href = '/login';
        };

        // 添加动画
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideInRight {
                from {
                    opacity: 0;
                    transform: translateX(100px);
                }
                to {
                    opacity: 1;
                    transform: translateX(0);
                }
            }
        `;
        if (!document.querySelector('style[data-auth-animation]')) {
            style.setAttribute('data-auth-animation', 'true');
            document.head.appendChild(style);
        }

        document.body.appendChild(notification);

        // 3秒后自动移除
        setTimeout(() => {
            notification.style.animation = 'slideInRight 0.3s ease-out reverse';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    /**
     * 要求用户登录（显示完整弹窗）
     * @param {string} message - 提示信息
     * @returns {Promise<boolean>} 是否已登录
     */
    async requireAuth(message = '请先登录后再使用此功能') {
        const isAuth = await this.checkAuth();
        if (!isAuth) {
            this.showLoginPrompt(message);
            return false;
        }
        return true;
    }

    /**
     * 拦截API请求，自动添加认证头
     * @param {string} url - API URL
     * @param {object} options - fetch options
     * @returns {Promise<Response>}
     */
    async authenticatedFetch(url, options = {}) {
        const token = sessionStorage.getItem('auth_token');
        if (!token) {
            this.showLoginPrompt();
            throw new Error('未登录');
        }

        const headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };

        const response = await fetch(url, {
            ...options,
            headers
        });

        // 如果返回401，说明token失效
        if (response.status === 401) {
            sessionStorage.removeItem('auth_token');
            this.isAuthenticated = false;
            this.user = null;
            this.showLoginPrompt('登录已过期，请重新登录');
            throw new Error('认证失败');
        }

        return response;
    }
}

// 创建全局实例
window.authCheck = new AuthCheck();

// 页面加载时自动检查认证状态
document.addEventListener('DOMContentLoaded', async () => {
    await window.authCheck.checkAuth();
});
