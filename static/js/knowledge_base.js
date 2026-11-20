/**
 * 知识库问答系统JavaScript
 * Knowledge Base Q&A System JavaScript
 */

// 全局变量
let files = [];
let isLoading = false;
let currentUser = null; // 当前用户信息
let kbId = null; // 知识库ID
let kbInfo = null; // 知识库信息

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    initKnowledgeBase();
});

/**
 * 初始化知识库功能
 */
async function initKnowledgeBase() {
    // 获取知识库ID
    kbId = window.KB_ID;

    if (!kbId) {
        alert('知识库ID不存在，将跳转到知识库管理页面');
        window.location.href = '/knowledge-base';
        return;
    }

    // 获取当前用户信息
    await loadCurrentUser();

    // 加载知识库信息
    await loadKnowledgeBaseInfo();

    // 初始化上传功能
    initUpload();

    // 初始化聊天功能
    initChat();

    // 加载文件列表和统计信息
    await loadStats();
    await loadFiles();
}

/**
 * 加载知识库信息
 */
async function loadKnowledgeBaseInfo() {
    try {
        const response = await fetch(`/api/kb/${kbId}`);
        const result = await response.json();

        if (result.success) {
            kbInfo = result.kb;
            
            // 更新页面标题和描述
            const nameElement = document.getElementById('kbName');
            if (nameElement) {
                nameElement.textContent = kbInfo.name || '未命名知识库';
            }
            
            const descElement = document.getElementById('kbDescription');
            if (descElement) {
                descElement.textContent = kbInfo.description || '暂无描述';
            }
            
            // 可以在页面标题中显示知识库名称
            document.title = `${kbInfo.name} - 知识库 - EduAgent智教创想`;
        }
    } catch (error) {
        console.error('加载知识库信息失败:', error);
    }
}

/**
 * 加载当前用户信息
 */
async function loadCurrentUser() {
    try {
        const authToken = sessionStorage.getItem('auth_token');
        if (!authToken) {
            return;
        }

        const response = await fetch('/api/auth/verify', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const result = await response.json();

        if (result.success && result.valid) {
            currentUser = result.user;
        }
    } catch (error) {
        console.error('加载用户信息失败:', error);
    }
}

// 监听头像更新事件（从个人资料页面触发）
window.addEventListener('avatarUpdated', (event) => {
    if (event.detail && event.detail.avatar_url) {
        console.log('收到头像更新事件:', event.detail.avatar_url);
        if (currentUser) {
            currentUser.avatar_url = event.detail.avatar_url;
            // 更新所有现有消息中的用户头像
            updateAllUserAvatars();
        }
    }
});

/**
 * 更新所有消息中的用户头像
 */
function updateAllUserAvatars() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) {
        return;
    }

    const userMessages = chatMessages.querySelectorAll('.message.user');
    userMessages.forEach(messageElement => {
        const avatar = messageElement.querySelector('.message-avatar');
        if (avatar && currentUser) {
            // 清空现有内容
            avatar.innerHTML = '';

            if (currentUser.avatar_url) {
                const img = document.createElement('img');
                img.src = currentUser.avatar_url;
                img.alt = '用户头像';
                img.className = 'avatar-image';
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.objectFit = 'cover';
                img.style.borderRadius = '50%';

                // 添加加载错误处理
                img.onerror = () => {
                    avatar.innerHTML = '';
                    const firstLetter = currentUser.username.charAt(0).toUpperCase();
                    avatar.textContent = firstLetter;
                    avatar.style.background = '#1677ff';
                    avatar.style.color = 'white';
                    avatar.style.display = 'flex';
                    avatar.style.alignItems = 'center';
                    avatar.style.justifyContent = 'center';
                    avatar.style.fontWeight = '700';
                };

                avatar.appendChild(img);
            } else if (currentUser.username) {
                const firstLetter = currentUser.username.charAt(0).toUpperCase();
                avatar.textContent = firstLetter;
                avatar.style.background = '#1677ff';
                avatar.style.color = 'white';
                avatar.style.display = 'flex';
                avatar.style.alignItems = 'center';
                avatar.style.justifyContent = 'center';
                avatar.style.fontWeight = '700';
            } else {
                avatar.textContent = '👤';
            }
        }
    });
}

/**
 * 初始化文件上传功能
 */
function initUpload() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');

    // 如果不是管理者，跳过上传初始化
    if (!uploadBox || !fileInput) return;

    // 点击上传
    uploadBox.addEventListener('click', () => {
        fileInput.click();
    });

    // 拖拽上传
    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.classList.add('dragover');
    });

    uploadBox.addEventListener('dragleave', () => {
        uploadBox.classList.remove('dragover');
    });

    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('dragover');

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length > 0) {
            handleFileUpload(Array.from(droppedFiles));
        }
    });

    // 文件选择
    fileInput.addEventListener('change', (e) => {
        const selectedFiles = e.target.files;
        if (selectedFiles.length > 0) {
            handleFileUpload(Array.from(selectedFiles));
        }
        // 重置input，允许重复选择同一文件
        e.target.value = '';
    });
}

/**
 * 处理文件上传
 */
async function handleFileUpload(fileList) {
    const uploadProgress = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    // 过滤非PDF文件
    const pdfFiles = fileList.filter(file => file.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length < fileList.length) {
        alert('部分文件格式不正确，仅支持上传 PDF 格式文件。');
    }
    
    if (pdfFiles.length === 0) return;

    // 显示进度条
    uploadProgress.style.display = 'block';
    progressFill.style.width = '0%';

    try {
        for (let i = 0; i < pdfFiles.length; i++) {
            const file = pdfFiles[i];
            progressText.textContent = `正在上传 ${i + 1}/${pdfFiles.length}: ${file.name}`;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('kb_id', kbId);

            const response = await fetch('/api/kb/upload', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            });

            const result = await response.json();

            if (result.success) {
                console.log(`✅ 文件上传成功: ${file.name}`);
                // 刷新文件列表
                await loadFiles();
                await loadStats();
            } else {
                console.error(`❌ 文件上传失败: ${result.error}`);
                if (!checkServiceError(result)) {
                    alert(`上传失败: ${result.error}`);
                }
            }

            progressFill.style.width = `${((i + 1) / fileList.length) * 100}%`;
        }

        progressText.textContent = '上传完成！';
        setTimeout(() => {
            uploadProgress.style.display = 'none';
        }, 2000);

    } catch (error) {
        console.error('上传错误:', error);
        alert(`上传失败: ${error.message}`);
        uploadProgress.style.display = 'none';
    }
}

/**
 * 加载文件列表
 */
async function loadFiles() {
    try {
        const response = await fetch(`/api/kb/files?kb_id=${kbId}`);
        const result = await response.json();

        if (result.success) {
            files = result.files;
            renderFileList();
        } else {
            checkServiceError(result);
        }
    } catch (error) {
        console.error('加载文件列表失败:', error);
    }
}

/**
 * 渲染文件列表
 */
function renderFileList() {
    const fileList = document.getElementById('fileList');

    if (files.length === 0) {
        fileList.innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 2rem;">暂无文档</div>';
        return;
    }

    fileList.innerHTML = files.map(file => {
        const uploadTime = new Date(file.uploaded_at).toLocaleString('zh-CN');
        return `
            <div class="file-item">
                <div class="file-info">
                    <div class="file-name">${file.file_name}</div>
                    <div class="file-meta">
                        ${formatFileSize(file.file_size)} • ${file.chunk_count} 个知识块 • ${uploadTime}
                    </div>
                </div>
                ${window.CAN_MANAGE ? `<button class="file-delete" onclick="deleteFile('${file.file_id}')">删除</button>` : ''}
            </div>
        `;
    }).join('');
}

/**
 * 删除文件
 */
async function deleteFile(fileId) {
    if (!confirm('确定要删除这个文件吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/kb/files/${fileId}?kb_id=${kbId}`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });

        const result = await response.json();

        if (result.success) {
            console.log('✅ 文件删除成功');
            await loadFiles();
            await loadStats();
        } else {
            alert(`删除失败: ${result.error}`);
        }
    } catch (error) {
        console.error('删除失败:', error);
        alert(`删除失败: ${error.message}`);
    }
}

/**
 * 加载统计信息
 */
async function loadStats() {
    try {
        const response = await fetch(`/api/kb/stats?kb_id=${kbId}`);
        const result = await response.json();

        if (result.success) {
            document.getElementById('fileCount').textContent = result.file_count;
            document.getElementById('chunkCount').textContent = result.stats.total_chunks;

            // Display Billing Status
            if (result.billing_status) {
                const status = result.billing_status;
                const size = status.total_size_mb;
                let tip = '';
                let color = '#666';

                if (size <= 20) {
                    tip = `🟢 小知识库 (<20MB): 免费`;
                } else if (size <= 100) {
                    const remaining = Math.max(0, 2 - status.daily_medium_count);
                    tip = `🟡 中型知识库 (${size}MB): 今日免费 ${remaining}/2 次 (超额10积分)`;
                    color = remaining > 0 ? '#10a37f' : '#f59e0b';
                } else {
                    const remaining = Math.max(0, 1 - status.daily_large_count);
                    tip = `🔴 大型知识库 (${size}MB): 今日免费 ${remaining}/1 次 (超额20积分)`;
                    color = remaining > 0 ? '#10a37f' : '#ef4444';
                }

                // Inspect if we have a place to put this. If not, create one in the header.
                let billingDiv = document.getElementById('kbBillingStatus');
                if (!billingDiv) {
                    const headerState = document.querySelector('.kb-stats');
                    billingDiv = document.createElement('div');
                    billingDiv.id = 'kbBillingStatus';
                    billingDiv.className = 'stat-item';
                    billingDiv.style.borderLeft = '1px solid rgba(0,0,0,0.1)';
                    billingDiv.style.paddingLeft = '2rem';
                    billingDiv.style.textAlign = 'left';
                    headerState.appendChild(billingDiv);
                }

                billingDiv.innerHTML = `
                    <div class="stat-value" style="font-size:1rem; color:${color}; margin-bottom:4px;">${size} MB</div>
                    <div class="stat-label" style="font-size:0.75rem;">${tip}</div>
                `;
            }
        } else {
            checkServiceError(result);
        }
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

/**
 * 初始化聊天功能
 */
function initChat() {
    const questionInput = document.getElementById('questionInput');
    const sendButton = document.getElementById('sendButton');

    // 发送按钮点击
    sendButton.addEventListener('click', handleSendQuestion);

    // 回车发送
    questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendQuestion();
        }
    });

    // 自动调整输入框高度（限制最大高度）
    questionInput.addEventListener('input', () => {
        questionInput.style.height = 'auto';
        const maxHeight = 150; // 最大高度150px，超过后显示滚动条
        if (questionInput.scrollHeight <= maxHeight) {
            questionInput.style.height = questionInput.scrollHeight + 'px';
        } else {
            questionInput.style.height = maxHeight + 'px';
            questionInput.style.overflowY = 'auto';
        }
    });

    // 初始化输入框样式
    questionInput.style.overflowY = 'hidden';
    questionInput.style.resize = 'none';
}

/**
 * 发送问题
 */
async function handleSendQuestion() {
    const questionInput = document.getElementById('questionInput');
    const sendButton = document.getElementById('sendButton');
    const question = questionInput.value.trim();

    if (!question || isLoading) {
        return;
    }

    // 禁用输入
    isLoading = true;
    sendButton.disabled = true;
    questionInput.disabled = true;

    // 显示用户消息
    addMessage('user', question);

    // 清空输入框
    questionInput.value = '';
    questionInput.style.height = 'auto';

    // 开始计时
    const startTime = Date.now();

    // 显示加载状态
    const loadingId = addMessage('assistant', '正在思考...', true);

    try {
        // 根据当前标签页选择不同的API端点
        const apiEndpoint = currentTab === 'screenshots' ? '/api/qa/answer' : '/api/kb/ask';
        const authToken = sessionStorage.getItem('auth_token');

        // 获取选中的模型和直接回答选项
        const modelSelect = document.getElementById('modelSelect');
        const selectedModel = modelSelect ? modelSelect.value : 'qwen-plus';
        
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`,
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ kb_id: kbId, question, top_k: 5, model: selectedModel })
        });

        const result = await response.json();

        if (result.success) {
            if (result.status === 'processing' && result.message_id) {
                // 进入异步轮询模式
                pollKBMessageStatus(result.message_id, loadingId, startTime, result.billing_info);
                return;
            }

            // 同步模式（截图问答或旧版兼容）
            setTimeout(() => {
                removeMessage(loadingId);
            }, 50);

            // 检查答案是否为空或不完整
            let answer = '';

            if (currentTab === 'screenshots') {
                // 截图问答模式 - 显示候选答案列表
                if (result.found && result.candidates && result.candidates.length > 0) {
                    // 找到匹配答案，显示最佳答案 + 候选列表
                    const bestMatch = result.candidates[0];
                    answer = `<div style="margin-bottom: 1rem;">
                        <div style="font-weight: 600; color: #10a37f; margin-bottom: 0.5rem;">✅ 最佳答案（相似度: ${(bestMatch.similarity * 100).toFixed(1)}%）</div>
                        <div style="background: #f0fdf4; padding: 0.75rem; border-radius: 0.5rem; border-left: 3px solid #10a37f;">
                            ${escapeHtml(bestMatch.answer)}
                        </div>
                        <div style="margin-top: 0.5rem; font-size: 0.85rem; color: #6b7280;">
                            匹配问题: ${escapeHtml(bestMatch.question)}
                        </div>
                    </div>`;

                    // 显示其他候选答案（如果有）
                    if (result.candidates.length > 1) {
                        answer += `<div style="margin-top: 1.5rem; border-top: 1px solid #e5e7eb; padding-top: 1rem;">
                            <div style="font-weight: 600; color: #6b7280; margin-bottom: 0.75rem;">📋 其他相关答案</div>`;

                        for (let i = 1; i < result.candidates.length; i++) {
                            const candidate = result.candidates[i];
                            answer += `<div style="margin-bottom: 1rem; padding: 0.75rem; background: #f9fafb; border-radius: 0.5rem; border: 1px solid #e5e7eb;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                    <span style="font-weight: 600; color: #374151;">候选 ${i + 1}</span>
                                    <span style="font-size: 0.85rem; color: #6b7280;">相似度: ${(candidate.similarity * 100).toFixed(1)}%</span>
                                </div>
                                <div style="font-size: 0.9rem; color: #4b5563; margin-bottom: 0.5rem;">
                                    <strong>问:</strong> ${escapeHtml(candidate.question)}
                                </div>
                                <div style="font-size: 0.9rem; color: #374151;">
                                    <strong>答:</strong> ${escapeHtml(candidate.answer)}
                                </div>
                            </div>`;
                        }
                        answer += `</div>`;
                    }
                } else if (!result.found && result.candidates && result.candidates.length > 0) {
                    // 未找到足够匹配的答案，但有候选
                    answer = `<div style="color: #d97706; margin-bottom: 1rem;">
                        ${result.answer || '未找到完全匹配的答案'}
                    </div>`;

                    answer += `<div style="margin-top: 1rem;">
                        <div style="font-weight: 600; color: #6b7280; margin-bottom: 0.75rem;">📋 可能相关的问答</div>`;

                    for (let i = 0; i < result.candidates.length; i++) {
                        const candidate = result.candidates[i];
                        answer += `<div style="margin-bottom: 1rem; padding: 0.75rem; background: #fffbeb; border-radius: 0.5rem; border: 1px solid #fcd34d;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                <span style="font-weight: 600; color: #92400e;">候选 ${i + 1}</span>
                                <span style="font-size: 0.85rem; color: #92400e;">相似度: ${(candidate.similarity * 100).toFixed(1)}%</span>
                            </div>
                            <div style="font-size: 0.9rem; color: #78350f; margin-bottom: 0.5rem;">
                                <strong>问:</strong> ${escapeHtml(candidate.question)}
                            </div>
                            <div style="font-size: 0.9rem; color: #92400e;">
                                <strong>答:</strong> ${escapeHtml(candidate.answer)}
                            </div>
                        </div>`;
                    }
                    answer += `</div>`;
                } else {
                    answer = result.answer || '未找到相关问答';
                }
            } else {
                // 文档问答模式
                answer = result.answer && result.answer.trim() ? result.answer.trim() : '抱歉，未能生成完整的答案。';
            }

            // Check Billing Info
            if (result.billing_info) {
                const b = result.billing_info;
                let billHtml = '';
                if (b.is_free) {
                    billHtml = `<div style="font-size:12px; color:#10a37f; margin-top:8px; padding-top:8px; border-top:1px dashed #eee;">
                        ✨ ${b.message} (当前KB大小: ${b.kb_size_mb}MB)
                    </div>`;
                } else {
                    billHtml = `<div style="font-size:12px; color:#f59e0b; margin-top:8px; padding-top:8px; border-top:1px dashed #eee;">
                        💎 ${b.message} (已扣除 ${b.points_deducted} 积分)
                    </div>`;
                }
                answer += billHtml;
                loadStats();
            }

            // 计算思考用时
            const thinkingDuration = (Date.now() - startTime) / 1000;

            // 设置全局变量启用打字动画
            window._useTypingAnimation = true;
            window._thinkingDuration = thinkingDuration;

            // 添加消息（会触发打字动画）
            const msgId = addMessage('assistant', answer, false);

            // 获取消息容器并启动打字动画
            setTimeout(async () => {
                const msgElement = document.getElementById(msgId);
                if (msgElement) {
                    const messageText = msgElement.querySelector('.message-text[data-pending-animation="true"]');
                    if (messageText) {
                        const content = messageText.getAttribute('data-content');
                        const duration = parseFloat(messageText.getAttribute('data-duration'));
                        messageText.removeAttribute('data-pending-animation');
                        messageText.removeAttribute('data-content');
                        messageText.removeAttribute('data-duration');

                        // 启动打字动画
                        await typeWriterEffect(messageText, content, duration);
                    }
                }
                // 重置全局变量
                window._useTypingAnimation = false;
                window._thinkingDuration = undefined;
            }, 100);
        } else {
            setTimeout(() => {
                removeMessage(loadingId);
            }, 50);
            if (!checkServiceError(result)) {
                addMessage('assistant', `抱歉，出现问题：${result.error || '未知错误'}`, false);
            }
        }
    } catch (error) {
        console.error('发送问题失败:', error);
        // 确保移除加载消息
        setTimeout(() => {
            removeMessage(loadingId);
        }, 50);
        addMessage('assistant', `抱歉，网络出现问题：${error.message}`, false);
    } finally {
        // 如果是同步模式或者是报错，恢复输入
        // 异步模式在轮询结束后恢复
        if (!result || (result.status !== 'processing')) {
            isLoading = false;
            sendButton.disabled = false;
            questionInput.disabled = false;
            questionInput.focus();
            
            // 确保滚动到底部
            const chatMessages = document.getElementById('chatMessages');
            setTimeout(() => {
                chatMessages.scrollTo({
                    top: chatMessages.scrollHeight,
                    behavior: 'smooth'
                });
            }, 100);
        }
    }
}

/**
 * 轮询知识库消息状态
 */
async function pollKBMessageStatus(msgId, loadingId, startTime, billingInfo) {
    const authToken = sessionStorage.getItem('auth_token');
    const sendButton = document.getElementById('sendButton');
    const questionInput = document.getElementById('questionInput');
    
    // 设置最大重试时间（120秒）
    const maxRetries = 120; // 改为120因为现在有1秒的短轮询
    let retries = 0;
    
    // 初始化轮询间隔 (前5次1秒，之后2秒)
    let pollInterval = 1000;
    
    // 用于保存流式输出ID，以便持续更新而不是每次创建新消息
    let currentStreamMsgId = null;
    
    const poll = async () => {
        try {
            retries++;
            if (retries > maxRetries) {
                removeMessage(loadingId);
                addMessage('assistant', '回答生成超时，请稍后在历史记录中查看。', false);
                isLoading = false;
                sendButton.disabled = false;
                questionInput.disabled = false;
                return;
            }

            const response = await fetch(`/api/kb/message_status/${msgId}`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            const msg = await response.json();
            
            // 处理流式输出 (状态为 processing 但已经有内容)
            if (msg.status === 'processing' && msg.content) {
                // 如果这是第一次收到内容，移除原有的等待动画
                removeMessage(loadingId);
                
                let partialAnswer = msg.content;
                
                // 暂时不附加计费信息，等 completed 再加
                
                if (!currentStreamMsgId) {
                    // 全新消息
                    const thinkingDuration = (Date.now() - startTime) / 1000;
                    window._useTypingAnimation = false; // 流式不需要打字动画了，因为已经是逐步出来的
                    
                    // 如果存在，移除之前的部分生成消息，避免重复
                    currentStreamMsgId = addMessage('assistant', partialAnswer + '...', false);
                } else {
                    // 更新现有消息的内容
                    updateMessageContent(currentStreamMsgId, partialAnswer + '...');
                }
            }
            
            if (msg.status === 'completed') {
                removeMessage(loadingId); // 确保等待动画被移除
                
                let answer = msg.content || '';
                
                // 附加计费信息
                if (billingInfo) {
                    const b = billingInfo;
                    let billHtml = '';
                    if (b.is_free) {
                        billHtml = `<div style="font-size:12px; color:#10a37f; margin-top:8px; padding-top:8px; border-top:1px dashed #eee;">
                            ✨ ${b.message} (当前KB大小: ${b.kb_size_mb}MB)
                        </div>`;
                    } else {
                        billHtml = `<div style="font-size:12px; color:#f59e0b; margin-top:8px; padding-top:8px; border-top:1px dashed #eee;">
                            💎 ${b.message} (已扣除 ${b.points_deducted} 积分)
                        </div>`;
                    }
                    answer += billHtml;
                }
                
                const thinkingDuration = (Date.now() - startTime) / 1000;
                
                // 如果之前有流式的ID，更新它并去掉省略号；否则创建新消息
                if (currentStreamMsgId) {
                    // 如果已经使用了局部更新，我们可以使用局部渲染
                    updateMessageContent(currentStreamMsgId, answer);
                    // 重新触发打字机或渲染（可选择性不触发，因为已经流式出来了）
                    const msgElement = document.getElementById(currentStreamMsgId);
                    if (msgElement) {
                         const messageText = msgElement.querySelector('.message-text');
                         if (messageText) {
                             messageText.innerHTML = renderThinkingContent(answer, thinkingDuration);
                         }
                    }
                } else {
                    window._useTypingAnimation = true;
                    window._thinkingDuration = thinkingDuration;
                    
                    const finalMsgId = addMessage('assistant', answer, false);
                    
                    setTimeout(async () => {
                        const msgElement = document.getElementById(finalMsgId);
                        if (msgElement) {
                            const messageText = msgElement.querySelector('.message-text[data-pending-animation="true"]');
                            if (messageText) {
                                const content = messageText.getAttribute('data-content');
                                const duration = parseFloat(messageText.getAttribute('data-duration'));
                                messageText.removeAttribute('data-pending-animation');
                                messageText.removeAttribute('data-content');
                                messageText.removeAttribute('data-duration');
                                await typeWriterEffect(messageText, content, duration);
                            }
                        }
                        window._useTypingAnimation = false;
                        window._thinkingDuration = undefined;
                    }, 100);
                }
                
                isLoading = false;
                sendButton.disabled = false;
                questionInput.disabled = false;
                loadStats();
                
            } else if (msg.status === 'error') {
                removeMessage(loadingId);
                if (currentStreamMsgId) {
                    updateMessageContent(currentStreamMsgId, `生成失败: ${msg.content || '未知错误'}`);
                } else {
                    addMessage('assistant', `生成失败: ${msg.content || '未知错误'}`, false);
                }
                isLoading = false;
                sendButton.disabled = false;
                questionInput.disabled = false;
            } else {
                // processing 继续轮询
                if (retries === 5) { // 5次之后，增加轮询间隔
                    pollInterval = 2000;
                }
                setTimeout(poll, pollInterval);
            }
        } catch (err) {
            console.error('Polling error:', err);
             // 出错也继续尝试
            setTimeout(poll, pollInterval);
        }
    };
    
    // 启动初始轮询
    setTimeout(poll, pollInterval);
}

/**
 * 更新现有消息的内容 (用于流式输出)
 */
function updateMessageContent(messageId, newContent) {
    const msgDiv = document.getElementById(messageId);
    if (!msgDiv) return;
    
    const msgText = msgDiv.querySelector('.message-text');
    if (!msgText) return;
    
    // 直接渲染新内容 (不带动画)
    msgText.innerHTML = renderThinkingContent(newContent, 0);
    
    // 滚动到底部
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'auto' // 流式更新频繁，用auto比smooth更好
        });
    }
}

/**
 * 添加消息到聊天窗口
 */
function addMessage(type, content, isLoading = false) {
    const chatMessages = document.getElementById('chatMessages');

    // 移除空状态提示
    const emptyState = chatMessages.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // 转换为智能对话模式的角色名称
    const role = type === 'ai' ? 'assistant' : type;

    // 如果是AI回答（非加载状态），先移除所有加载中的消息，避免重复
    if (role === 'assistant' && !isLoading) {
        removeAllLoadingMessages();
    }

    // 使用更唯一的ID（时间戳 + 随机数）
    const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

    // 创建消息DOM元素
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.id = messageId;

    // 创建头像
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';

    if (role === 'assistant') {
        // AI助手头像使用图片
        const img = document.createElement('img');
        img.src = '/static/images/favicon.svg';
        img.alt = 'AI助手';
        img.className = 'avatar-image';
        avatar.appendChild(img);
    } else {
        // 用户头像（使用智能问答逻辑）
        if (currentUser && currentUser.avatar_url) {
            const img = document.createElement('img');
            img.src = currentUser.avatar_url;
            img.alt = '用户头像';
            img.className = 'avatar-image';
            img.style.width = '100%';
            img.style.height = '100%';
            img.style.objectFit = 'cover';
            img.style.borderRadius = '50%';

            // 添加加载错误处理，如果图片加载失败则显示用户名首字母
            img.onerror = () => {
                avatar.innerHTML = '';
                const firstLetter = currentUser.username.charAt(0).toUpperCase();
                avatar.textContent = firstLetter;
                avatar.style.background = '#1677ff';
                avatar.style.color = 'white';
                avatar.style.display = 'flex';
                avatar.style.alignItems = 'center';
                avatar.style.justifyContent = 'center';
                avatar.style.fontWeight = '700';
            };

            avatar.appendChild(img);
        } else if (currentUser) {
            // 显示用户名首字母 + 渐变背景
            const firstLetter = currentUser.username.charAt(0).toUpperCase();
            avatar.textContent = firstLetter;
            avatar.style.background = '#1677ff';
            avatar.style.color = 'white';
            avatar.style.display = 'flex';
            avatar.style.alignItems = 'center';
            avatar.style.justifyContent = 'center';
            avatar.style.fontWeight = '700';
        } else {
            avatar.textContent = '👤';
        }
    }

    // 创建消息内容
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    const messageText = document.createElement('div');
    messageText.className = 'message-text';
    if (isLoading) {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'loading-dots';
        loadingDiv.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
        messageText.appendChild(loadingDiv);
    } else if (role === 'assistant') {
        // 检查是否需要打字动画（通过全局变量控制）
        if (window._useTypingAnimation && window._thinkingDuration !== undefined) {
            // 先添加空容器，后续通过打字动画填充
            messageText.setAttribute('data-pending-animation', 'true');
            messageText.setAttribute('data-content', content);
            messageText.setAttribute('data-duration', window._thinkingDuration);
        } else {
            // 直接渲染
            messageText.innerHTML = renderThinkingContent(content, 0);
        }
    } else {
        messageText.textContent = content;
    }


    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = timeStr;

    messageContent.appendChild(messageText);
    messageContent.appendChild(messageTime);

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(messageContent);

    chatMessages.appendChild(messageDiv);

    // 平滑滚动到底部
    setTimeout(() => {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);

    return messageId;
}

/**
 * 移除消息
 */
function removeMessage(messageId) {
    if (!messageId) {
        // 如果没有指定ID，移除所有加载中的消息
        removeAllLoadingMessages();
        return;
    }

    // 尝试多种方式移除消息，确保可靠
    const message = document.getElementById(messageId);
    if (message) {
        message.remove();
    } else {
        // 如果找不到指定ID的消息，尝试移除所有加载中的消息
        removeAllLoadingMessages();
    }
}

/**
 * 移除所有加载中的消息
 */
function removeAllLoadingMessages() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) {
        return;
    }

    // 查找所有包含加载动画的AI消息
    const loadingMessages = chatMessages.querySelectorAll('.message.assistant');
    loadingMessages.forEach(messageElement => {
        const loading = messageElement.querySelector('.loading, .loading-dots');
        const content = messageElement.textContent || '';
        // 如果包含加载动画或者内容是"正在思考..."
        if (loading || content.includes('正在思考')) {
            messageElement.remove();
        }
    });
}

/**
 * 工具函数：获取CSRF Token
 */
function getCSRFToken() {
    // 从cookie中获取CSRF token
    const name = 'csrf_token';
    const value = '; ' + document.cookie;
    const parts = value.split('; ' + name + '=');
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

/**
 * 工具函数：格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * 工具函数：HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function containsHtml(content) {
    if (!content) {
        return false;
    }
    return /<\/?[a-z][\s\S]*?>/i.test(content);
}

function normalizeMarkdown(content) {
    if (!content) {
        return '';
    }
    let text = content.replace(/\r\n/g, '\n');
    text = text
        .replace(/\s*```/g, '\n```')
        .replace(/```\s*/g, '```\n')
        .replace(/\n{3,}/g, '\n\n');

    const newlineCount = (text.match(/\n/g) || []).length;
    if (newlineCount < 2) {
        text = text
            .replace(/([^\n])(\s*#{1,6}\s+)/g, '$1\n$2')
            .replace(/([^\n])(\s*[-*•]\s+)/g, '$1\n$2')
            .replace(/([^\n])(\s*\d+\.\s+)/g, '$1\n$2')
            .replace(/([。！？!?;；:])\s+/g, '$1\n');
    }
    return text.trim();
}

/**
 * 解析带有思考过程的AI回答
 * 识别 -thinking- 标记，分离思考内容和正式回答
 * @param {string} content - 原始回答内容
 * @returns {object} - { hasThinking: boolean, thinking: string, answer: string }
 */
function parseThinkingContent(content) {
    if (!content) {
        return { hasThinking: false, thinking: '', answer: '' };
    }

    // 尝试多种匹配方式
    // 方式1: 标准格式 -thinking- ... ✅ 回答
    let thinkingMatch = content.match(/^-thinking-\s*\n?([\s\S]*?)(?:\n\n+)?✅\s*回答\s*\n?([\s\S]*)$/i);
    if (thinkingMatch) {
        return {
            hasThinking: true,
            thinking: thinkingMatch[1].trim(),
            answer: thinkingMatch[2].trim()
        };
    }

    // 方式2: 只有 ✅ 回答 标记（可能思考部分被省略或格式不同）
    let answerOnlyMatch = content.match(/^✅\s*回答\s*\n?([\s\S]*)$/i);
    if (answerOnlyMatch) {
        return {
            hasThinking: false,
            thinking: '',
            answer: answerOnlyMatch[1].trim()
        };
    }

    // 方式3: 宽松匹配 -thinking- 开头
    if (content.trim().startsWith('-thinking-')) {
        const answerIdx = content.indexOf('✅');
        if (answerIdx > 0) {
            const thinkingPart = content.substring('-thinking-'.length, answerIdx);
            const answerPart = content.substring(answerIdx);
            const answerContent = answerPart.replace(/^✅\s*回答\s*\n?/i, '');
            return {
                hasThinking: true,
                thinking: thinkingPart.trim(),
                answer: answerContent.trim()
            };
        }
    }

    return { hasThinking: false, thinking: '', answer: content };
}

/**
 * 渲染带有思考过程的消息内容（支持可折叠和用时显示）
 * @param {string} content - 原始内容
 * @param {number} thinkingDuration - 思考用时（秒）
 * @returns {string} - 格式化后的HTML
 */
function renderThinkingContent(content, thinkingDuration = 0) {
    const parsed = parseThinkingContent(content);

    // 辅助函数：渲染Markdown
    function renderMarkdown(text) {
        if (!text) return '';
        const normalized = normalizeMarkdown(text);
        if (window.marked) {
            try {
                return marked.parse(normalized);
            } catch (e) {
                console.error('Marked.js解析错误:', e);
                return escapeHtml(normalized).replace(/\n/g, '<br>');
            }
        }
        return escapeHtml(normalized).replace(/\n/g, '<br>');
    }

    // 格式化用时
    function formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds.toFixed(1)}秒`;
        } else {
            const minutes = Math.floor(seconds / 60);
            const secs = (seconds % 60).toFixed(0);
            return `${minutes}分${secs}秒`;
        }
    }

    // 生成唯一ID
    const uniqueId = 'thinking_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    // 没有思考过程标记，直接渲染全部内容
    if (!parsed.hasThinking && !parsed.answer.startsWith('###') && !parsed.answer.includes('**')) {
        return renderMarkdown(content);
    }

    // 有思考过程，分块渲染（可折叠）
    if (parsed.hasThinking && parsed.thinking) {
        const thinkingHtml = renderMarkdown(parsed.thinking);
        const answerHtml = renderMarkdown(parsed.answer);
        const durationText = thinkingDuration > 0 ? formatDuration(thinkingDuration) : '';

        return `
            <div class="kb-thinking-section kb-collapsible" id="${uniqueId}">
                <div class="kb-thinking-header kb-toggle-header" onclick="toggleThinkingSection('${uniqueId}')">
                    <span class="kb-thinking-icon">💭</span>
                    <span class="kb-thinking-title">思考过程</span>
                    ${durationText ? `<span class="kb-thinking-duration">用时 ${durationText}</span>` : ''}
                    <span class="kb-toggle-icon">▼</span>
                </div>
                <div class="kb-thinking-content kb-collapsible-content">
                    ${thinkingHtml}
                </div>
            </div>
            <div class="kb-answer-section">
                <div class="kb-answer-header">
                    <span class="kb-answer-icon">✅</span>
                    <span class="kb-answer-title">回答</span>
                </div>
                <div class="kb-answer-content">
                    ${answerHtml}
                </div>
            </div>
        `;
    }

    // 只有回答部分
    const answerHtml = renderMarkdown(parsed.answer || content);
    return `
        <div class="kb-answer-section">
            <div class="kb-answer-header">
                <span class="kb-answer-icon">✅</span>
                <span class="kb-answer-title">回答</span>
            </div>
            <div class="kb-answer-content">
                ${answerHtml}
            </div>
        </div>
    `;
}

/**
 * 切换思考过程的展开/折叠状态
 */
function toggleThinkingSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;

    section.classList.toggle('kb-collapsed');
    const icon = section.querySelector('.kb-toggle-icon');
    if (icon) {
        icon.textContent = section.classList.contains('kb-collapsed') ? '▶' : '▼';
    }
}

/**
 * 打字动画效果 - 逐字显示内容
 * @param {HTMLElement} container - 容器元素
 * @param {string} content - 原始内容
 * @param {number} thinkingDuration - 思考用时（秒）
 * @param {function} onComplete - 完成回调
 */
async function typeWriterEffect(container, content, thinkingDuration, onComplete) {
    const parsed = parseThinkingContent(content);
    const CHAR_DELAY = 15; // 每个字符的延迟（毫秒）

    // 辅助函数：渲染Markdown
    function renderMarkdown(text) {
        if (!text) return '';
        const normalized = normalizeMarkdown(text);
        if (window.marked) {
            try {
                return marked.parse(normalized);
            } catch (e) {
                return escapeHtml(normalized).replace(/\n/g, '<br>');
            }
        }
        return escapeHtml(normalized).replace(/\n/g, '<br>');
    }

    // 格式化用时
    function formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds.toFixed(1)}秒`;
        } else {
            const minutes = Math.floor(seconds / 60);
            const secs = (seconds % 60).toFixed(0);
            return `${minutes}分${secs}秒`;
        }
    }

    const uniqueId = 'thinking_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    // 如果有思考过程
    if (parsed.hasThinking && parsed.thinking) {
        const durationText = thinkingDuration > 0 ? formatDuration(thinkingDuration) : '';

        // 先创建结构
        container.innerHTML = `
            <div class="kb-thinking-section kb-collapsible" id="${uniqueId}">
                <div class="kb-thinking-header kb-toggle-header" onclick="toggleThinkingSection('${uniqueId}')">
                    <span class="kb-thinking-icon">💭</span>
                    <span class="kb-thinking-title">思考过程</span>
                    ${durationText ? `<span class="kb-thinking-duration">用时 ${durationText}</span>` : ''}
                    <span class="kb-toggle-icon">▼</span>
                </div>
                <div class="kb-thinking-content kb-collapsible-content" id="${uniqueId}_content"></div>
            </div>
            <div class="kb-answer-section">
                <div class="kb-answer-header">
                    <span class="kb-answer-icon">✅</span>
                    <span class="kb-answer-title">回答</span>
                </div>
                <div class="kb-answer-content" id="${uniqueId}_answer"></div>
            </div>
        `;

        const thinkingContent = document.getElementById(`${uniqueId}_content`);
        const answerContent = document.getElementById(`${uniqueId}_answer`);

        // 打字效果 - 思考过程
        await typeText(thinkingContent, parsed.thinking, CHAR_DELAY);

        // 打字效果 - 回答
        await typeText(answerContent, parsed.answer, CHAR_DELAY);

        // 完成后折叠思考过程
        setTimeout(() => {
            const section = document.getElementById(uniqueId);
            if (section) {
                section.classList.add('kb-collapsed');
                const icon = section.querySelector('.kb-toggle-icon');
                if (icon) icon.textContent = '▶';
            }
        }, 500);

    } else {
        // 只有回答
        container.innerHTML = `
            <div class="kb-answer-section">
                <div class="kb-answer-header">
                    <span class="kb-answer-icon">✅</span>
                    <span class="kb-answer-title">回答</span>
                </div>
                <div class="kb-answer-content" id="${uniqueId}_answer"></div>
            </div>
        `;

        const answerContent = document.getElementById(`${uniqueId}_answer`);
        await typeText(answerContent, parsed.answer || content, CHAR_DELAY);
    }

    if (onComplete) onComplete();
}

/**
 * 逐字打字效果（带Markdown渲染）
 */
async function typeText(container, text, charDelay) {
    if (!container || !text) return;

    const normalized = normalizeMarkdown(text);
    const chars = [...normalized]; // 支持中文字符
    let currentText = '';

    for (let i = 0; i < chars.length; i++) {
        currentText += chars[i];

        // 每10个字符渲染一次Markdown（优化性能）
        if (i % 10 === 0 || i === chars.length - 1) {
            if (window.marked) {
                try {
                    container.innerHTML = marked.parse(currentText);
                } catch (e) {
                    container.textContent = currentText;
                }
            } else {
                container.textContent = currentText;
            }

            // 滚动到底部
            const chatMessages = document.getElementById('chatMessages');
            if (chatMessages) {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }

        // 延迟
        await new Promise(resolve => setTimeout(resolve, charDelay));
    }

    // 最终渲染
    if (window.marked) {
        try {
            container.innerHTML = marked.parse(normalized);
        } catch (e) {
            container.textContent = normalized;
        }
    }
}

/**
 * 工具函数：防抖
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==================== 截图问答功能 ====================

let screenshots = [];
let currentTab = 'documents'; // 当前标签页

// ==================== 错误处理与服务重置 ====================

function checkServiceError(result) {
    if (result && result.error && (typeof result.error === 'string') &&
        (result.error.includes('未初始化') || result.error.includes('初始化失败'))) {
        showReinitOption(result.error);
        return true;
    }
    return false;
}

function showReinitOption(errorMsg) {
    // 避免重复显示
    if (document.getElementById('serviceErrorBanner')) return;

    const container = document.querySelector('.kb-container');
    if (!container) return;

    const banner = document.createElement('div');
    banner.id = 'serviceErrorBanner';
    banner.style.cssText = 'background: #fee2e2; color: #b91c1c; padding: 1rem; text-align: center; position: absolute; top: 0; left: 0; right: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; gap: 1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);';
    banner.innerHTML = `
    < span style = "display:flex;align-items:center;gap:0.5rem" >⚠️ <strong>服务异常</strong>: ${errorMsg.substring(0, 100)}${errorMsg.length > 100 ? '...' : ''}</span >
        <button onclick="window.reinitService()" style="background: #dc2626; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.25rem; cursor: pointer; font-weight: 600;">🛠️ 尝试修复</button>
        <button onclick="this.parentElement.remove()" style="background: white; border: 1px solid #b91c1c; color: #b91c1c; padding: 0.5rem; border-radius: 0.25rem; cursor: pointer;">✕</button>
`;

    // 插入到标题栏下方
    const header = container.querySelector('.kb-header');
    if (header && header.nextSibling) {
        container.insertBefore(banner, header.nextSibling);
    } else {
        container.prepend(banner);
    }
}

window.reinitService = async function () {
    if (!confirm('确定要尝试重新初始化服务吗？\n这会尝试重新连接数据库和加载模型，可能会花费几秒钟。')) return;

    const btn = document.querySelector('#serviceErrorBanner button');
    if (btn) {
        btn.textContent = '⏳处理中...';
        btn.disabled = true;
    }

    try {
        const authToken = sessionStorage.getItem('auth_token');
        const response = await fetch('/api/kb/reinit', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Authorization': `Bearer ${authToken} `
            }
        });
        const result = await response.json();

        if (result.success) {
            alert('✅ 服务修复成功！页面将刷新。');
            window.location.reload();
        } else {
            alert('❌ 修复失败: ' + (result.details || result.error || '未知错误'));
            if (btn) {
                btn.textContent = '重试失败';
                btn.disabled = false;
            }
        }
    } catch (e) {
        alert('❌ 请求失败: ' + e);
        if (btn) {
            btn.textContent = '请求错误';
            btn.disabled = false;
        }
    }
};

function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            switchTab(tabName);
        });
    });

    // 初始化截图上传功能
    initScreenshotUpload();
}

/**
 * 切换标签页
 */
function switchTab(tabName) {
    currentTab = tabName;

    // 更新按钮状态
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });

    // 更新内容显示
    document.getElementById('documentsTab').classList.remove('active');
    document.getElementById('screenshotsTab').classList.remove('active');

    if (tabName === 'documents') {
        document.getElementById('documentsTab').classList.add('active');
    } else if (tabName === 'screenshots') {
        document.getElementById('screenshotsTab').classList.add('active');
        // 加载截图列表
        loadScreenshots();
        loadQAStats();
    }
}

/**
 * 初始化截图上传功能
 */
function initScreenshotUpload() {
    const screenshotUploadBox = document.getElementById('screenshotUploadBox');
    const screenshotInput = document.getElementById('screenshotInput');

    if (!screenshotUploadBox || !screenshotInput) return;

    // 点击上传区域
    screenshotUploadBox.addEventListener('click', () => {
        screenshotInput.click();
    });

    // 文件选择
    screenshotInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            uploadScreenshot(files[0]);
        }
    });

    // 拖拽上传
    screenshotUploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        screenshotUploadBox.style.borderColor = '#667eea';
        screenshotUploadBox.style.background = '#f5f7ff';
    });

    screenshotUploadBox.addEventListener('dragleave', (e) => {
        e.preventDefault();
        screenshotUploadBox.style.borderColor = '#d1d5db';
        screenshotUploadBox.style.background = '';
    });

    screenshotUploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        screenshotUploadBox.style.borderColor = '#d1d5db';
        screenshotUploadBox.style.background = '';

        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('image/')) {
            uploadScreenshot(files[0]);
        } else {
            alert('请上传图片文件');
        }
    });
}

/**
 * 上传截图
 */
async function uploadScreenshot(file) {
    const progressDiv = document.getElementById('screenshotProgress');
    const progressFill = document.getElementById('screenshotProgressFill');
    const progressText = document.getElementById('screenshotProgressText');

    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = '正在上传截图...';

    try {
        const formData = new FormData();
        formData.append('kb_id', kbId);
        formData.append('screenshot', file);

        const authToken = sessionStorage.getItem('auth_token');

        progressFill.style.width = '30%';
        progressText.textContent = '正在分析截图...';

        const response = await fetch('/api/qa/upload-screenshot', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken} `
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            progressFill.style.width = '100%';
            progressText.textContent = `成功！提取到${result.qa_count} 个问答对`;

            // 显示提取结果
            if (result.qa_pairs && result.qa_pairs.length > 0) {
                showQAExtractionResult(result);
            }

            // 重新加载截图列表
            setTimeout(() => {
                loadScreenshots();
                loadQAStats();
                progressDiv.style.display = 'none';
                // 清空input
                document.getElementById('screenshotInput').value = '';
            }, 2000);
        } else {
            throw new Error(result.error || '上传失败');
        }
    } catch (error) {
        console.error('上传截图失败:', error);
        progressText.textContent = '上传失败: ' + error.message;
        setTimeout(() => {
            progressDiv.style.display = 'none';
        }, 3000);
    }
}

/**
 * 显示问答对提取结果
 */
function showQAExtractionResult(result) {
    const chatMessages = document.getElementById('chatMessages');

    // 清除空状态
    const emptyState = chatMessages.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    // 添加系统消息
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
    < div class="message-avatar" >🤖</div >
        <div class="message-content">
            <div class="message-text">
                <strong>截图上传成功！</strong><br><br>
                    已从截图中提取到 <strong>${result.qa_count}</strong> 个问答对：<br><br>
                        ${result.qa_pairs.slice(0, 3).map((qa, idx) => `
                    <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: #f3f4f6; border-radius: 0.5rem;">
                        <div style="font-weight: 600; color: #667eea;">问题 ${idx + 1}:</div>
                        <div style="margin: 0.25rem 0;">${escapeHtml(qa.question)}</div>
                        <div style="font-weight: 600; color: #10a37f; margin-top: 0.5rem;">答案:</div>
                        <div>${escapeHtml(qa.answer.substring(0, 100))}${qa.answer.length > 100 ? '...' : ''}</div>
                    </div>
                `).join('')}
                        ${result.qa_count > 3 ? `<div style="color: #6b7280; font-size: 0.9rem;">还有 ${result.qa_count - 3} 个问答对...</div>` : ''}
                    </div>
                        <div class="message-time">${new Date().toLocaleString()}</div>
                    </div>
                    `;

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * 加载截图列表
 */
async function loadScreenshots() {
    try {
        const authToken = sessionStorage.getItem('auth_token');
        const response = await fetch(`/api/qa/screenshots?kb_id=${kbId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const result = await response.json();

        if (result.success) {
            screenshots = result.screenshots;
            renderScreenshots();
        }
    } catch (error) {
        console.error('加载截图列表失败:', error);
    }
}

/**
 * 渲染截图列表
 */
function renderScreenshots() {
    const screenshotList = document.getElementById('screenshotList');

    if (screenshots.length === 0) {
        screenshotList.innerHTML = '<div style="text-align: center; padding: 2rem; color: #9ca3af;">暂无截图，请上传截图提取问答对</div>';
        return;
    }

    screenshotList.innerHTML = screenshots.map(screenshot => `
                    <div class="file-item" style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border: 1px solid #e5e7eb; border-radius: 0.5rem; margin-bottom: 0.5rem;">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-weight: 500; margin-bottom: 0.25rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${screenshot.screenshot_name}">
                                📸 ${screenshot.screenshot_name}
                            </div>
                            <div style="font-size: 0.75rem; color: #6b7280;">
                                ${screenshot.qa_count} 个问答对
                                ${screenshot.split_count > 1 ? ` · ${screenshot.split_count}个片段` : ''}
                            </div>
                            <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">
                                ${new Date(screenshot.uploaded_at).toLocaleString()}
                            </div>
                        </div>
                        <button
                            class="file-delete"
                            onclick="deleteScreenshot('${screenshot.screenshot_id}')"
                            style="margin-left: 0.5rem; padding: 0.375rem 0.75rem; background: #fee2e2; color: #dc2626; border: none; border-radius: 0.375rem; cursor: pointer; font-size: 0.8rem;"
                        >
                            删除
                        </button>
                    </div>
                    `).join('');
}

/**
 * 删除截图
 */
async function deleteScreenshot(screenshotId) {
    if (!confirm('确定要删除这个截图及其所有问答对吗？')) {
        return;
    }

    try {
        const authToken = sessionStorage.getItem('auth_token');
        const response = await fetch(`/api/qa/screenshots/${screenshotId}?kb_id=${kbId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const result = await response.json();

        if (result.success) {
            alert('删除成功');
            loadScreenshots();
            loadQAStats();
        } else {
            alert('删除失败: ' + result.error);
        }
    } catch (error) {
        console.error('删除截图失败:', error);
        alert('删除失败: ' + error.message);
    }
}

/**
 * 加载问答统计信息
 */
async function loadQAStats() {
    try {
        const authToken = sessionStorage.getItem('auth_token');
        const response = await fetch(`/api/qa/stats?kb_id=${kbId}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        const result = await response.json();

        if (result.success) {
            const qaCountElement = document.getElementById('qaCount');
            if (qaCountElement) {
                qaCountElement.textContent = `(${result.stats.total_qa_pairs}个问答对)`;
            }
        }
    } catch (error) {
        console.error('加载问答统计失败:', error);
    }
}

// 在原有的初始化函数中添加Tab初始化
document.addEventListener('DOMContentLoaded', function () {
    initTabs();
});

