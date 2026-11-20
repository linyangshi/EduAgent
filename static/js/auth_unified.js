/**
 * 统一认证界面交互逻辑
 * Unified Auth Interface Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    initAuthInterface();

    // 初始化密码强度校验
    initPasswordValidation();
});

function initAuthInterface() {
    // 获取DOM元素
    const loginTab = document.getElementById('loginTab');
    const registerTab = document.getElementById('registerTab');
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const switchLink = document.getElementById('switchLink');
    const switchText = document.getElementById('switchText');
    const welcomeTitle = document.getElementById('welcomeTitle');
    const sendCodeBtn = document.getElementById('sendCodeBtn');

    // 标签切换逻辑
    loginTab.addEventListener('click', () => switchToLogin());
    registerTab.addEventListener('click', () => switchToRegister());
    switchLink.addEventListener('click', () => {
        if (loginForm.classList.contains('active')) {
            switchToRegister();
        } else {
            switchToLogin();
        }
    });

    // 验证码发送
    if (sendCodeBtn) {
        sendCodeBtn.addEventListener('click', handleSendCode);
    }

    // 表单提交
    loginForm.addEventListener('submit', handleLogin);
    registerForm.addEventListener('submit', handleRegister);

    // 初始化根据URL参数
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'register') {
        switchToRegister();
    }
}

/**
 * 切换到登录表单
 */
function switchToLogin() {
    const loginTab = document.getElementById('loginTab');
    const registerTab = document.getElementById('registerTab');
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const switchText = document.getElementById('switchText');
    const switchLink = document.getElementById('switchLink');

    loginTab.classList.add('active');
    registerTab.classList.remove('active');
    loginForm.classList.add('active');
    registerForm.classList.remove('active');

    switchText.textContent = '没有账号？';
    switchLink.textContent = '现在注册';

    // 更新URL
    history.pushState({}, '', '/login');
}

/**
 * 切换到注册表单
 */
function switchToRegister() {
    const loginTab = document.getElementById('loginTab');
    const registerTab = document.getElementById('registerTab');
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const switchText = document.getElementById('switchText');
    const switchLink = document.getElementById('switchLink');

    registerTab.classList.add('active');
    loginTab.classList.remove('active');
    registerForm.classList.add('active');
    loginForm.classList.remove('active');

    switchText.textContent = '已有账号？';
    switchLink.textContent = '立即登录';

    // 更新URL
    history.pushState({}, '', '/register');
}

/**
 * 切换密码可见性
 */
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
}

/**
 * 发送邮箱验证码
 */
async function handleSendCode() {
    const emailInput = document.getElementById('register-email');
    const email = emailInput.value.trim();
    const sendCodeBtn = document.getElementById('sendCodeBtn');

    // 验证邮箱
    if (!email) {
        alert('请先输入邮箱地址');
        emailInput.focus();
        return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        alert('邮箱格式不正确');
        emailInput.focus();
        return;
    }

    // 禁用按钮并开始倒计时
    sendCodeBtn.disabled = true;
    let countdown = 60;
    sendCodeBtn.textContent = `${countdown}秒后重试`;

    const timer = setInterval(() => {
        countdown--;
        if (countdown > 0) {
            sendCodeBtn.textContent = `${countdown}秒后重试`;
        } else {
            clearInterval(timer);
            sendCodeBtn.disabled = false;
            sendCodeBtn.textContent = '获取验证码';
        }
    }, 1000);

    try {
        // 调用发送验证码API
        const response = await fetch('/api/auth/send-verification-code', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email: email })
        });

        const data = await response.json();

        if (data.success) {
            alert('验证码已发送到您的邮箱，请查收');
        } else {
            alert(data.error || '发送失败，请重试');
            // 如果发送失败，重置按钮
            clearInterval(timer);
            sendCodeBtn.disabled = false;
            sendCodeBtn.textContent = '获取验证码';
        }
    } catch (error) {
        console.error('发送验证码错误:', error);
        alert('网络错误，请检查连接后重试');
        // 发送失败，重置按钮
        clearInterval(timer);
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = '获取验证码';
    }
}


/**
 * 处理登录
 */
async function handleLogin(e) {
    e.preventDefault();

    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const loginBtn = document.getElementById('loginBtn');
    const errorDiv = document.getElementById('login-error');

    // 验证
    if (!username || !password) {
        showError(errorDiv, '请输入用户名和密码');
        return;
    }

    // 禁用按钮
    loginBtn.disabled = true;
    loginBtn.textContent = '登录中...';
    errorDiv.style.display = 'none';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username_or_email: username,
                password: password
            })
        });

        const data = await response.json();

        if (data.success) {
            // 保存token
            if (data.token) {
                sessionStorage.setItem('auth_token', data.token);
            }

            // 跳转到应用
            window.location.href = data.redirect || '/knowledge-base';
        } else {
            showError(errorDiv, data.error || '登录失败，请重试');
            loginBtn.disabled = false;
            loginBtn.textContent = '登录';
        }
    } catch (error) {
        console.error('登录错误:', error);
        showError(errorDiv, '网络错误，请检查连接后重试');
        loginBtn.disabled = false;
        loginBtn.textContent = '登录';
    }
}

/**
 * 处理注册
 */
async function handleRegister(e) {
    e.preventDefault();

    const username = document.getElementById('register-username').value.trim();
    const email = document.getElementById('register-email').value.trim();
    const code = document.getElementById('register-code').value.trim();
    const password = document.getElementById('register-password').value;
    const confirmPassword = document.getElementById('register-confirm').value;
    const agreementCheck = document.getElementById('agreement-check').checked;
    const registerBtn = document.getElementById('registerBtn');
    const errorDiv = document.getElementById('register-error');

    // 验证协议勾选
    if (!agreementCheck) {
        showError(errorDiv, '请先阅读并同意用户协议和隐私政策');
        return;
    }

    // 验证
    if (!username || !email || !code || !password || !confirmPassword) {
        showError(errorDiv, '请填写所有必填项');
        return;
    }

    if (password !== confirmPassword) {
        showError(errorDiv, '两次输入的密码不一致');
        return;
    }

    if (password.length < 8) {
        showError(errorDiv, '密码长度至少为8位');
        return;
    }

    // 邮箱格式验证
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        showError(errorDiv, '邮箱格式不正确');
        return;
    }

    // 禁用按钮
    registerBtn.disabled = true;
    registerBtn.textContent = '注册中...';
    errorDiv.style.display = 'none';

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                email: email,
                verification_code: code,
                password: password
            })
        });

        const data = await response.json();

        if (data.success) {
            // 注册成功，自动登录或跳转到登录页
            if (data.token) {
                sessionStorage.setItem('auth_token', data.token);
                let redirectUrl = data.redirect || '/knowledge-base';
                if (data.bonus_awarded) {
                    redirectUrl += (redirectUrl.includes('?') ? '&' : '?') + 'registration_bonus=true';
                }
                window.location.href = redirectUrl;
            } else {
                // 提示成功并切换到登录
                alert('注册成功！请登录');
                switchToLogin();
                document.getElementById('login-username').value = username;
            }
        } else {
            showError(errorDiv, data.error || '注册失败，请重试');
            registerBtn.disabled = false;
            registerBtn.textContent = '注册';
        }
    } catch (error) {
        console.error('注册错误:', error);
        showError(errorDiv, '网络错误，请检查连接后重试');
        registerBtn.disabled = false;
        registerBtn.textContent = '注册';
    }
}

/**
 * 显示错误消息
 */
function showError(errorDiv, message) {
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';

    // 3秒后自动隐藏
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

// 全局函数供HTML调用
window.togglePassword = togglePassword;

/**
 * 初始化密码实时校验
 */
function initPasswordValidation() {
    const passwordInput = document.getElementById('register-password');
    const requirementsBox = document.getElementById('password-requirements');

    if (!passwordInput || !requirementsBox) return;

    const reqLength = document.getElementById('req-length');
    const reqUppercase = document.getElementById('req-uppercase');
    const reqLowercase = document.getElementById('req-lowercase');
    const reqDigit = document.getElementById('req-digit');
    const reqSpecial = document.getElementById('req-special');

    // 显示校验框
    passwordInput.addEventListener('focus', () => {
        requirementsBox.style.display = 'block';
    });

    // 失去焦点时，如果均符合则隐藏，否则保留提示
    passwordInput.addEventListener('blur', () => {
        if (checkAllValid(passwordInput.value)) {
            requirementsBox.style.display = 'none';
        }
    });

    // 实时输入监听
    passwordInput.addEventListener('input', () => {
        const value = passwordInput.value;

        // 1. 长度校验
        updateRequirement(reqLength, value.length >= 8);

        // 2. 大写字母
        updateRequirement(reqUppercase, /[A-Z]/.test(value));

        // 3. 小写字母
        updateRequirement(reqLowercase, /[a-z]/.test(value));

        // 4. 数字
        updateRequirement(reqDigit, /\d/.test(value));

        // 5. 特殊符号
        updateRequirement(reqSpecial, /[!@#$%^&*(),.?":{}|<>]/.test(value));
    });
}

function checkAllValid(value) {
    const isLengthValid = value.length >= 8;
    const hasUpper = /[A-Z]/.test(value);
    const hasLower = /[a-z]/.test(value);
    const hasDigit = /\d/.test(value);
    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(value);

    return isLengthValid && hasUpper && hasLower && hasDigit && hasSpecial;
}

function updateRequirement(element, isValid) {
    if (!element) return;
    const icon = element.querySelector('.icon');
    if (isValid) {
        element.classList.add('valid');
        element.classList.remove('invalid');
        icon.textContent = '✓';
    } else {
        element.classList.remove('valid');
        icon.textContent = '○';
    }
}
