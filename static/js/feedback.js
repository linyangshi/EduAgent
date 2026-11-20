document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('feedbackForm');
    // Load history
    loadHistory();

    const submitBtn = document.getElementById('submitBtn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Basic validation
        const content = document.getElementById('content').value.trim();
        if (!content) {
            showToast('请填写反馈内容', 'error');
            return;
        }

        // Prepare data
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        // Loading state
        submitBtn.disabled = true;
        submitBtn.textContent = '提交中...';

        try {
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok && result.success) {
                showToast(result.message || '反馈提交成功！', 'success');
                form.reset();
                loadHistory(); // Reload history immediately
                setTimeout(() => {
                    // Start redirect after 1.5s
                    window.location.href = '/app';
                }, 1500);
            } else {
                throw new Error(result.error || '提交失败');
            }
        } catch (error) {
            console.error(error);
            showToast(error.message || '网络错误，请稍后重试', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = '提交反馈';
        }
    });

    async function loadHistory() {
        const listContainer = document.getElementById('feedbackList');
        try {
            const response = await fetch('/api/feedback/history');
            const data = await response.json();

            if (data.success && data.feedbacks) {
                if (data.feedbacks.length === 0) {
                    listContainer.innerHTML = '<div class="no-history">暂无反馈记录</div>';
                    return;
                }

                listContainer.innerHTML = data.feedbacks.map(item => `
                    <div class="history-item">
                        <div class="history-top">
                            <span class="history-type">${getTypeText(item.type)}</span>
                            <span class="history-date">${formatDate(item.created_at)}</span>
                        </div>
                        <div class="history-content">${escapeHtml(item.content)}</div>
                        <div class="history-status status-${item.status}">
                            ${getStatusText(item.status)}
                        </div>
                    </div>
                `).join('');

            } else {
                listContainer.innerHTML = '<div class="loading-history">加载失败</div>';
            }
        } catch (e) {
            console.error(e);
            listContainer.innerHTML = '<div class="loading-history">网络错误</div>';
        }
    }

    function getTypeText(type) {
        const types = {
            'suggestion': '✨ 产品建议',
            'bug': '🐛 程序Bug',
            'other': '📝 其他'
        };
        return types[type] || '其他';
    }

    function getStatusText(status) {
        const statuses = {
            'pending': '待处理',
            'processing': '处理中',
            'resolved': '已处理'
        };
        return statuses[status] || status;
    }

    function formatDate(isoString) {
        const date = new Date(isoString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type}`; // remove hidden, set type

        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }
});
