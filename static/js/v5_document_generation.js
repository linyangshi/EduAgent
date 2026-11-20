/**
 * V5智能文档生成 - 前端逻辑
 * V5 Document Generation - Frontend Logic
 */

class V5DocumentGenerator {
    constructor() {
        this.apiBaseUrl = window.location.origin + '/api';
        this.uploadedFile = null;
        this.taskId = null;
        this.progressTimer = null;
        this.generatedFilePath = null;
        this.lastPrompt = '';
        this.selectedModel = 'qwen-flash';  // 默认选择通义千问 Flash

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupDragAndDrop();
        this.checkAuth();
        this.hideResultSection();
        this.resetProgressUI();
    }

    checkAuth() {
        return !!this.getAuthToken();
    }

    getAuthToken() {
        return (
            sessionStorage.getItem('auth_token') ||
            sessionStorage.getItem('access_token') ||
            localStorage.getItem('token') ||
            localStorage.getItem('access_token') ||
            ''
        );
    }

    getAuthHeaders(extraHeaders = {}) {
        const authToken = this.getAuthToken();
        if (!authToken) {
            return extraHeaders;
        }

        return {
            ...extraHeaders,
            'Authorization': `Bearer ${authToken}`
        };
    }

    // 统一处理API响应，检查401未授权
    async handleResponse(response) {
        if (response.status === 401) {
            alert('登录已过期，请重新登录');
            sessionStorage.removeItem('auth_token');
            sessionStorage.removeItem('access_token');
            window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname);
            throw new Error('Unauthorized');
        }
        return response;
    }

    setupEventListeners() {
        // 文件上传
        const fileInput = document.getElementById('fileInput');
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                this.handleFileUpload(e.target.files[0]);
            }
        });

        // 清除已上传文件
        const clearFileBtn = document.getElementById('clearFileBtn');
        if (clearFileBtn) {
            clearFileBtn.addEventListener('click', () => this.clearUploadedFile());
        }

        // 再次生成
        const regenerateBtn = document.getElementById('regenerateBtn');
        if (regenerateBtn) {
            regenerateBtn.addEventListener('click', () => this.openRegenerateModal());
        }

        // Prompt输入
        const promptInput = document.getElementById('promptInput');
        promptInput.addEventListener('input', () => {
            this.autoResizeTextarea(promptInput);
        });

        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendPrompt();
            }
        });

        // 发送按钮
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.addEventListener('click', () => this.sendPrompt());

        // 下载按钮
        const downloadBtn = document.getElementById('downloadBtn');
        downloadBtn.addEventListener('click', () => this.downloadDocument());
    }

    setupDragAndDrop() {
        const uploadArea = document.getElementById('uploadArea');

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        uploadArea.addEventListener('dragenter', () => {
            uploadArea.style.borderColor = '#667eea';
            uploadArea.style.background = '#f3f4f6';
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.style.borderColor = '#d1d5db';
            uploadArea.style.background = '#f9fafb';
        });

        uploadArea.addEventListener('drop', (e) => {
            uploadArea.style.borderColor = '#d1d5db';
            uploadArea.style.background = '#f9fafb';

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileUpload(files[0]);
            }
        });
    }

    prepareForNewRun() {
        this.clearProgressTimer();
        this.resetProgressUI();
        this.hideResultSection();
        this.generatedFilePath = null;
        this.taskId = null;
        this.displayProgress = 0;
        this.targetProgress = 0;
        const progressSection = document.getElementById('progressSection');
        if (progressSection) progressSection.classList.add('active');
    }

    clearUploadedFile() {
        this.clearProgressTimer();
        this.uploadedFile = null;
        this.generatedFilePath = null;
        this.lastPrompt = '';
        this.taskId = null;
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        this.updateUploadStatus('idle');
        this.disablePromptInput();
        this.resetProgressUI();
        this.hideResultSection();
    }

    openRegenerateModal() {
        if (!this.uploadedFile) {
            this.showError('请先上传模板文件');
            return;
        }

        // 显示上传和模型选择区域
        const uploadSection = document.querySelector('.upload-section');
        const modelSection = document.querySelector('.model-section');
        if (uploadSection) {
            uploadSection.classList.remove('hidden');
        }
        if (modelSection) {
            modelSection.classList.remove('hidden');
        }

        // 隐藏结果区域
        this.hideResultSection();

        // 启用输入框并聚焦
        const promptInput = document.getElementById('promptInput');
        const sendBtn = document.getElementById('sendBtn');
        if (promptInput) {
            promptInput.disabled = false;
            promptInput.value = '';
            promptInput.focus();
            promptInput.placeholder = '请输入新的需求说明，继续使用已上传的模板生成...';
        }
        if (sendBtn) {
            sendBtn.disabled = false;
        }

        // 滚动到输入区域
        const inputSection = document.querySelector('.input-section');
        if (inputSection) {
            inputSection.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
    }

    closeRegenerateModal() {
        // 不再需要模态对话框
    }

    confirmRegenerate() {
        // 不再需要模态对话框
    }

    clearProgressAnim() {
        // 兼容旧逻辑，当前版本直接使用真实进度，不再单独维护动画定时器。
    }

    async handleFileUpload(file) {
        // 验证文件类型（支持 .doc 和 .docx）
        const fileName = file.name.toLowerCase();
        if (!fileName.endsWith('.docx') && !fileName.endsWith('.doc')) {
            this.showError('请上传 .doc 或 .docx 格式的文件');
            return;
        }

        // 验证文件大小 (最大20MB)
        if (file.size > 20 * 1024 * 1024) {
            this.showError('文件大小不能超过 20MB');
            return;
        }

        // 显示上传中状态
        this.updateUploadStatus('uploading', file.name);

        try {
            const formData = new FormData();
            formData.append('file', file);

            let response = await fetch(`${this.apiBaseUrl}/v5/upload-template`, {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: formData
            });
            response = await this.handleResponse(response);

            const data = await response.json();

            if (data.success) {
                this.uploadedFile = {
                    name: data.file_name,  // 使用服务器返回的文件名（可能已转换）
                    path: data.file_path,
                    size: file.size
                };
                this.updateUploadStatus('success', data.file_name);
                this.enablePromptInput();

                // 根据是否转换显示不同的消息
                let message = `✅ 模板上传成功！文件名：${data.file_name}`;
                if (data.converted) {
                    message += '\n\n📝 已自动将 .doc 格式转换为 .docx 格式';
                }
                message += '\n\n现在请告诉我您的需求，我会基于这个模板为您生成文档。';

                this.addMessage('assistant', message);
            } else {
                this.showError(data.error || '文件上传失败');
                this.updateUploadStatus('idle');
            }
        } catch (error) {
            console.error('Upload error:', error);
            this.showError('文件上传失败，请重试');
            this.updateUploadStatus('idle');
        }
    }

    updateUploadStatus(status, fileName = '') {
        const uploadArea = document.getElementById('uploadArea');
        const uploadIcon = document.getElementById('uploadIcon');
        const uploadText = document.getElementById('uploadText');
        const fileInfo = document.getElementById('fileInfo');
        const fileNameSpan = document.getElementById('fileName');

        switch (status) {
            case 'idle':
                uploadArea.classList.remove('has-file');
                uploadIcon.textContent = '📄';
                uploadText.textContent = '点击或拖拽上传DOCX模板';
                fileInfo.style.display = 'none';
                this.hideResultSection();
                this.resetProgressUI();
                this.displayProgress = 0;
                this.targetProgress = 0;
                break;

            case 'uploading':
                uploadIcon.textContent = '⏳';
                uploadText.textContent = '上传中...';
                break;

            case 'success':
                uploadArea.classList.add('has-file');
                uploadIcon.textContent = '✅';
                uploadText.textContent = '模板已上传';
                fileNameSpan.textContent = fileName;
                fileInfo.style.display = 'flex';
                break;
        }
    }

    enablePromptInput() {
        const promptInput = document.getElementById('promptInput');
        const sendBtn = document.getElementById('sendBtn');

        if (promptInput) promptInput.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        if (promptInput) promptInput.focus();
    }

    async sendPrompt() {
        const promptInput = document.getElementById('promptInput');
        const prompt = promptInput.value.trim();

        if (!prompt) {
            this.showError('请输入您的需求描述');
            return;
        }

        if (!this.uploadedFile) {
            this.showError('请先上传模板文件');
            return;
        }

        // 添加用户消息
        this.addMessage('user', prompt);
        promptInput.value = '';
        this.autoResizeTextarea(promptInput);
        this.lastPrompt = prompt;
        this.prepareForNewRun();

        // 禁用输入
        promptInput.disabled = true;
        document.getElementById('sendBtn').disabled = true;

        // 添加加载消息
        this.addMessage('assistant', '正在启动V5文档生成流程...');

        try {
            let response = await fetch(`${this.apiBaseUrl}/v5/generate`, {
                method: 'POST',
                headers: this.getAuthHeaders({
                    'Content-Type': 'application/json',
                }),
                body: JSON.stringify({
                    file_path: this.uploadedFile.path,
                    prompt: prompt,
                    mode: 'inference',  // 使用推理模式（不做VLM检查，更快）
                    model: this.selectedModel  // 用户选择的模型：qwen-flash/qwen-plus/kimi/gemini
                })
            });
            response = await this.handleResponse(response);

            const data = await response.json();

            if (data.success) {
                this.taskId = data.task_id;
                this.addMessage('assistant', `✅ 任务已创建（ID: ${this.taskId}）\n\n开始生成文档，请稍候...`);
                this.startProgressMonitoring();
            } else {
                this.showError(data.error || '启动生成失败');
                this.enablePromptInput();
            }
        } catch (error) {
            console.error('Generation error:', error);
            this.showError('启动生成失败，请重试');
            this.enablePromptInput();
        }
    }

    startProgressMonitoring() {
        // 显示进度区域
        const progressSection = document.getElementById('progressSection');
        if (!progressSection) {
            console.error('❌ 找不到进度条元素 #progressSection');
            this.showError('进度条初始化失败');
            return;
        }

        progressSection.classList.add('active');
        console.log('✅ 进度监控已启动，任务ID:', this.taskId);
        this.clearProgressTimer();

        // 定期查询进度
        this.progressTimer = setInterval(() => {
            this.checkProgress();
        }, 1000);  // 每1秒查询一次，进度更顺滑

        // 立即执行一次进度查询
        this.checkProgress();
    }

    async checkProgress() {
        if (!this.taskId) {
            console.warn('⚠️ checkProgress: 没有任务ID');
            return;
        }

        try {
            const url = `${this.apiBaseUrl}/v5/progress/${this.taskId}`;
            console.log(`📡 查询进度: ${url}`);

            let response = await fetch(url, {
                headers: this.getAuthHeaders()
            });
            response = await this.handleResponse(response);

            if (!response.ok) {
                console.error(`❌ 进度查询失败: ${response.status} ${response.statusText}`);
                if (response.status === 404) {
                    this.clearProgressTimer();
                    this.handleGenerationFailed('任务不存在或已过期，请重新发起生成');
                }
                return;
            }

            const data = await response.json();
            console.log('📊 进度数据:', data);

            if (data.success) {
                this.updateProgress(data.progress, data.status, data.message);

                if (data.status === 'completed') {
                    clearInterval(this.progressTimer);
                    this.handleGenerationComplete(data);
                } else if (data.status === 'failed') {
                    clearInterval(this.progressTimer);
                    this.handleGenerationFailed(data.error);
                }
            } else {
                console.error('❌ 进度查询返回失败:', data);
            }
        } catch (error) {
            console.error('❌ 进度查询异常:', error);
            // 不要停止定时器，继续尝试
        }
    }

    updateProgress(progress, status, message) {
        console.log(`📈 更新进度: ${progress}% - ${status}`);

        const progressFill = document.getElementById('progressFill');
        const progressStatus = document.getElementById('progressStatus');

        if (!progressFill || !progressStatus) {
            console.error('❌ 找不到进度条元素');
            return;
        }

        const normalizedProgress = Number.isFinite(Number(progress))
            ? Math.max(0, Math.min(100, Number(progress)))
            : 0;
        const fallbackStatusText = status === 'completed'
            ? '生成完成'
            : status === 'failed'
                ? '生成失败'
                : '处理中';
        const progressText = message || fallbackStatusText;

        progressFill.style.width = `${normalizedProgress}%`;
        progressStatus.textContent = `${normalizedProgress}% · ${progressText}`;
    }


    handleGenerationComplete(data) {
        const progressSection = document.getElementById('progressSection');
        const resultSection = document.getElementById('resultSection');

        // 隐藏进度，显示结果
        progressSection.classList.remove('active');
        resultSection.classList.add('active');

        // 保存生成文件路径
        this.generatedFilePath = data.file_path;
        this.showResultSection();

        // 添加成功消息
        const warningText = data.error ? `\n\n提示：${data.error}` : '';
        this.addMessage('assistant', `🎉 文档生成完成！\n\n文件名：${data.file_name}\n\n点击下方按钮下载文档。${warningText}`);
        this.enablePromptInput();
    }

    handleGenerationFailed(error) {
        const progressSection = document.getElementById('progressSection');
        progressSection.classList.remove('active');

        this.showError(`生成失败：${error}`);
        this.addMessage('assistant', `❌ 生成失败：${error}\n\n请检查模板和需求描述后重试。`);
        this.enablePromptInput();
    }

    async downloadDocument() {
        if (!this.generatedFilePath) {
            this.showError('没有可下载的文件');
            return;
        }

        try {
            const downloadUrl = `${this.apiBaseUrl}/v5/download?file_path=${encodeURIComponent(this.generatedFilePath)}`;
            let response = await fetch(downloadUrl, {
                headers: this.getAuthHeaders()
            });
            response = await this.handleResponse(response);

            if (!response.ok) {
                throw new Error('下载请求失败');
            }

            const blob = await response.blob();
            const objectUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = this.generatedFilePath.split('/').pop() || 'generated.docx';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(objectUrl);

            this.addMessage('assistant', '📥 文档下载已开始...');
        } catch (error) {
            console.error('Download error:', error);
            this.showError('下载失败，请重试');
        }
    }

    addMessage(role, content) {
        const chatMessages = document.getElementById('chatMessages');

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = content;

        const time = document.createElement('div');
        time.className = 'message-time';
        time.textContent = new Date().toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
        });

        messageDiv.appendChild(bubble);
        messageDiv.appendChild(time);
        chatMessages.appendChild(messageDiv);

        // 滚动到底部
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    hideResultSection() {
        const resultSection = document.getElementById('resultSection');
        if (resultSection) {
            resultSection.classList.remove('active');
        }
    }

    showResultSection() {
        const resultSection = document.getElementById('resultSection');
        const uploadSection = document.querySelector('.upload-section');
        const modelSection = document.querySelector('.model-section');

        if (resultSection) {
            resultSection.classList.add('active');
            // 确保按钮可见，滚动到结果区域
            resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        // 隐藏上传和模型选择区域
        if (uploadSection) {
            uploadSection.classList.add('hidden');
        }
        if (modelSection) {
            modelSection.classList.add('hidden');
        }
    }

    resetProgressUI() {
        const progressSection = document.getElementById('progressSection');
        const progressFill = document.getElementById('progressFill');
        const progressStatus = document.getElementById('progressStatus');
        const progressLog = document.getElementById('progressLog');
        if (progressSection) progressSection.classList.remove('active');
        if (progressFill) progressFill.style.width = '0%';
        if (progressStatus) progressStatus.textContent = '0%';
        if (progressLog) {
            progressLog.innerHTML = '';
            progressLog.style.display = 'none';
        }
    }

    clearProgressTimer() {
        if (this.progressTimer) {
            clearInterval(this.progressTimer);
            this.progressTimer = null;
        }
    }


    disablePromptInput() {
        const promptInput = document.getElementById('promptInput');
        const sendBtn = document.getElementById('sendBtn');
        if (promptInput) promptInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
    }

    showError(message) {
        const errorDiv = document.getElementById('errorMessage');
        if (!errorDiv) {
            return;
        }
        errorDiv.textContent = '❌ ' + message;
        errorDiv.classList.add('active');

        setTimeout(() => {
            errorDiv.classList.remove('active');
        }, 5000);
    }

    autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }
}

// 重置生成（全局函数，供HTML调用）
function resetGeneration() {
    if (confirm('确定要重置并开始新的生成吗？')) {
        // 显示上传和模型选择区域
        const uploadSection = document.querySelector('.upload-section');
        const modelSection = document.querySelector('.model-section');
        if (uploadSection) {
            uploadSection.classList.remove('hidden');
        }
        if (modelSection) {
            modelSection.classList.remove('hidden');
        }

        window.location.reload();
    }
}

// 模型选择（全局函数，供HTML调用）
function selectModel(modelType) {
    // 更新选中状态
    const modelOptions = document.querySelectorAll('.model-option');
    modelOptions.forEach(option => {
        option.classList.remove('selected');
    });

    let selectedOption;
    let modelName;

    if (modelType === 'qwen-flash') {
        selectedOption = document.querySelector('label[for="modelQwenFlash"]');
        modelName = 'DocuMind Mini';
    } else if (modelType === 'qwen-plus') {
        selectedOption = document.querySelector('label[for="modelQwenPlus"]');
        modelName = 'DocuMind Flash';
    } else if (modelType === 'kimi') {
        selectedOption = document.querySelector('label[for="modelKimi"]');
        modelName = 'DocuMind Pro';
    } else if (modelType === 'gpt') {
        selectedOption = document.querySelector('label[for="modelGPT"]');
        modelName = 'DocuMind GPT';
    }

    if (selectedOption) {
        selectedOption.classList.add('selected');
    }

    // 更新generator实例的selectedModel
    if (window.v5Generator) {
        window.v5Generator.selectedModel = modelType;
        console.log(`✅ 模型已切换至: ${modelName}`);
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.v5Generator = new V5DocumentGenerator();
});
