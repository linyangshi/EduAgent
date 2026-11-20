/**
 * AI Word Editor - 智能Word编辑器
 */

class AIWordEditor {
    constructor() {
        this.sessionId = null;
        this.filename = null;
        this.document = null;
        this.isDirty = false;
        this.autoSaveTimer = null;
        this.selectedText = '';
        this.rewriteResult = '';
        this.currentBlockId = null;
        this.currentBlockEl = null;  // 当前聚焦的编辑块
        this.isCompletionLoading = false;  // 补全加载状态
        this.lastGeneratedContent = null;  // 最后生成的内容（用于插入）
        this.savedSelection = null;  // 保存的选区，用于应用重写
        this.selectionRect = null;   // 保存选区位置
        this.fontFamilySelect = null;
        this.fontSizeSelect = null;
        this.matchPrevFormatBtn = null;
        this.agentTaskId = null;
        this.agentPollTimer = null;
        this.agentDownloadPath = null;
        this.agentLogs = [];
        this.defaultFont = { name: '宋体', size_pt: 12 };
        this.fontStacks = {
            'SimSun': "'SimSun','宋体','Songti SC',serif",
            '宋体': "'宋体','SimSun','Songti SC',serif",
            'KaiTi': "'KaiTi','楷体','STKaiti',serif",
            '楷体': "'楷体','KaiTi','STKaiti',serif",
            'FangSong': "'FangSong','仿宋','FangSong_GB2312',serif",
            '仿宋': "'仿宋','FangSong','FangSong_GB2312',serif",
            'SimHei': "'SimHei','黑体','Heiti SC',sans-serif",
            '黑体': "'黑体','SimHei','Heiti SC',sans-serif",
            'Microsoft YaHei': "'Microsoft YaHei','微软雅黑','PingFang SC',sans-serif",
            'Times New Roman': "'Times New Roman','Times',serif"
        };

        this.init();
    }

    async init() {
        console.log('🚀 DocuMind 智能文档编辑器初始化...');

        this.bindEvents();

        // 检查URL参数
        const urlParams = new URLSearchParams(window.location.search);
        const sessionId = urlParams.get('session');
        if (sessionId) {
            await this.loadSession(sessionId);
        }
    }

    getAuthHeaders() {
        return {
            'Content-Type': 'application/json'
        };
    }

    bindEvents() {
        // 文件上传
        document.getElementById('fileInput').addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                this.handleFileUpload(e.target.files[0]);
            }
        });

        this.fontFamilySelect = document.getElementById('fontFamilySelect');
        this.fontSizeSelect = document.getElementById('fontSizeSelect');
        this.matchPrevFormatBtn = document.getElementById('matchPrevFormatBtn');
        this.indentBtn = document.getElementById('indentBtn');
        this.agentStatusBadge = document.getElementById('agentStatusBadge');
        this.agentLogContainer = document.getElementById('agentLog');
        this.agentPromptInput = document.getElementById('agentPrompt');
        this.agentModeSelect = document.getElementById('agentModeSelect');
        this.agentBackendSelect = document.getElementById('agentBackendSelect');

        if (this.fontFamilySelect) {
            this.fontFamilySelect.addEventListener('change', (e) => {
                const value = e.target.value;
                if (!this.currentBlockEl) {
                    this.showNotification('请先选择要调整的段落或单元格', 'warning');
                    e.target.value = '';
                    return;
                }
                this.applyFontFamily(value);
            });
        }

        if (this.fontSizeSelect) {
            this.fontSizeSelect.addEventListener('change', (e) => {
                const value = e.target.value;
                if (!this.currentBlockEl) {
                    this.showNotification('请先选择要调整的段落或单元格', 'warning');
                    e.target.value = '';
                    return;
                }
                this.applyFontSize(value);
            });
        }

        if (this.matchPrevFormatBtn) {
            this.matchPrevFormatBtn.addEventListener('click', () => {
                if (!this.currentBlockEl) {
                    this.showNotification('请先选择要调整的段落或单元格', 'warning');
                    return;
                }
                this.matchPreviousFormat();
            });
        }

        if (this.indentBtn) {
            this.indentBtn.addEventListener('click', () => {
                if (!this.currentBlockEl) {
                    this.showNotification('请先选择要调整的段落', 'warning');
                    return;
                }
                this.toggleIndent();
            });
        }

        const agentStartBtn = document.getElementById('agentStartBtn');
        if (agentStartBtn) {
            agentStartBtn.addEventListener('click', () => this.startAgentGeneration());
        }

        const agentDownloadBtn = document.getElementById('agentDownloadBtn');
        if (agentDownloadBtn) {
            agentDownloadBtn.addEventListener('click', () => this.downloadAgentResult());
        }

        // 拖拽上传 - 整个欢迎区域
        const welcomeSection = document.getElementById('welcomeSection');
        if (welcomeSection) {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
                welcomeSection.addEventListener(event, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                });
            });

            welcomeSection.addEventListener('dragover', () => welcomeSection.classList.add('drag-over'));
            welcomeSection.addEventListener('dragleave', () => welcomeSection.classList.remove('drag-over'));
            welcomeSection.addEventListener('drop', (e) => {
                welcomeSection.classList.remove('drag-over');
                if (e.dataTransfer.files.length > 0) {
                    this.handleFileUpload(e.dataTransfer.files[0]);
                }
            });
        }

        // 按钮事件
        document.getElementById('saveBtn').addEventListener('click', () => this.saveDocument());
        document.getElementById('exportBtn').addEventListener('click', () => this.exportDocument());
        document.getElementById('toggleSidebar').addEventListener('click', () => this.toggleSidebar());
        document.getElementById('closeSidebar').addEventListener('click', () => this.closeSidebar());
        document.getElementById('sendChatBtn').addEventListener('click', () => this.sendChatMessage());

        document.getElementById('chatInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendChatMessage();
            }
        });

        document.getElementById('aiRewriteBtn').addEventListener('click', () => this.openRewriteModal());

        // 快捷键
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 's') {
                e.preventDefault();
                this.saveDocument();
            }
            if (e.ctrlKey && e.key === 'k' && this.selectedText) {
                e.preventDefault();
                this.openRewriteModal();
            }
        });

        // 页面离开提示
        window.addEventListener('beforeunload', (e) => {
            if (this.isDirty) {
                e.preventDefault();
                e.returnValue = '您有未保存的更改，确定要离开吗？';
            }
        });
    }

    async handleFileUpload(file) {
        if (!file.name.endsWith('.docx')) {
            this.showNotification('只支持.docx格式文件', 'error');
            return;
        }

        this.showLoading('正在上传并分析文档...');

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/editor/upload', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
                },
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                this.sessionId = data.session_id;
                this.filename = data.document.filename;
                this.document = data.document;

                window.history.pushState({}, '', `?session=${this.sessionId}`);
                this.renderEditor();
                this.switchToEditMode();
                this.showNotification('文档加载成功！', 'success');
            } else {
                this.showNotification(data.error || '上传失败', 'error');
            }
        } catch (error) {
            console.error('上传失败:', error);
            this.showNotification('上传失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    async loadSession(sessionId) {
        this.showLoading('正在加载文档...');

        try {
            const response = await fetch(`/api/editor/document/${sessionId}`, {
                headers: this.getAuthHeaders()
            });

            const data = await response.json();

            if (data.success) {
                this.sessionId = sessionId;
                this.filename = data.document.filename;
                this.document = data.document;

                this.renderEditor();
                this.switchToEditMode();
                this.showNotification('文档加载成功！', 'success');
            } else {
                this.showNotification(data.error || '加载失败', 'error');
            }
        } catch (error) {
            console.error('加载失败:', error);
            this.showNotification('加载失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    renderEditor() {
        if (!this.document || !this.document.blocks) return;

        const container = document.getElementById('documentEditor');
        let html = '';

        for (const block of this.document.blocks) {
            if (block.block_type === 'paragraph') {
                const content = block.content || '';
                if (block.has_drawing) {
                    const fontAttrs = this.buildFontAttributes(block.font);
                    html += `<div class="editor-block readonly" data-block-id="${block.block_id}"${fontAttrs}>[图片内容，不可编辑]</div>`;
                } else {
                    let fontAttrs = this.buildFontAttributes(block.font);
                    if (block.indent) {
                        if (fontAttrs.includes('style="')) {
                            fontAttrs = fontAttrs.replace('style="', 'style="text-indent: 2em; ');
                        } else {
                            fontAttrs += ' style="text-indent: 2em"';
                        }
                        fontAttrs += ' data-indent="true"';
                    }
                    html += `<div class="editor-block editable" data-block-id="${block.block_id}"${fontAttrs} contenteditable="true">${this.escapeHtml(content)}</div>`;
                }
            } else if (block.block_type === 'table') {
                html += this.renderTable(block);
            }
        }

        container.innerHTML = html;
        this.bindEditorEvents();
    }

    renderTable(block) {
        const tableData = block.content;
        if (!tableData || !tableData.cells) return '';

        let html = `<table class="editor-table" data-block-id="${block.block_id}">`;

        for (const row of tableData.cells) {
            html += '<tr>';
            for (const cell of row) {
                const colspan = cell.col_span > 1 ? ` colspan="${cell.col_span}"` : '';
                // 将换行符转换为<br>用于显示
                const fontAttrs = this.buildFontAttributes(cell.font);
                const content = this.escapeHtml(cell.content || '').replace(/\n/g, '<br>');
                html += `<td${colspan} class="editor-cell" data-row="${cell.row}" data-col="${cell.col}"${fontAttrs} contenteditable="true">${content}</td>`;
            }
            html += '</tr>';
        }

        html += '</table>';
        return html;
    }

    buildFontAttributes(fontMeta) {
        const meta = fontMeta || {};
        const attrs = [];
        const styleParts = [];

        if (meta.name) {
            const safeName = String(meta.name).replace(/"/g, '&quot;');
            attrs.push(`data-font-name="${safeName}"`);
            styleParts.push(`font-family:${this.getFontFamilyStack(meta.name)}`);
        }

        if (meta.size_pt) {
            const size = parseFloat(meta.size_pt);
            if (!isNaN(size)) {
                attrs.push(`data-font-size="${size}"`);
                styleParts.push(`font-size:${size}pt`);
            }
        }

        if (!attrs.length && !styleParts.length) return '';
        const attrStr = attrs.length ? ' ' + attrs.join(' ') : '';
        const styleStr = styleParts.length ? ` style="${styleParts.join(';')}"` : '';
        return attrStr + styleStr;
    }

    getFontFamilyStack(name) {
        if (!name) {
            return this.getFontFamilyStack(this.defaultFont.name);
        }
        return this.fontStacks[name] || `'${name}', serif`;
    }

    ensureFontDefaults(el) {
        if (!el) return;
        const hasFont = el.dataset.fontName || el.dataset.fontSize;
        if (hasFont) return;

        const prev = this.findPreviousEditableElement(el);
        if (prev) {
            const prevMeta = this.getElementFontMeta(prev, true);
            if (prevMeta) {
                this.setElementFont(el, prevMeta, { silent: true });
                return;
            }
        }
        this.setElementFont(el, this.defaultFont, { silent: true });
    }

    getElementFontMeta(el, datasetOnly = false) {
        if (!el) return null;
        const name = el.dataset.fontName || '';
        const size = el.dataset.fontSize ? parseFloat(el.dataset.fontSize) : null;
        if (!datasetOnly) {
            if (!name) {
                const style = window.getComputedStyle(el);
                return {
                    name: this.extractPrimaryFontName(style.fontFamily),
                    size_pt: this.convertPxToPt(parseFloat(style.fontSize))
                };
            }
        }
        if (!name && (size === null || isNaN(size))) return null;
        return {
            name: name || undefined,
            size_pt: !isNaN(size) ? size : undefined
        };
    }

    extractPrimaryFontName(fontFamily) {
        if (!fontFamily) return undefined;
        const first = fontFamily.split(',')[0].trim();
        return first.replace(/^['"]|['"]$/g, '') || undefined;
    }

    convertPxToPt(px) {
        if (!px || isNaN(px)) return undefined;
        return Math.round((px * 72 / 96) * 10) / 10;
    }

    setElementFont(el, fontMeta, options = {}) {
        if (!el || !fontMeta) return;
        const current = this.getElementFontMeta(el, true) || {};
        const next = {
            name: fontMeta.name !== undefined ? fontMeta.name : current.name,
            size_pt: fontMeta.size_pt !== undefined ? fontMeta.size_pt : current.size_pt
        };

        if (next.name) {
            el.dataset.fontName = next.name;
            el.style.fontFamily = this.getFontFamilyStack(next.name);
        } else {
            delete el.dataset.fontName;
            el.style.removeProperty('font-family');
        }

        if (next.size_pt) {
            el.dataset.fontSize = String(next.size_pt);
            el.style.fontSize = `${next.size_pt}pt`;
        } else {
            delete el.dataset.fontSize;
            el.style.removeProperty('font-size');
        }

        if (!options.silent) {
            this.isDirty = true;
            this.scheduleAutoSave();
        }
    }

    applyFontFamily(fontName) {
        if (!this.currentBlockEl) return;
        if (!fontName) {
            this.setElementFont(this.currentBlockEl, { name: this.defaultFont.name });
        } else {
            this.setElementFont(this.currentBlockEl, { name: fontName });
        }
        this.updateFormattingToolbar(this.currentBlockEl);
    }

    applyFontSize(sizeValue) {
        if (!this.currentBlockEl) return;
        const size = sizeValue ? parseFloat(sizeValue) : this.defaultFont.size_pt;
        if (size && !isNaN(size)) {
            this.setElementFont(this.currentBlockEl, { size_pt: size });
            this.updateFormattingToolbar(this.currentBlockEl);
        }
    }

    toggleIndent() {
        if (!this.currentBlockEl) return;
        
        // 检查当前缩进状态
        const current = this.currentBlockEl.style.textIndent;
        const isIndented = current === '2em' || this.currentBlockEl.dataset.indent === 'true';
        
        if (isIndented) {
            this.currentBlockEl.style.textIndent = '';
            delete this.currentBlockEl.dataset.indent;
        } else {
            this.currentBlockEl.style.textIndent = '2em';
            this.currentBlockEl.dataset.indent = 'true';
        }
        
        this.isDirty = true;
        this.scheduleAutoSave();
        this.updateFormattingToolbar(this.currentBlockEl);
    }

    matchPreviousFormat() {
        const prev = this.findPreviousEditableElement(this.currentBlockEl);
        if (!prev) {
            this.showNotification('找不到上一段格式', 'warning');
            return;
        }
        const fontMeta = this.getElementFontMeta(prev, true);
        if (!fontMeta) {
            this.showNotification('上一段没有可复制的格式', 'warning');
            return;
        }
        this.setElementFont(this.currentBlockEl, fontMeta);
        this.updateFormattingToolbar(this.currentBlockEl);
        this.showNotification('已同步上一段格式', 'success');
    }

    findPreviousEditableElement(el) {
        if (!el) return null;
        const elements = Array.from(document.querySelectorAll('.editor-block.editable, .editor-cell'));
        const idx = elements.indexOf(el);
        if (idx <= 0) return null;
        for (let i = idx - 1; i >= 0; i--) {
            const candidate = elements[i];
            if (candidate.dataset.fontName || candidate.dataset.fontSize) {
                return candidate;
            }
        }
        return null;
    }

    updateFormattingToolbar(el) {
        if (!el) return;
        const meta = this.getElementFontMeta(el, true);
        if (this.fontFamilySelect) {
            this.fontFamilySelect.value = meta?.name || '';
        }
        if (this.fontSizeSelect) {
            this.fontSizeSelect.value = meta?.size_pt ? String(meta.size_pt) : '';
        }
        if (this.indentBtn) {
            const isIndented = el.style.textIndent === '2em' || el.dataset.indent === 'true';
            if (isIndented) this.indentBtn.classList.add('active');
            else this.indentBtn.classList.remove('active');
        }
    }

    bindEditorEvents() {
        // 编辑事件
        document.querySelectorAll('.editor-block.editable, .editor-cell').forEach(el => {
            el.addEventListener('input', () => {
                this.isDirty = true;
                this.scheduleAutoSave();
            });

            el.addEventListener('focus', () => {
                this.currentBlockId = el.dataset.blockId || el.closest('table')?.dataset.blockId;
                this.currentBlockEl = el;
                this.ensureFontDefaults(el);
                this.updateFormattingToolbar(el);
            });

            // 键盘事件
            el.addEventListener('keydown', (e) => {
                // Tab键自动补全
                if (e.key === 'Tab' && !e.shiftKey) {
                    e.preventDefault();
                    this.triggerAutoComplete(el);
                }
                // 回车键检测@@@占位符
                if (e.key === 'Enter' && !e.shiftKey) {
                    const handled = this.checkAndTriggerPlaceholder(el);
                    if (handled) {
                        e.preventDefault();
                    }
                }
            });
        });

        // 选中文本检测 - 显示悬浮按钮
        document.getElementById('documentEditor').addEventListener('mouseup', (e) => {
            // 延迟检测，确保选区已经稳定
            setTimeout(() => {
                this.handleTextSelection(e);
            }, 10);
        });

        // 点击其他地方隐藏悬浮按钮
        document.addEventListener('mousedown', (e) => {
            const floatingBtn = document.getElementById('floatingAiBtn');
            const floatingPopup = document.getElementById('floatingRewritePopup');

            // 如果点击的不是悬浮按钮或弹窗，则隐藏它们
            if (floatingBtn && !floatingBtn.contains(e.target) &&
                floatingPopup && !floatingPopup.contains(e.target) &&
                !e.target.closest('#documentEditor')) {
                floatingBtn.style.display = 'none';
                // 不要在这里隐藏弹窗，让用户可以继续操作
            }
        });
    }

    // 处理文本选择，显示悬浮AI按钮
    handleTextSelection(e) {
        const selection = window.getSelection();
        this.selectedText = selection.toString().trim();

        const floatingBtn = document.getElementById('floatingAiBtn');
        const floatingPopup = document.getElementById('floatingRewritePopup');

        if (this.selectedText && selection.rangeCount > 0) {
            // 保存选区以便后续应用
            this.savedSelection = selection.getRangeAt(0).cloneRange();

            // 获取选区的位置
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            this.selectionRect = rect;

            // 计算悬浮按钮位置（在选中文字的下方居中）
            const btnWidth = 100; // 按钮大约宽度
            let left = rect.left + (rect.width / 2) - (btnWidth / 2);
            let top = rect.bottom + window.scrollY + 8;

            // 确保不超出屏幕边界
            if (left < 10) left = 10;
            if (left + btnWidth > window.innerWidth - 10) {
                left = window.innerWidth - btnWidth - 10;
            }

            floatingBtn.style.left = left + 'px';
            floatingBtn.style.top = top + 'px';
            floatingBtn.style.display = 'block';

            // 同时更新工具栏按钮（可选）
            document.getElementById('aiRewriteBtn').style.display = 'inline-flex';
        } else {
            // 如果弹窗没有打开，则隐藏按钮
            if (floatingPopup.style.display === 'none') {
                floatingBtn.style.display = 'none';
            }
            document.getElementById('aiRewriteBtn').style.display = 'none';
        }
    }

    // ========== @@@占位符实时生成功能 ==========
    checkAndTriggerPlaceholder(el) {
        const text = el.textContent;
        // 匹配 @@@xxx 模式（xxx是指令）
        const match = text.match(/@@@([^\s@]+)\s*$/);

        if (match) {
            const instruction = match[1];
            const placeholder = match[0];
            this.generateAndReplacePlaceholder(el, placeholder, instruction);
            return true;
        }
        return false;
    }

    async generateAndReplacePlaceholder(el, placeholder, instruction) {
        if (this.isCompletionLoading) return;
        this.isCompletionLoading = true;

        // 获取文档上下文（排除当前占位符）
        const fullText = el.textContent;
        const contextBefore = fullText.substring(0, fullText.lastIndexOf(placeholder));
        const docContext = this.getDocumentText();

        // 保存原始HTML内容以保持格式
        const originalHTML = el.innerHTML;
        const originalText = el.textContent;

        // 显示加载状态：将@@@xxx替换为加载提示
        el.innerHTML = this.escapeHtml(contextBefore) + '<span class="placeholder-loading">正在生成' + this.escapeHtml(instruction) + '...</span>';

        try {
            const response = await fetch('/api/ai/generate-placeholder', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    instruction: instruction,
                    context_before: contextBefore,
                    document_context: docContext.substring(0, 2000)
                })
            });

            const data = await response.json();

            if (data.success && data.content) {
                // 🔧 修复：保持换行格式
                // 1. 获取原始HTML，找到@@@占位符的位置
                const placeholderIndex = originalHTML.lastIndexOf(this.escapeHtml(placeholder));

                if (placeholderIndex !== -1) {
                    // 2. 分割HTML: 之前的部分 + 生成的内容
                    const htmlBefore = originalHTML.substring(0, placeholderIndex);
                    // 将生成内容中的换行转换为<br>
                    const generatedContentHTML = this.escapeHtml(data.content).replace(/\n/g, '<br>');
                    el.innerHTML = htmlBefore + generatedContentHTML;
                } else {
                    // 降级方案：如果找不到占位符，使用textContent
                    el.textContent = contextBefore + data.content;
                }

                this.isDirty = true;
                this.scheduleAutoSave();
                this.showNotification(`已生成: ${instruction}`, 'success');
            } else {
                // 恢复原HTML以保持格式
                el.innerHTML = originalHTML;
                this.showNotification(data.error || '生成失败', 'error');
            }
        } catch (error) {
            // 恢复原HTML以保持格式
            el.innerHTML = originalHTML;
            console.error('占位符生成失败:', error);
            this.showNotification('生成失败: ' + error.message, 'error');
        } finally {
            this.isCompletionLoading = false;
        }
    }

    // ========== Tab自动补全功能 ==========
    async triggerAutoComplete(el) {
        if (this.isCompletionLoading) return;

        // 获取光标前的文本作为上下文
        const selection = window.getSelection();
        const range = selection.getRangeAt(0);

        // 获取光标位置前的文本
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(el);
        preCaretRange.setEnd(range.endContainer, range.endOffset);
        const textBeforeCursor = preCaretRange.toString();

        // 获取整个文档的上下文
        const fullContext = this.getDocumentText();

        if (!textBeforeCursor.trim()) {
            this.showNotification('请先输入一些内容再使用自动补全', 'warning');
            return;
        }

        this.isCompletionLoading = true;

        // 显示补全加载提示
        const loadingSpan = document.createElement('span');
        loadingSpan.className = 'completion-loading';
        loadingSpan.textContent = '...';
        range.insertNode(loadingSpan);

        try {
            const response = await fetch('/api/ai/complete', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    text_before: textBeforeCursor,
                    full_context: fullContext.substring(0, 1500)
                })
            });

            const data = await response.json();

            // 移除加载提示
            loadingSpan.remove();

            if (data.success && data.completion) {
                // 插入补全内容
                const completionSpan = document.createElement('span');
                completionSpan.className = 'completion-text';
                completionSpan.textContent = data.completion;

                // 在光标位置插入
                const newRange = document.createRange();
                newRange.setStartAfter(range.endContainer);
                selection.removeAllRanges();
                selection.addRange(range);

                document.execCommand('insertText', false, data.completion);

                this.isDirty = true;
                this.scheduleAutoSave();
            } else if (data.error) {
                this.showNotification(data.error, 'error');
            }
        } catch (error) {
            loadingSpan.remove();
            console.error('自动补全失败:', error);
            this.showNotification('自动补全失败', 'error');
        } finally {
            this.isCompletionLoading = false;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========== 新建空白文档 ==========
    async createNewDocument() {
        this.showLoading('正在创建新文档...');

        try {
            const response = await fetch('/api/editor/new', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    filename: '未命名文档.docx'
                })
            });

            const data = await response.json();

            if (data.success) {
                this.sessionId = data.session_id;
                this.filename = data.document.filename;
                this.document = data.document;

                window.history.pushState({}, '', `?session=${this.sessionId}`);

                // 创建一个空的编辑区域
                const container = document.getElementById('documentEditor');
                const fontAttrs = this.buildFontAttributes(this.defaultFont);
                container.innerHTML = `
                    <div class="editor-block editable" data-block-id="new-block-1"${fontAttrs} contenteditable="true" placeholder="开始输入内容，或使用 @@@指令 生成..."></div>
                `;

                this.bindEditorEvents();
                this.switchToEditMode();
                this.showNotification('已创建新文档', 'success');

                // 聚焦到编辑区
                setTimeout(() => {
                    const firstBlock = container.querySelector('.editor-block.editable');
                    if (firstBlock) firstBlock.focus();
                }, 100);
            } else {
                this.showNotification(data.error || '创建失败', 'error');
            }
        } catch (error) {
            console.error('创建文档失败:', error);
            this.showNotification('创建失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    switchToEditMode() {
        // 隐藏欢迎页面
        const welcomeSection = document.getElementById('welcomeSection');
        if (welcomeSection) welcomeSection.style.display = 'none';

        // 显示编辑区域
        document.getElementById('editorSection').style.display = 'flex';
        document.getElementById('formatTools').style.display = 'flex';

        // 显示文件名和工具栏按钮
        const fileNameEl = document.getElementById('fileName');
        fileNameEl.style.display = 'block';
        fileNameEl.textContent = this.filename;

        document.getElementById('saveBtn').style.display = 'inline-flex';
        document.getElementById('exportBtn').style.display = 'inline-flex';
        document.getElementById('toggleSidebar').style.display = 'inline-flex';
    }

    scheduleAutoSave() {
        if (this.autoSaveTimer) clearTimeout(this.autoSaveTimer);
        this.autoSaveTimer = setTimeout(() => this.saveDocument(true), 5000);
    }

    async saveDocument(isAutoSave = false) {
        if (!this.sessionId) return;
        if (!isAutoSave) this.showLoading('正在保存...');

        try {
            const changes = this.extractChanges();

            const response = await fetch(`/api/editor/document/${this.sessionId}`, {
                method: 'PUT',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({ changes })
            });

            const data = await response.json();

            if (data.success) {
                this.isDirty = false;
                if (!isAutoSave) this.showNotification('保存成功！', 'success');
            } else {
                this.showNotification(data.error || '保存失败', 'error');
            }
        } catch (error) {
            console.error('保存失败:', error);
            this.showNotification('保存失败: ' + error.message, 'error');
        } finally {
            if (!isAutoSave) this.hideLoading();
        }
    }

    extractChanges() {
        const changes = [];

        // 提取段落变更
        document.querySelectorAll('.editor-block.editable').forEach(el => {
            const change = {
                block_id: el.dataset.blockId,
                content: el.textContent
            };
            const fontMeta = this.getElementFontMeta(el, true);
            if (fontMeta && (fontMeta.name || fontMeta.size_pt)) {
                change.font = fontMeta;
            }
            if (el.dataset.indent === 'true' || el.style.textIndent === '2em') {
                change.indent = true;
            } else {
                change.indent = false;
            }
            changes.push(change);
        });

        // 提取表格变更
        document.querySelectorAll('.editor-cell').forEach(cell => {
            const table = cell.closest('table');
            if (table) {
                // 获取innerHTML并将<br>转换回换行符
                let content = cell.innerHTML;
                // 处理 <br> 标签（可能是 <br>, <br/>, <br /> 等形式）
                content = content.replace(/<br\s*\/?>/gi, '\n');
                // 移除其他HTML标签，只保留文本
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = content;
                content = tempDiv.textContent || tempDiv.innerText || '';

                const change = {
                    block_id: table.dataset.blockId,
                    row: parseInt(cell.dataset.row),
                    col: parseInt(cell.dataset.col),
                    content: content
                };
                const fontMeta = this.getElementFontMeta(cell, true);
                if (fontMeta && (fontMeta.name || fontMeta.size_pt)) {
                    change.font = fontMeta;
                }
                changes.push(change);
            }
        });

        return changes;
    }

    async exportDocument() {
        if (!this.sessionId) return;

        await this.saveDocument();
        this.showLoading('正在导出DOCX...');

        try {
            const response = await fetch(`/api/editor/export/${this.sessionId}`, {
                method: 'POST',
                headers: this.getAuthHeaders()
            });

            const data = await response.json();

            if (data.success) {
                const a = document.createElement('a');
                a.href = data.download_url;
                a.download = data.filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                this.showNotification('导出成功！', 'success');
            } else {
                this.showNotification(data.error || '导出失败', 'error');
            }
        } catch (error) {
            console.error('导出失败:', error);
            this.showNotification('导出失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    // ========== AI 侧边栏功能 ==========
    toggleSidebar() {
        document.getElementById('aiSidebar').classList.toggle('open');
    }

    closeSidebar() {
        document.getElementById('aiSidebar').classList.remove('open');
    }

    async sendChatMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        if (!message) return;

        this.addChatMessage(message, 'user');
        input.value = '';

        // 显示加载状态
        const loadingId = this.addChatMessage('正在思考...', 'ai', true);

        try {
            const response = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    message: message,
                    context: {
                        selected_text: this.selectedText,
                        document_content: this.getDocumentText(),
                        current_block_id: this.currentBlockId
                    }
                })
            });

            const data = await response.json();

            // 移除加载消息
            this.removeChatMessage(loadingId);

            if (data.success) {
                // 检查是否有生成的内容可以插入
                if (data.generated_content) {
                    this.lastGeneratedContent = data.generated_content;
                    this.addChatMessageWithInsert(data.response, data.generated_content);
                } else {
                    this.addChatMessage(data.response, 'ai');
                }
            } else {
                this.addChatMessage('抱歉，发生了错误: ' + (data.error || '未知错误'), 'ai');
            }
        } catch (error) {
            this.removeChatMessage(loadingId);
            this.addChatMessage('网络错误：' + error.message, 'ai');
        }
    }

    async startAgentGeneration() {
        if (!this.sessionId) {
            this.showNotification('请先上传或打开一个文档', 'warning');
            return;
        }
        if (this.agentTaskId) {
            this.showNotification('已有任务正在执行，请稍候', 'warning');
            return;
        }
        const prompt = (this.agentPromptInput?.value || '').trim();
        if (!prompt) {
            this.showNotification('请输入需要生成的指令', 'warning');
            return;
        }

        this.agentLogs = [];
        this.renderAgentLogs(this.agentLogs);
        this.appendLocalAgentLog('🟢 任务已提交，等待排队...');
        this.setAgentStatus('running', '启动中');
        this.toggleAgentDownload(false);

        try {
            const response = await fetch('/api/editor/agent/generate', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    requirement: prompt,
                    mode: this.agentModeSelect ? this.agentModeSelect.value : 'inference',
                    backend: this.agentBackendSelect ? this.agentBackendSelect.value : 'qwen'
                })
            });

            const data = await response.json();
            if (data.success && data.task_id) {
                this.agentTaskId = data.task_id;
                this.pollAgentTask();
            } else {
                this.setAgentStatus('failed', data.error || '任务创建失败');
                this.appendLocalAgentLog(`❌ ${data.error || '任务创建失败'}`);
            }
        } catch (error) {
            this.setAgentStatus('failed', '网络异常');
            this.appendLocalAgentLog(`❌ 启动失败：${error.message}`);
        }
    }

    async pollAgentTask() {
        if (!this.agentTaskId) return;
        try {
            const response = await fetch(`/api/editor/agent/progress/${this.agentTaskId}`, {
                headers: this.getAuthHeaders()
            });
            const data = await response.json();
            if (!data.success) {
                this.setAgentStatus('failed', data.error || '查询失败');
                this.appendLocalAgentLog(`❌ ${data.error || '查询失败'}`);
                this.agentTaskId = null;
                return;
            }

            const logs = (data.logs || []).map(item => ({
                time: item.time || Date.now() / 1000,
                message: item.message || ''
            }));
            if (logs.length) {
                this.agentLogs = logs;
                this.renderAgentLogs(logs);
            }

            this.setAgentStatus(data.status, data.message || '');

            if (data.status === 'completed') {
                this.agentDownloadPath = data.file_path;
                this.toggleAgentDownload(!!data.file_path);
                this.appendLocalAgentLog('📎 文档已生成，可点击下载。');
                this.agentTaskId = null;
                this.stopAgentPolling();
                return;
            }

            if (data.status === 'failed') {
                if (data.error) {
                    this.appendLocalAgentLog(`❌ ${data.error}`);
                }
                this.toggleAgentDownload(false);
                this.agentTaskId = null;
                this.stopAgentPolling();
                return;
            }

            this.scheduleAgentPolling();
        } catch (error) {
            this.appendLocalAgentLog(`⚠️ 查询失败：${error.message}`);
            this.scheduleAgentPolling();
        }
    }

    scheduleAgentPolling() {
        this.stopAgentPolling();
        this.agentPollTimer = setTimeout(() => this.pollAgentTask(), 2500);
    }

    stopAgentPolling() {
        if (this.agentPollTimer) {
            clearTimeout(this.agentPollTimer);
            this.agentPollTimer = null;
        }
    }

    setAgentStatus(status, message = '') {
        if (!this.agentStatusBadge) return;
        const labels = {
            queued: '排队',
            running: '进行中',
            completed: '已完成',
            failed: '已失败'
        };
        this.agentStatusBadge.textContent = labels[status] || '待机';
        if (status === 'completed') {
            this.agentStatusBadge.style.background = 'rgba(16, 185, 129, 0.2)';
        } else if (status === 'failed') {
            this.agentStatusBadge.style.background = 'rgba(248, 113, 113, 0.2)';
        } else if (status === 'running') {
            this.agentStatusBadge.style.background = 'rgba(59, 130, 246, 0.25)';
        } else {
            this.agentStatusBadge.style.background = 'rgba(148, 163, 184, 0.2)';
        }
    }

    appendLocalAgentLog(text) {
        const entry = { time: Date.now() / 1000, message: text };
        this.agentLogs.push(entry);
        this.renderAgentLogs(this.agentLogs);
    }

    renderAgentLogs(logs = []) {
        if (!this.agentLogContainer) return;
        if (!logs.length) {
            this.agentLogContainer.innerHTML = '<div class="agent-log-empty">暂无执行记录</div>';
            return;
        }
        const sorted = [...logs].sort((a, b) => a.time - b.time);
        this.agentLogContainer.innerHTML = sorted.map(log => `
            <div class="agent-log-entry">
                <div class="agent-log-time">${this.formatAgentTime(log.time)}</div>
                <div class="agent-log-text">${this.escapeHtml(log.message || '')}</div>
            </div>
        `).join('');
        this.agentLogContainer.scrollTop = this.agentLogContainer.scrollHeight;
    }

    formatAgentTime(timestamp) {
        if (!timestamp) return '--:--';
        const date = new Date(timestamp * 1000);
        const hh = String(date.getHours()).padStart(2, '0');
        const mm = String(date.getMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    }

    toggleAgentDownload(show) {
        const btn = document.getElementById('agentDownloadBtn');
        if (btn) {
            btn.style.display = show ? 'inline-flex' : 'none';
        }
    }

    downloadAgentResult() {
        if (!this.agentDownloadPath) {
            this.showNotification('还没有可下载的文档', 'warning');
            return;
        }
        const url = `/api/unified/download?file_path=${encodeURIComponent(this.agentDownloadPath)}`;
        window.open(url, '_blank');
    }

    getDocumentText() {
        const editor = document.getElementById('documentEditor');
        return editor ? editor.textContent.substring(0, 2000) : '';
    }

    addChatMessage(text, role, isLoading = false) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        const msgId = 'msg-' + Date.now();
        div.id = msgId;
        div.className = `chat-message ${role}${isLoading ? ' loading' : ''}`;
        div.innerHTML = `<div class="message-content">${this.escapeHtml(text)}</div>`;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return msgId;
    }

    removeChatMessage(msgId) {
        const msg = document.getElementById(msgId);
        if (msg) msg.remove();
    }

    // 添加带有"插入文档"按钮的AI消息
    addChatMessageWithInsert(responseText, generatedContent) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        div.className = 'chat-message ai with-actions';

        div.innerHTML = `
            <div class="message-content">${this.escapeHtml(responseText)}</div>
            <div class="generated-content-preview">
                <div class="preview-label">生成的内容：</div>
                <div class="preview-text">${this.escapeHtml(generatedContent)}</div>
            </div>
            <div class="message-actions">
                <button class="insert-btn" onclick="aiEditor.insertGeneratedContent('${this.escapeAttr(generatedContent)}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 5v14M5 12h14"/>
                    </svg>
                    插入到文档
                </button>
                <button class="copy-btn" onclick="aiEditor.copyToClipboard('${this.escapeAttr(generatedContent)}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"></path>
                    </svg>
                    复制
                </button>
            </div>
        `;

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    escapeAttr(str) {
        return str.replace(/'/g, "\\'").replace(/\n/g, '\\n');
    }

    // 插入生成的内容到文档
    insertGeneratedContent(content) {
        // 还原转义的换行符
        content = content.replace(/\\n/g, '\n').replace(/\\'/g, "'");

        if (this.currentBlockEl) {
            // 如果有当前聚焦的块，插入到该块末尾
            const currentText = this.currentBlockEl.textContent;
            this.currentBlockEl.textContent = currentText + (currentText ? '\n' : '') + content;
            this.isDirty = true;
            this.scheduleAutoSave();
            this.showNotification('已插入到当前段落', 'success');
        } else {
            // 否则创建新段落插入
            const editor = document.getElementById('documentEditor');
            const newBlock = document.createElement('div');
            newBlock.className = 'editor-block editable';
            newBlock.contentEditable = 'true';
            newBlock.dataset.blockId = 'new-' + Date.now();
            newBlock.textContent = content;
            editor.appendChild(newBlock);

            // 绑定事件
            newBlock.addEventListener('input', () => {
                this.isDirty = true;
                this.scheduleAutoSave();
            });
            newBlock.addEventListener('focus', () => {
                this.currentBlockId = newBlock.dataset.blockId;
                this.currentBlockEl = newBlock;
            });
            newBlock.addEventListener('keydown', (e) => {
                if (e.key === 'Tab' && !e.shiftKey) {
                    e.preventDefault();
                    this.triggerAutoComplete(newBlock);
                }
            });

            this.isDirty = true;
            this.scheduleAutoSave();
            this.showNotification('已添加新段落', 'success');
        }
    }

    copyToClipboard(content) {
        content = content.replace(/\\n/g, '\n').replace(/\\'/g, "'");
        navigator.clipboard.writeText(content).then(() => {
            this.showNotification('已复制到剪贴板', 'success');
        }).catch(() => {
            this.showNotification('复制失败', 'error');
        });
    }

    // ========== 悬浮重写功能 ==========
    openFloatingRewrite() {
        if (!this.selectedText) {
            this.showNotification('请先选中要重写的文本', 'warning');
            return;
        }

        const floatingBtn = document.getElementById('floatingAiBtn');
        const popup = document.getElementById('floatingRewritePopup');

        // 设置选中文本预览
        document.getElementById('floatingSelectedText').textContent = this.selectedText;
        document.getElementById('floatingRewriteInput').value = '';
        document.getElementById('floatingResultArea').style.display = 'none';
        document.getElementById('floatingApplyBtn').style.display = 'none';
        document.getElementById('floatingRewriteBtn').style.display = 'inline-flex';

        // 计算弹窗位置（在按钮下方）
        const btnRect = floatingBtn.getBoundingClientRect();
        let left = btnRect.left;
        let top = btnRect.bottom + window.scrollY + 8;

        // 确保不超出屏幕右边界
        const popupWidth = 400;
        if (left + popupWidth > window.innerWidth - 20) {
            left = window.innerWidth - popupWidth - 20;
        }
        if (left < 20) left = 20;

        popup.style.left = left + 'px';
        popup.style.top = top + 'px';
        popup.style.display = 'block';

        // 隐藏悬浮按钮
        floatingBtn.style.display = 'none';

        // 聚焦输入框
        setTimeout(() => {
            document.getElementById('floatingRewriteInput').focus();
        }, 100);
    }

    closeFloatingRewrite() {
        document.getElementById('floatingRewritePopup').style.display = 'none';
        document.getElementById('floatingAiBtn').style.display = 'none';
        this.rewriteResult = '';
    }

    async doFloatingRewrite() {
        const instruction = document.getElementById('floatingRewriteInput').value.trim();
        if (!instruction) {
            this.showNotification('请输入重写要求', 'warning');
            return;
        }

        const btn = document.getElementById('floatingRewriteBtn');
        btn.disabled = true;
        btn.textContent = '重写中...';

        try {
            const response = await fetch('/api/ai/rewrite', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    selected_text: this.selectedText,
                    instruction: instruction
                })
            });

            const data = await response.json();

            if (data.success) {
                this.rewriteResult = data.rewritten;
                document.getElementById('floatingResultText').textContent = data.rewritten;
                document.getElementById('floatingResultArea').style.display = 'block';
                document.getElementById('floatingApplyBtn').style.display = 'inline-flex';
                btn.style.display = 'none';
            } else {
                this.showNotification(data.error || '重写失败', 'error');
            }
        } catch (error) {
            this.showNotification('重写失败: ' + error.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '重写';
        }
    }

    applyFloatingRewrite() {
        if (!this.rewriteResult || !this.savedSelection) {
            this.showNotification('无法应用：没有保存的选区', 'error');
            return;
        }

        try {
            // 使用保存的选区进行替换
            const range = this.savedSelection;

            // 删除选中的内容
            range.deleteContents();

            // 插入新内容
            const textNode = document.createTextNode(this.rewriteResult);
            range.insertNode(textNode);

            // 将光标移动到新插入内容的末尾
            range.setStartAfter(textNode);
            range.setEndAfter(textNode);

            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);

            this.isDirty = true;
            this.scheduleAutoSave();
            this.closeFloatingRewrite();
            this.showNotification('已应用重写结果', 'success');
        } catch (error) {
            console.error('应用重写失败:', error);
            this.showNotification('应用失败，请重新选择文本', 'error');
        }
    }

    // ========== 旧版模态框功能（保留兼容）==========
    openRewriteModal() {
        if (!this.selectedText) {
            this.showNotification('请先选中要重写的文本', 'warning');
            return;
        }
        // 使用新的悬浮方式
        this.openFloatingRewrite();
    }

    closeRewriteModal() {
        this.closeFloatingRewrite();
    }

    async doRewrite() {
        await this.doFloatingRewrite();
    }

    applyRewrite() {
        this.applyFloatingRewrite();
    }

    // 工具函数
    showLoading(text = '加载中...') {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('notifications');
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        container.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('fade-out');
            setTimeout(() => container.removeChild(notification), 300);
        }, 3000);
    }
}

// 初始化
let aiEditor;
document.addEventListener('DOMContentLoaded', () => {
    aiEditor = new AIWordEditor();
});
