/**
 * EduAgent Coze Style Frontend Logic
 */

class EduAgentApp {
    constructor() {
        this.currentChatId = null;
        this.isTyping = false;
        this.chatHistory = [];
        this.init();
    }

    init() {
        this.cacheDOM();
        this.bindEvents();
        this.loadHistory();
        this.checkAuth();
        this.checkRegistrationBonus();
    }

    cacheDOM() {
        // Layout Elements
        this.sidebar = document.getElementById('sidebar');
        this.homeView = document.getElementById('home-view');
        this.chatView = document.getElementById('chat-view');

        // Buttons
        this.newTaskBtn = document.getElementById('newTaskBtn');
        this.homeSendBtn = document.getElementById('homeSendBtn');
        this.chatSendBtn = document.getElementById('chatSendBtn');
        this.feedbackBtn = document.querySelector('.floating-feedback-btn') || document.querySelector('.feedback-fab');

        // Inputs
        this.homeInput = document.getElementById('homeInput');
        this.chatInput = document.getElementById('chatInput');

        // Containers
        this.chatMessages = document.getElementById('chatMessages');
        this.historyList = document.getElementById('historyList');
        this.runningStatus = document.getElementById('runningStatus');
        this.suggestedQuestions = document.getElementById('suggestedQuestions');
        this.chatTitle = document.getElementById('chatTitle');
    }

    bindEvents() {
        // New Task
        this.newTaskBtn.addEventListener('click', () => this.resetToHome());

        // Send Buttons
        this.homeSendBtn.addEventListener('click', () => this.handleHomeSend());
        this.chatSendBtn.addEventListener('click', () => this.handleChatSend());

        // Enter Key Handling
        this.homeInput.addEventListener('keydown', (e) => this.handleEnter(e, () => this.handleHomeSend()));
        this.chatInput.addEventListener('keydown', (e) => this.handleEnter(e, () => this.handleChatSend()));

        // Suggestion Chips
        this.suggestedQuestions.addEventListener('click', (e) => {
            if (e.target.classList.contains('suggestion-pill')) {
                this.chatInput.value = e.target.textContent;
                this.handleChatSend();
            }
        });

        // Feedback
        if (this.feedbackBtn) {
            this.feedbackBtn.addEventListener('click', (e) => {
                if (this.feedbackBtn.tagName !== 'A') {
                    e.preventDefault();
                    window.location.href = '/feedback';
                }
            });
        }
    }

    handleEnter(e, callback) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            callback();
        }
    }

    // --- State Management ---

    resetToHome() {
        this.currentChatId = null;
        this.homeView.classList.remove('hidden');
        this.chatView.classList.add('hidden');
        this.homeInput.value = '';
        this.chatInput.value = '';
        this.chatMessages.innerHTML = '';
        this.runningStatus.classList.add('hidden');
        this.suggestedQuestions.classList.add('hidden');
        this.removeActiveHistory();
    }

    switchToChat() {
        this.homeView.classList.add('hidden');
        this.chatView.classList.remove('hidden');
        this.scrollToBottom();
    }

    // --- Message Handling ---

    async handleHomeSend() {
        // Auth check
        const isAuth = await window.authCheck.checkAuth();
        if (!isAuth) {
            window.authCheck.showTopNotification('未登录，请登陆后使用');
            setTimeout(() => {
                localStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
                window.location.href = '/login';
            }, 1500);
            return;
        }

        const text = this.homeInput.value.trim();
        if (!text) return;

        this.switchToChat();

        // Transfer text to chat input context (conceptually) but send immediately
        this.addMessage('user', text);
        this.homeInput.value = '';

        await this.processMessage(text);
    }

    async handleChatSend() {
        // Auth check
        const isAuth = await window.authCheck.checkAuth();
        if (!isAuth) {
            window.authCheck.showTopNotification('未登录，请登陆后使用');
            setTimeout(() => {
                localStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
                window.location.href = '/login';
            }, 1500);
            return;
        }

        const text = this.chatInput.value.trim();
        if (!text || this.isTyping) return;

        this.addMessage('user', text);
        this.chatInput.value = '';

        await this.processMessage(text);
    }

    addMessage(role, content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        // Simple avatar logic matching CSS
        // Unified Avatar Logic
        if (role === 'user') {
            const user = window.currentUser || {};
            if (user.avatar_url) {
                avatar.innerHTML = `<img src="${user.avatar_url}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;" onerror="this.onerror=null; this.parentElement.innerHTML='<div style=\&quot;width:100%;height:100%;border-radius:50%;background:#1677ff;color:white;display:flex;align-items:center;justify-content:center;font-weight:700;\&quot;>${user.initial || '?'}</div>'">`;
            } else {
                avatar.innerHTML = `<div style="width:100%;height:100%;border-radius:50%;background:#1677ff;color:white;display:flex;align-items:center;justify-content:center;font-weight:700;">${user.initial || '?'}</div>`;
            }
        } else {
            // Agent Avatar
            avatar.innerHTML = `<img src="/static/images/favicon.svg" style="width:100%;height:100%;border-radius:4px;object-fit:cover;" >`;
            avatar.style.background = 'transparent';
            avatar.style.border = 'none';
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content';

        if (role === 'assistant') {
            this.renderMarkdown(contentDiv, content);
        } else {
            contentDiv.textContent = content;
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(contentDiv);

        this.chatMessages.appendChild(msgDiv);
        this.scrollToBottom();
        return contentDiv; // Return for streaming updates
    }

    // --- API Interaction ---

    async processMessage(text) {
        this.isTyping = true;
        this.runningStatus.classList.remove('hidden'); // Show "Running..." capsule
        this.suggestedQuestions.classList.add('hidden'); // Hide suggestions while running

        // Disable inputs
        this.chatInput.disabled = true;
        this.chatSendBtn.disabled = true;

        const assistantContentDiv = this.addMessage('assistant', ''); // Empty initially
        let fullText = '';

        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    // Default model, can be made configurable
                    model: 'qwen-max',
                    conversation_id: this.currentChatId
                })
            });

            if (!response.ok) {
                let errorData = {};
                try {
                    errorData = await response.json();
                } catch (e) { }

                const error = new Error(errorData.error || 'API Error');
                error.cause = errorData; // Attach full error data
                throw error;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));

                            if (data.conversation_id) {
                                this.currentChatId = data.conversation_id;
                                this.refreshHistory(); // Refresh history if new chat
                            }

                            if (data.chunk) {
                                fullText += data.chunk;
                                // Simple <think> tag cleaning matching user preference
                                let displayText = fullText.replace(/<think>[\s\S]*?<\/think>/g, '');
                                this.renderMarkdown(assistantContentDiv, displayText);
                                this.scrollToBottom();
                            }
                        } catch (e) {
                            // JSON parse error for partial chunks is common, ignore
                        }
                    }
                }
            }

        } catch (error) {
            assistantContentDiv.innerHTML = `<span style="color:red">Error: ${error.message}</span>`;

            // Handle insufficient points
            if (error.cause && error.cause.code === 'INSUFFICIENT_POINTS') {
                if (confirm('积分不足，请先充值。是否前往充值页面？')) {
                    window.location.href = '/shop';
                }
            }
        } finally {
            this.isTyping = false;
            this.runningStatus.classList.add('hidden'); // Hide status
            this.suggestedQuestions.classList.remove('hidden'); // Show suggestions

            this.chatInput.disabled = false;
            this.chatSendBtn.disabled = false;
            this.chatInput.focus();
        }
    }

    // --- Helpers ---

    renderMarkdown(target, text) {
        if (window.marked) {
            target.innerHTML = marked.parse(text);
        } else {
            target.textContent = text;
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // --- History Management ---

    async loadHistory() {
        try {
            const res = await fetch('/api/conversations');
            const data = await res.json();
            if (data.success) {
                this.chatHistory = data.conversations;
                this.renderHistory();
            }
        } catch (e) { console.error(e); }
    }

    refreshHistory() {
        // Debounce or simple call
        this.loadHistory();
    }

    renderHistory() {
        this.historyList.innerHTML = '';
        this.chatHistory.forEach(chat => {
            const item = document.createElement('div');
            item.className = 'history-item';

            if (chat.id === this.currentChatId) item.classList.add('active');
            item.onclick = () => this.loadConversation(chat.id);

            // Title
            const titleSpan = document.createElement('span');
            titleSpan.className = 'history-title';
            titleSpan.textContent = chat.title || '无标题对话';
            item.appendChild(titleSpan);

            // Delete Button
            const deleteBtn = document.createElement('div');
            deleteBtn.className = 'delete-chat-btn';
            deleteBtn.innerHTML = '×'; // Simple cross or use SVG
            deleteBtn.title = '删除对话';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                if (confirm('确定要删除这个对话吗？')) {
                    this.deleteConversation(chat.id);
                }
            };
            item.appendChild(deleteBtn);

            this.historyList.appendChild(item);
        });
    }

    async deleteConversation(id) {
        try {
            const res = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                // Remove from local array
                this.chatHistory = this.chatHistory.filter(c => c.id !== id);
                this.renderHistory();

                // If current chat was deleted, reset
                if (this.currentChatId === id) {
                    this.resetToHome();
                }
            } else {
                alert(data.error || '删除失败');
            }
        } catch (e) {
            console.error(e);
            alert('删除失败，请重试');
        }
    }

    removeActiveHistory() {
        const active = this.historyList.querySelector('.active');
        if (active) active.classList.remove('active');
    }

    async loadConversation(id) {
        if (this.currentChatId === id) return;

        try {
            const res = await fetch(`/api/conversations/${id}`);
            const data = await res.json();

            if (data.success) {
                this.currentChatId = id;
                this.chatTitle.textContent = data.title || '历史对话';

                this.switchToChat();
                this.chatMessages.innerHTML = '';

                // Re-render history to update active state
                this.renderHistory();

                data.messages.forEach(msg => {
                    this.addMessage(msg.role, msg.content);
                });

                // Show input area, assume ready
                this.runningStatus.classList.add('hidden');
                this.suggestedQuestions.classList.remove('hidden'); // Assume suggested questions for history too
            }
        } catch (e) { console.error(e); }
    }

    async checkAuth() {
        // Simple auth check to get avatar if possible
        // Relying on template rendered user info for now in sidebar
        // But we can fetch /api/auth/status if needed
    }

    checkRegistrationBonus() {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('registration_bonus') === 'true') {
            // Remove param clean
            const newUrl = window.location.pathname;
            window.history.replaceState({}, document.title, newUrl);

            // Inject Styles for Animation
            if (!document.getElementById('bonus-styles')) {
                const style = document.createElement('style');
                style.id = 'bonus-styles';
                style.textContent = `
                    @keyframes bonusOverlayIn {
                        from { opacity: 0; backdrop-filter: blur(0px); }
                        to { opacity: 1; backdrop-filter: blur(8px); }
                    }
                    @keyframes bonusModalIn {
                        0% { opacity: 0; transform: scale(0.9) translateY(20px); }
                        60% { opacity: 1; transform: scale(1.02) translateY(0); }
                        100% { transform: scale(1) translateY(0); }
                    }
                    @keyframes bonusFadeOut {
                        from { opacity: 1; transform: scale(1); }
                        to { opacity: 0; transform: scale(0.95); }
                    }
                    .bonus-overlay {
                        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                        background-color: rgba(0,0,0,0.6);
                        display: flex; justify-content: center; align-items: center;
                        z-index: 9999;
                        animation: bonusOverlayIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
                    }
                    .bonus-modal {
                        background: radial-gradient(circle at top right, #ffffff, #f8f9fa);
                        padding: 40px 32px;
                        border-radius: 24px;
                        width: 90%; max-width: 420px;
                        text-align: center;
                        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25), 
                                    0 0 0 1px rgba(255, 255, 255, 0.5) inset;
                        animation: bonusModalIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
                    }
                    .bonus-emoji {
                        font-size: 64px; margin-bottom: 20px;
                        animation: float 3s ease-in-out infinite;
                        text-shadow: 0 10px 20px rgba(0,0,0,0.1);
                    }
                    @keyframes float {
                        0%, 100% { transform: translateY(0); }
                        50% { transform: translateY(-10px); }
                    }
                    .bonus-btn {
                        background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
                        color: white; border: none; border-radius: 12px;
                        padding: 14px 40px; font-size: 16px; font-weight: 600;
                        cursor: pointer;
                        box-shadow: 0 10px 25px -5px rgba(124, 58, 237, 0.5);
                        transition: all 0.2s ease;
                        margin-top: 10px;
                    }
                    .bonus-btn:hover {
                        transform: translateY(-2px) scale(1.02);
                        box-shadow: 0 15px 30px -5px rgba(124, 58, 237, 0.6);
                    }
                    .bonus-btn:active {
                        transform: translateY(1px) scale(0.98);
                    }
                    .bonus-out {
                        animation: bonusFadeOut 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards !important;
                        pointer-events: none;
                    }
                `;
                document.head.appendChild(style);
            }

            // Create Elements
            const overlay = document.createElement('div');
            overlay.className = 'bonus-overlay';

            const modal = document.createElement('div');
            modal.className = 'bonus-modal';

            const emoji = document.createElement('div');
            emoji.className = 'bonus-emoji';
            emoji.textContent = '🎁';

            const title = document.createElement('h2');
            title.textContent = '欢迎加入 EduAgent';
            Object.assign(title.style, {
                fontSize: '26px', fontWeight: '700', marginBottom: '12px',
                color: '#1a1a1a', letterSpacing: '-0.5px'
            });

            const text = document.createElement('p');
            text.innerHTML = '注册成功！已为您赠送 <span style="color:#7c3aed; font-weight:700; font-size:1.1em">300</span> 积分体验金<br>快来体验强大的AI功能吧！';
            Object.assign(text.style, {
                fontSize: '16px', lineHeight: '1.6', color: '#4b5563', marginBottom: '28px'
            });

            const btn = document.createElement('button');
            btn.className = 'bonus-btn';
            btn.textContent = '开始体验';

            // Close Handler - 跳转到知识库页面
            const close = () => {
                overlay.classList.add('bonus-out');
                // Wait for animation then redirect to knowledge base
                setTimeout(() => {
                    window.location.href = '/knowledge-base';
                }, 300);
            };

            btn.onclick = close;
            overlay.onclick = (e) => {
                if (e.target === overlay) close();
            }

            modal.appendChild(emoji);
            modal.appendChild(title);
            modal.appendChild(text);
            modal.appendChild(btn);
            overlay.appendChild(modal);
            document.body.appendChild(overlay);
        }
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.app = new EduAgentApp();
});
