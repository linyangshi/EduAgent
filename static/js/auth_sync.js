/**
 * auth_sync.js
 * 同步前端 sessionStorage Token 与页面登录状态
 * 如果 sessionStorage 短暂丢失（例如移动设备在新标签页打开链接），将尝试通过 Flask Session 自动恢复
 */

(function() {
    function updateUI(isLoggedIn) {
        document.querySelectorAll('.user-profile').forEach(el => {
            el.style.display = isLoggedIn ? 'flex' : 'none';
        });

        document.querySelectorAll('.guest-only').forEach(el => {
            el.style.display = isLoggedIn ? 'none' : 'flex';
        });
    }

    async function checkLoginStatus() {
        let authToken = sessionStorage.getItem('auth_token');
        const isLoggedInInTemplate = document.body.dataset.isLoggedIn === 'true';

        console.log('🔄 AuthSync: Token=', !!authToken, 'TemplateLoggedIn=', isLoggedInInTemplate);

        if (!authToken) {
            if (isLoggedInInTemplate) {
                console.log('🔄 AuthSync: Attempting to recover token from server session (mobile context swap detected)...');
                try {
                    const res = await fetch('/api/auth/recover-token', { method: 'POST', headers: {'Content-Type': 'application/json'} });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.success && data.token) {
                            sessionStorage.setItem('auth_token', data.token);
                            if (data.user) {
                                sessionStorage.setItem('username', data.user.username);
                                if (data.user.avatar_url) sessionStorage.setItem('avatar_url', data.user.avatar_url);
                            }
                            console.log('✅ AuthSync: Token recovered successfully!');
                            authToken = data.token;
                        }
                    }
                } catch (e) {
                    console.error('AuthSync: Failed to recover token', e);
                }
            }

            if (!authToken) {
                updateUI(false);
                if (document.body.dataset.requireAuth === 'true') {
                    console.warn('🚨 需要认证但 Token 缺失，准备跳转登录...');
                    window.location.href = '/login?msg=session_expired';
                }
                return;
            }
        }
        
        // 如果有 Token 或恢复成功
        updateUI(true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkLoginStatus);
    } else {
        checkLoginStatus();
    }
    
    window.addEventListener('storage', (e) => {
        if (e.key === 'auth_token') {
            checkLoginStatus();
        }
    });

    window.syncAuthUI = checkLoginStatus;
})();

window.checkLoginAndRedirect = async function(targetUrl, message = '请先登录后再进行操作') {
    let authToken = sessionStorage.getItem('auth_token');
    
    // 如果 token 丢失但 HTML 渲染出已登录标记，尝试拉回 token
    if (!authToken && document.body.dataset.isLoggedIn === 'true') {
        try {
            const res = await fetch('/api/auth/recover-token', { method: 'POST', headers: {'Content-Type': 'application/json'} });
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.token) {
                    sessionStorage.setItem('auth_token', data.token);
                    authToken = data.token;
                }
            }
        } catch (e) {
            console.error('Recover failed during redirect check', e);
        }
    }

    if (!authToken) {
        alert(message);
        window.location.href = `/login?next=${encodeURIComponent(targetUrl)}`;
        return false;
    }
    window.location.href = targetUrl;
    return true;
};
