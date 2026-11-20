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
        this.savedSelection = null;  // 保存的选区，用于应用重写/缩进
        this.selectionRect = null;   // 保存选区位置
        this.fontFamilySelect = null;
        this.fontSizeSelect = null;
        this.matchPrevFormatBtn = null;
        this.agentTaskId = null;
        this.agentPollTimer = null;
        this.agentDownloadPath = null;
        this.agentLogs = [];
        this.defaultFont = { name: '宋体', size_pt: 12 };
        this.operationHistory = [];
        this.maxHistory = 50;
        // 实时建议相关状态
        this.inlineSuggestion = '';  // 当前的行内建议
        this.suggestionDebounceTimer = null;  // 防抖定时器
        this.suggestionElement = null;  // 建议显示元素
        this.suggestionAbortController = null;  // 用于取消请求
        this.lastSuggestionText = '';  // 上次请求时的文本，避免重复请求
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
        this.lastSelectionMeta = null;
        this.selectionMonitorInitialized = false;

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

        // 首行缩进按钮
        const indentBtn = document.getElementById('indentBtn');
        if (indentBtn) {
            indentBtn.addEventListener('click', () => {
                this.applyFirstLineIndent();
            });
        }

        // 清理Markdown按钮
        const cleanMarkdownBtn = document.getElementById('cleanMarkdownBtn');
        if (cleanMarkdownBtn) {
            cleanMarkdownBtn.addEventListener('click', () => {
                this.cleanMarkdownFormat();
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
            if ((e.ctrlKey || e.metaKey) && e.key === '/') {
                e.preventDefault();
                this.applyFirstLineIndent();
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                if (this.operationHistory.length > 0) {
                    e.preventDefault();
                    this.undoLastAction();
                }
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
                    'Authorization': `Bearer ${sessionStorage.getItem('auth_token')}`
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
        const indent = '　　';  // 两个全角空格

        for (const block of this.document.blocks) {
            if (block.block_type === 'paragraph') {
                let content = block.content || '';
                // 🔥 如果原文档有首行缩进，在内容开头添加全角空格显示
                if (block.indent && content && !content.startsWith('　') && !content.startsWith('  ')) {
                    content = indent + content;
                }
                if (block.has_drawing) {
                    const fontAttrs = this.buildFontAttributes(block.font);
                    html += `<div class="editor-block readonly" data-block-id="${block.block_id}"${fontAttrs}>[图片内容，不可编辑]</div>`;
                } else {
                    const fontAttrs = this.buildFontAttributes(block.font);
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

        // 预处理：计算每个列的垂直合并信息
        // 使用 Map 来跟踪每列的合并状态
        const colMergeInfo = new Map();  // key: col, value: { startRow, endRow, content }

        // 第一遍：识别所有垂直合并
        for (let rowIdx = 0; rowIdx < tableData.cells.length; rowIdx++) {
            const row = tableData.cells[rowIdx];
            for (const cell of row) {
                const colIdx = cell.col;
                const vmerge = cell.v_merge;

                if (vmerge === 'restart' || vmerge === 'start') {
                    // 开始新的合并
                    colMergeInfo.set(colIdx, { startRow: rowIdx, endRow: rowIdx });
                } else if (vmerge === 'continue') {
                    // 继续合并
                    const info = colMergeInfo.get(colIdx);
                    if (info) {
                        info.endRow = rowIdx;
                    }
                }
            }
        }

        // 计算每个合并起始单元格的rowspan
        const rowspanMap = new Map();  // key: `${row}-${col}`, value: rowspan
        for (const [col, info] of colMergeInfo) {
            const rowspan = info.endRow - info.startRow + 1;
            if (rowspan > 1) {
                rowspanMap.set(`${info.startRow}-${col}`, rowspan);
            }
        }

        // 创建已渲染单元格跟踪器，避免重复渲染
        const renderedCells = new Set();

        for (let rowIdx = 0; rowIdx < tableData.cells.length; rowIdx++) {
            const row = tableData.cells[rowIdx];
            html += '<tr>';

            for (const cell of row) {
                const colIdx = cell.col;
                const cellKey = `${rowIdx}-${colIdx}`;

                // 检查是否已经渲染过（防止重复）
                if (renderedCells.has(cellKey)) {
                    continue;
                }

                // 检查是否是被垂直合并的单元格（应该跳过）
                if (cell.v_merge === 'continue') {
                    // 这个单元格是被合并的，跳过渲染
                    renderedCells.add(cellKey);
                    continue;
                }

                const colspan = cell.col_span > 1 ? ` colspan="${cell.col_span}"` : '';

                // 获取预计算的rowspan
                let rowspan = '';
                const precomputedRowspan = rowspanMap.get(cellKey);
                if (precomputedRowspan) {
                    rowspan = ` rowspan="${precomputedRowspan}"`;
                }

                // 将换行符转换为<br>用于显示
                const fontAttrs = this.buildFontAttributes(cell.font);
                const content = this.escapeHtml(cell.content || '').replace(/\n/g, '<br>');
                html += `<td${colspan}${rowspan} class="editor-cell" data-row="${cell.row}" data-col="${cell.col}"${fontAttrs} contenteditable="true">${content}</td>`;

                renderedCells.add(cellKey);
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

    // ========== 首行缩进功能 ==========
    applyFirstLineIndent() {
        const editor = document.getElementById('documentEditor');
        if (!editor) {
            this.showNotification('编辑器未准备好', 'error');
            return;
        }

        const selection = window.getSelection();
        const allBlocks = Array.from(editor.querySelectorAll('.editor-block.editable, .editor-cell'));
        let targetElements = [];
        let workingRange = null;
        let debugSource = 'none';

        if (selection && selection.rangeCount > 0) {
            const activeRange = selection.getRangeAt(0);
            if (!activeRange.collapsed) {
                const cloned = activeRange.cloneRange();
                if (this.isRangeInsideEditor(cloned, editor)) {
                    workingRange = cloned;
                    debugSource = 'active_selection';
                }
            }
        }

        if (!workingRange && this.savedSelection) {
            const savedRange = this.savedSelection.cloneRange ? this.savedSelection.cloneRange() : this.savedSelection;
            if (savedRange && !savedRange.collapsed && this.isRangeInsideEditor(savedRange, editor)) {
                workingRange = savedRange;
                debugSource = 'saved_selection';
            }
        }

        if (workingRange && !workingRange.collapsed) {
            targetElements = this.collectBlocksFromRange(workingRange, allBlocks);
        }

        if (targetElements.length === 0 && this.currentBlockEl) {
            targetElements = [this.currentBlockEl];
            if (debugSource === 'none') {
                debugSource = 'current_block';
            }
        }

        if (targetElements.length === 0) {
            this.showNotification('请先选中要缩进的段落', 'warning');
            this.logIndentDebug({
                source: debugSource,
                workingRange,
                targetElements,
                indentCount: 0,
                selectionInfo: {
                    exists: Boolean(selection),
                    rangeCount: selection?.rangeCount || 0,
                    isCollapsed: selection?.isCollapsed ?? null
                }
            });
            return;
        }

        const indent = '　　';  // 两个全角空格
        let indentCount = 0;
        const undoEntry = { type: 'indent', elements: [] };

        targetElements.forEach(el => {
            const originalHTML = el.innerHTML || '';
            let html = originalHTML;
            let modified = false;

            // 1. 处理元素开头（第一段）
            const textStart = (el.textContent || '').substring(0, 2);
            if (!textStart.startsWith('　') && !textStart.startsWith('  ')) {
                html = indent + html;
                modified = true;
            }

            // 2. 处理每个 <br> 后面的段落（后续段落的首行）
            const brPattern = /(<br\s*\/?>)(\s*)(?!　　|  )/gi;
            const newHtml = html.replace(brPattern, (match, brTag) => brTag + indent);

            if (newHtml !== html) {
                html = newHtml;
                modified = true;
            }

            if (modified) {
                undoEntry.elements.push({ element: el, previousHTML: originalHTML });
                el.innerHTML = html;
                indentCount++;
            }
        });

        if (indentCount > 0) {
            if (undoEntry.elements.length > 0) {
                this.pushOperation(undoEntry);
            }
            this.isDirty = true;
            this.scheduleAutoSave();
            this.showNotification(`已为 ${indentCount} 个段落添加首行缩进`, 'success');
        } else {
            this.showNotification('所选段落已有缩进', 'info');
        }

        this.logIndentDebug({
            source: debugSource,
            workingRange,
            targetElements,
            indentCount,
            selectionInfo: {
                exists: Boolean(selection),
                rangeCount: selection?.rangeCount || 0,
                isCollapsed: selection?.isCollapsed ?? null
            }
        });
    }

    collectBlocksFromRange(range, allBlocks) {
        if (!range) return [];

        const matched = [];
        const startBlock = this.getEditableBlockFromNode(range.startContainer);
        const endBlock = this.getEditableBlockFromNode(range.endContainer);

        // 只缩进真正与选区相交的段落/单元格，避免“中间未选中段落”被误缩进
        allBlocks.forEach(block => {
            if (this.rangeIntersectsElement(range, block)) {
                matched.push(block);
            }
        });

        if (matched.length === 0) {
            if (startBlock) matched.push(startBlock);
            if (endBlock && endBlock !== startBlock) matched.push(endBlock);
        }

        return matched;
    }

    getEditableBlockFromNode(node) {
        if (!node) return null;

        if (node.nodeType === Node.TEXT_NODE) {
            return node.parentElement ? node.parentElement.closest('.editor-block.editable, .editor-cell') : null;
        }

        if (node.nodeType === Node.ELEMENT_NODE) {
            const element = node;
            if (element.matches('.editor-block.editable, .editor-cell')) {
                return element;
            }
            return element.closest('.editor-block.editable, .editor-cell');
        }

        return null;
    }

    isRangeInsideEditor(range, editorEl) {
        if (!range || !editorEl) return false;
        try {
            return editorEl.contains(range.startContainer) && editorEl.contains(range.endContainer);
        } catch (error) {
            return false;
        }
    }

    rangeIntersectsElement(range, element) {
        if (!range || !element) return false;

        try {
            if (typeof range.intersectsNode === 'function') {
                return range.intersectsNode(element);
            }
        } catch (error) {
            // fall through to manual comparison
        }

        const doc = element.ownerDocument || document;
        const tempRange = doc.createRange();
        tempRange.selectNodeContents(element);

        const rangeEndsBeforeElementStarts = range.compareBoundaryPoints(Range.END_TO_START, tempRange) < 0;
        const rangeStartsAfterElementEnds = range.compareBoundaryPoints(Range.START_TO_END, tempRange) > 0;

        tempRange.detach?.();

        return !(rangeEndsBeforeElementStarts || rangeStartsAfterElementEnds);
    }

    logIndentDebug({ source, workingRange, targetElements, indentCount, selectionInfo }) {
        try {
            console.groupCollapsed('%c[AIEditor] 首行缩进调试', 'color:#8a2be2;font-weight:bold;');
            console.log('触发来源:', source);
            console.log('缩进段落数量:', indentCount);
            console.log('当前聚焦块:', this.currentBlockEl?.dataset?.blockId || null);
            console.log('保存的选区信息:', this.lastSelectionMeta);
            console.log('Selection 状态:', selectionInfo);
            if (workingRange) {
                console.log('Range collapsed:', workingRange.collapsed);
                const preview = (workingRange.toString() || '').replace(/\s+/g, ' ').trim().slice(0, 80);
                console.log('Range 文本预览:', preview);
            } else {
                console.log('无可用 Range');
            }
            const rows = targetElements.map((el, idx) => ({
                '#': idx + 1,
                blockId: el.dataset?.blockId || '(table-cell)',
                type: el.classList.contains('editor-cell') ? 'cell' : 'paragraph',
                preview: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
                hasIndent: (el.textContent || '').startsWith('　　') || (el.textContent || '').startsWith('  ')
            }));
            if (rows.length) {
                console.table(rows);
            } else {
                console.log('没有匹配到目标段落');
            }
            console.groupEnd();
        } catch (error) {
            console.error('首行缩进调试日志失败:', error);
        }
    }

    pushOperation(operation) {
        this.operationHistory.push(operation);
        if (this.operationHistory.length > this.maxHistory) {
            this.operationHistory.shift();
        }
    }

    undoLastAction() {
        if (this.operationHistory.length === 0) {
            this.showNotification('没有可撤回的操作', 'info');
            return;
        }

        const operation = this.operationHistory.pop();

        if (operation.type === 'indent') {
            operation.elements.forEach(item => {
                if (item.element) {
                    item.element.innerHTML = item.previousHTML;
                }
            });
        }

        this.isDirty = true;
        this.scheduleAutoSave();
        this.showNotification('已撤回上一步操作', 'success');
    }

    // ========== 清理Markdown格式功能 ==========
    cleanMarkdownFormat() {
        const selection = window.getSelection();

        // 确定要操作的元素
        let targetElements = [];

        if (selection.rangeCount > 0 && !selection.isCollapsed) {
            // 有选中文本
            const range = selection.getRangeAt(0);
            const editor = document.getElementById('documentEditor');
            const allBlocks = editor.querySelectorAll('.editor-block.editable, .editor-cell');

            for (const block of allBlocks) {
                if (range.intersectsNode(block)) {
                    targetElements.push(block);
                }
            }
        } else if (this.currentBlockEl) {
            // 无选中文本，使用当前聚焦的块
            targetElements.push(this.currentBlockEl);
        }

        if (targetElements.length === 0) {
            this.showNotification('请先选中要清理的内容', 'warning');
            return;
        }

        let cleanCount = 0;

        for (const el of targetElements) {
            const originalHtml = el.innerHTML;
            let html = originalHtml;

            // 1. 将 ##文字## 转换为加粗 <strong>文字</strong>
            // 匹配 ##...## 模式（非贪婪匹配），支持多行
            html = html.replace(/##([^#]+?)##/g, '<strong>$1</strong>');

            // 也处理纯文本中的情况（可能还没有被HTML化）
            // 匹配 textContent 中的 ##...## 并转换

            // 2. 删除单独的 # 标题标记（在行首或独立出现的）
            // 处理 HTML 中的情况：可能是 "# 标题" 或 "<br># 标题" 等
            // 匹配行首的 # 标记（1-6个#后跟空格）
            html = html.replace(/^(#{1,6})\s+/gm, '');
            html = html.replace(/<br\s*\/?>\s*(#{1,6})\s+/gi, '<br>');

            // 3. 删除独立的 # 符号（如果只是单个#没有内容）
            html = html.replace(/^#\s*$/gm, '');

            // 4. 处理可能遗留的多余 # 号（在文本中间的）
            // 只删除看起来像标题标记的 #（后面跟空格的情况）
            html = html.replace(/\n(#{1,6})\s+/g, '\n');

            // 5. 处理 **粗体** 格式（标准markdown加粗）
            html = html.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');

            // 6. 处理 *斜体* 格式（标准markdown斜体）
            html = html.replace(/\*([^*]+?)\*/g, '<em>$1</em>');

            if (html !== originalHtml) {
                el.innerHTML = html;
                cleanCount++;
            }
        }

        if (cleanCount > 0) {
            this.isDirty = true;
            this.scheduleAutoSave();
            this.showNotification(`已清理 ${cleanCount} 个段落的Markdown格式`, 'success');
        } else {
            this.showNotification('未发现需要清理的Markdown格式', 'info');
        }
    }

    // 自动清理从LLM返回的内容（用于插入时自动处理）
    autoCleanLLMContent(content) {
        if (!content) return content;

        let cleaned = content;

        // 1. 将 ##文字## 转换为 **文字**（保留为markdown格式，后续插入时再处理）
        // 或者直接处理为纯文本+标记
        cleaned = cleaned.replace(/##([^#]+)##/g, '【$1】');  // 临时用【】标记加粗部分

        // 2. 删除标题标记 # 
        cleaned = cleaned.replace(/^(#{1,6})\s+/gm, '');
        cleaned = cleaned.replace(/\n(#{1,6})\s+/g, '\n');

        return cleaned;
    }

    // 清理LLM返回的Markdown格式（用于插入到文档前的处理）
    // 返回处理后的纯文本（移除所有markdown标记）
    cleanLLMMarkdown(content) {
        if (!content) return content;

        let cleaned = content;

        // 1. 删除行首的 # 标题标记（1-6个#后跟空格）
        cleaned = cleaned.replace(/^(#{1,6})\s+/gm, '');

        // 2. 处理 ##文字## 格式 - 直接移除##标记，保留文字
        cleaned = cleaned.replace(/##([^#]+?)##/g, '$1');

        // 3. 处理 **粗体** 格式 - 移除**标记，保留文字
        cleaned = cleaned.replace(/\*\*([^*]+?)\*\*/g, '$1');

        // 4. 处理 *斜体* 格式 - 移除*标记，保留文字
        cleaned = cleaned.replace(/\*([^*]+?)\*/g, '$1');

        // 5. 删除可能残留的独立 # 
        cleaned = cleaned.replace(/\s#\s/g, ' ');

        // 6. 处理 `代码` 格式 - 移除`标记，保留文字
        cleaned = cleaned.replace(/`([^`]+?)`/g, '$1');

        // 7. 统一换行符，并移除多余空行
        cleaned = cleaned.replace(/\r\n/g, '\n');
        cleaned = cleaned.replace(/\n\s*\n+/g, '\n');

        // 8. 去除首尾多余空白
        cleaned = cleaned.trim();

        return cleaned;
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
                // Tab键 - 应用建议或触发补全
                if (e.key === 'Tab' && !e.shiftKey) {
                    e.preventDefault();
                    // 如果有当前建议，直接应用
                    if (this.inlineSuggestion) {
                        this.applyInlineSuggestion(el);
                    } else {
                        // 否则触发完整补全
                        this.triggerAutoComplete(el);
                    }
                }
                // Escape键 - 取消建议
                if (e.key === 'Escape') {
                    this.clearInlineSuggestion();
                }
                // 回车键检测@@@占位符
                if (e.key === 'Enter' && !e.shiftKey) {
                    const handled = this.checkAndTriggerPlaceholder(el);
                    if (handled) {
                        e.preventDefault();
                    }
                    // 清除建议
                    this.clearInlineSuggestion();
                }
            });

            // 输入事件 - 触发实时建议
            el.addEventListener('input', (e) => {
                this.scheduleInlineSuggestion(el);
            });

            // 失去焦点时清除建议
            el.addEventListener('blur', (e) => {
                // 延迟清除，以便Tab键有机会先应用建议
                setTimeout(() => {
                    this.clearInlineSuggestion();
                }, 100);
            });
        });

        // 选中文本检测 - 显示悬浮按钮
        document.getElementById('documentEditor').addEventListener('mouseup', (e) => {
            // 延迟检测，确保选区已经稳定
            setTimeout(() => {
                this.handleTextSelection(e);
            }, 10);
        });

        // 点击文档时清除建议（如果点击位置不在建议元素内）
        document.getElementById('documentEditor').addEventListener('mousedown', (e) => {
            if (this.suggestionElement && !this.suggestionElement.contains(e.target)) {
                this.clearInlineSuggestion();
            }
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

        this.monitorSelectionChanges();
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
        // 使用全文上下文，便于识别标题等全局信息
        const docContext = this.getFullDocumentText();

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
                    document_context: docContext
                })
            });

            const data = await response.json();

            if (data.success && data.content) {
                // 🔧 修复：保持换行格式，并清理markdown
                // 先清理LLM返回的markdown格式
                const cleanedContent = this.cleanLLMMarkdown(data.content);

                // 1. 获取原始HTML，找到@@@占位符的位置
                const placeholderIndex = originalHTML.lastIndexOf(this.escapeHtml(placeholder));

                if (placeholderIndex !== -1) {
                    // 2. 分割HTML: 之前的部分 + 生成的内容
                    const htmlBefore = originalHTML.substring(0, placeholderIndex);
                    // 将生成内容中的换行转换为<br>
                    const generatedContentHTML = this.escapeHtml(cleanedContent).replace(/\n/g, '<br>');
                    el.innerHTML = htmlBefore + generatedContentHTML;
                } else {
                    // 降级方案：如果找不到占位符，使用textContent
                    el.textContent = contextBefore + cleanedContent;
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

    // ========== 实时行内建议功能 ==========

    // 调度实时建议请求（带防抖）
    scheduleInlineSuggestion(el) {
        // 清除之前的定时器
        if (this.suggestionDebounceTimer) {
            clearTimeout(this.suggestionDebounceTimer);
        }

        // 取消正在进行的请求
        if (this.suggestionAbortController) {
            this.suggestionAbortController.abort();
        }

        // 清除当前建议
        this.clearInlineSuggestion();

        // 获取光标前的文本
        const selection = window.getSelection();
        if (!selection.rangeCount) return;

        const range = selection.getRangeAt(0);
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(el);
        preCaretRange.setEnd(range.endContainer, range.endOffset);
        const textBeforeCursor = preCaretRange.toString();

        // 文本太短不触发
        if (textBeforeCursor.trim().length < 5) return;

        // 避免重复请求相同文本
        if (textBeforeCursor === this.lastSuggestionText) return;

        // 防抖延迟800ms
        this.suggestionDebounceTimer = setTimeout(() => {
            this.fetchInlineSuggestion(el, textBeforeCursor);
        }, 800);
    }

    // 获取实时建议
    async fetchInlineSuggestion(el, textBeforeCursor) {
        if (this.isCompletionLoading) return;

        this.lastSuggestionText = textBeforeCursor;
        this.suggestionAbortController = new AbortController();

        try {
            // 提取文档标题（第一行非空文本）
            const fullText = this.getDocumentText();
            let documentTitle = '';
            if (fullText) {
                const lines = fullText.split(/\r?\n/);
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed) {
                        documentTitle = trimmed.slice(0, 50);
                        break;
                    }
                }
            }

            const response = await fetch('/api/ai/inline-suggest', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    text_before: textBeforeCursor,
                    document_title: documentTitle
                }),
                signal: this.suggestionAbortController.signal
            });

            const data = await response.json();

            if (data.success && data.suggestion) {
                // 检查光标是否仍在该元素内
                const currentSelection = window.getSelection();
                if (currentSelection.rangeCount > 0) {
                    const currentRange = currentSelection.getRangeAt(0);
                    let container = currentRange.commonAncestorContainer;
                    while (container && container !== el) {
                        container = container.parentElement;
                    }
                    if (container === el) {
                        this.showInlineSuggestion(el, data.suggestion);
                    }
                }
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.log('获取建议失败:', error);
            }
        }
    }

    // 显示行内建议（灰色提示）
    showInlineSuggestion(el, suggestion) {
        this.clearInlineSuggestion();

        if (!suggestion) return;

        this.inlineSuggestion = suggestion;

        // 获取当前光标位置
        const selection = window.getSelection();
        if (!selection.rangeCount) return;

        const range = selection.getRangeAt(0);

        // 创建建议元素
        this.suggestionElement = document.createElement('span');
        this.suggestionElement.className = 'inline-suggestion';
        this.suggestionElement.textContent = suggestion;
        this.suggestionElement.style.cssText = `
            color: #999;
            opacity: 0.6;
            pointer-events: none;
            user-select: none;
        `;

        // 在光标位置插入建议
        range.insertNode(this.suggestionElement);

        // 将光标移回建议元素之前
        range.setStartBefore(this.suggestionElement);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    // 清除行内建议
    clearInlineSuggestion() {
        if (this.suggestionElement && this.suggestionElement.parentNode) {
            this.suggestionElement.parentNode.removeChild(this.suggestionElement);
        }
        this.suggestionElement = null;
        this.inlineSuggestion = '';
    }

    // 应用行内建议
    applyInlineSuggestion(el) {
        if (!this.inlineSuggestion || !this.suggestionElement) return;

        const suggestion = this.inlineSuggestion;

        // 移除建议元素的样式，使其成为正常文本
        this.suggestionElement.style.cssText = '';
        this.suggestionElement.className = '';

        // 将光标移到建议文本末尾
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(this.suggestionElement);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);

        // 清除状态
        this.suggestionElement = null;
        this.inlineSuggestion = '';
        this.lastSuggestionText = '';

        this.isDirty = true;
        this.scheduleAutoSave();
        this.showNotification('已应用建议', 'success');
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

        // 提取文档标题（第一行非空文本）
        let documentTitle = '';
        if (fullContext) {
            const lines = fullContext.split(/\r?\n/);
            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed) {
                    documentTitle = trimmed.slice(0, 50);
                    break;
                }
            }
        }

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
                    full_context: fullContext.substring(0, 1500),
                    document_title: documentTitle
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
    }

    monitorSelectionChanges() {
        if (this.selectionMonitorInitialized) return;
        document.addEventListener('selectionchange', () => {
            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) return;
            const range = selection.getRangeAt(0);
            if (!range || range.collapsed) return;
            const editor = document.getElementById('documentEditor');
            if (!editor) return;
            if (!editor.contains(range.startContainer) || !editor.contains(range.endContainer)) {
                return;
            }
            try {
                this.savedSelection = range.cloneRange();
                const startBlock = this.getEditableBlockFromNode(range.startContainer);
                const endBlock = this.getEditableBlockFromNode(range.endContainer);
                this.lastSelectionMeta = {
                    startBlockId: startBlock?.dataset?.blockId || null,
                    endBlockId: endBlock?.dataset?.blockId || null,
                    textPreview: (range.toString() || '').replace(/\s+/g, ' ').trim().slice(0, 60),
                    updatedAt: new Date().toISOString()
                };
            } catch (error) {
                console.warn('Selection monitor failed:', error);
            }
        });
        this.selectionMonitorInitialized = true;
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
                let billingSuffix = '';
                if (data.billing_info) {
                    const b = data.billing_info;
                    const icon = b.is_free ? '✨' : '💎';
                    const color = b.is_free ? '#10a37f' : '#f59e0b';
                    billingSuffix = `<br><span style="font-size:12px; color:${color}; opacity:0.8; margin-top:4px; display:inline-block;">(${icon} ${b.message})</span>`;
                }

                if (data.generated_content) {
                    this.lastGeneratedContent = data.generated_content;
                    this.lastTargetField = data.target_field || null;  // 保存目标字段
                    this.addChatMessageWithInsert(data.response + billingSuffix, data.generated_content, data.target_field);
                } else {
                    this.addChatMessage(data.response + billingSuffix, 'ai');
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

    // 获取用于大模型调用的全文本（不截断）
    getFullDocumentText() {
        const editor = document.getElementById('documentEditor');
        return editor ? editor.textContent : '';
    }

    // 获取用于补全/建议等轻量场景的截断文本
    getDocumentText() {
        const editor = document.getElementById('documentEditor');
        return editor ? editor.textContent.substring(0, 2000) : '';
    }

    // 渲染Markdown到指定容器（用于AI助手消息）
    renderMarkdown(container, text) {
        if (!container) return;
        const safeText = text || '';
        try {
            if (window.marked && typeof window.marked.parse === 'function') {
                container.innerHTML = window.marked.parse(safeText);
            } else {
                container.textContent = safeText;
            }
        } catch (e) {
            console.warn('Markdown 渲染失败，回退为纯文本:', e);
            container.textContent = safeText;
        }
    }

    addChatMessage(text, role, isLoading = false) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        const msgId = 'msg-' + Date.now();
        div.id = msgId;
        div.className = `chat-message ${role}${isLoading ? ' loading' : ''}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (role === 'ai' && !isLoading) {
            // AI回复使用Markdown渲染
            this.renderMarkdown(contentDiv, text);
        } else {
            // 用户消息和loading提示使用纯文本
            contentDiv.textContent = text;
        }

        div.appendChild(contentDiv);
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return msgId;
    }

    removeChatMessage(msgId) {
        const msg = document.getElementById(msgId);
        if (msg) msg.remove();
    }

    // 添加带有"插入文档"按钮的AI消息
    addChatMessageWithInsert(responseText, generatedContent, targetField = null) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        div.className = 'chat-message ai with-actions';

        // 构建插入按钮的参数
        const insertArgs = targetField
            ? `'${this.escapeAttr(generatedContent)}', '${this.escapeAttr(targetField)}'`
            : `'${this.escapeAttr(generatedContent)}'`;

        // 按钮文本：如果有目标字段则显示"智能插入"
        const insertBtnText = targetField ? `智能插入到「${targetField}」` : '插入到文档';

        div.innerHTML = `
            <div class="message-content"></div>
            <div class="generated-content-preview">
                <div class="preview-label">生成的内容：</div>
                <div class="preview-text"></div>
            </div>
            <div class="message-actions">
                <button class="insert-btn" onclick="aiEditor.insertGeneratedContent(${insertArgs})">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 5v14M5 12h14"/>
                    </svg>
                    ${insertBtnText}
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

        // 渲染AI说明为Markdown
        const msgContentEl = div.querySelector('.message-content');
        this.renderMarkdown(msgContentEl, responseText);

        // 生成内容预览使用纯文本（便于与最终插入内容一致）
        const previewTextEl = div.querySelector('.preview-text');
        previewTextEl.textContent = generatedContent;

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    escapeAttr(str) {
        return str.replace(/'/g, "\\'").replace(/\n/g, '\\n');
    }

    // 插入生成的内容到文档
    insertGeneratedContent(content, targetField = null) {
        // 还原转义的换行符
        content = content.replace(/\\n/g, '\n').replace(/\\'/g, "'");
        // 清理LLM返回的markdown格式
        content = this.cleanLLMMarkdown(content);

        // 如果有目标字段，尝试智能识别位置
        if (targetField) {
            const targetEl = this.findTargetElement(targetField);
            if (targetEl) {
                this.insertContentToElement(targetEl, content, targetField);
                return;
            } else {
                console.log(`未找到目标字段「${targetField}」，使用默认插入方式`);
            }
        }

        // 默认行为：插入到当前聚焦的块或创建新段落
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

    // 查找包含目标字段标题的元素
    findTargetElement(targetField) {
        const editor = document.getElementById('documentEditor');
        if (!editor) return null;

        // 构建可能的匹配模式
        // 如：二、构思与内容  或  构思与内容
        const chineseNumbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
        const patterns = [
            targetField,                           // 直接匹配：构思与内容
        ];
        // 添加带序号的模式
        for (const num of chineseNumbers) {
            patterns.push(`${num}、${targetField}`);  // 匹配：二、构思与内容
        }

        // 在表格单元格中搜索
        const cells = editor.querySelectorAll('.editor-cell');
        for (const cell of cells) {
            const text = cell.textContent || '';
            for (const pattern of patterns) {
                if (text.includes(pattern)) {
                    console.log(`找到目标单元格，包含「${pattern}」`);
                    return cell;
                }
            }
        }

        // 在段落中搜索
        const blocks = editor.querySelectorAll('.editor-block.editable');
        for (const block of blocks) {
            const text = block.textContent || '';
            for (const pattern of patterns) {
                if (text.includes(pattern)) {
                    console.log(`找到目标段落，包含「${pattern}」`);
                    return block;
                }
            }
        }

        return null;
    }

    // 将内容插入到目标元素
    insertContentToElement(el, content, targetField) {
        // 获取当前内容
        const currentText = el.textContent || '';
        const currentHtml = el.innerHTML || '';

        // 判断当前内容的结构
        // 如果是 "二、构思与内容<br>" 这样的格式，需要在标题后追加内容
        // 检查是否只有标题（如"二、构思与内容"或只有换行）
        const chineseNumbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
        let titleEndIndex = -1;
        let foundTitle = '';

        for (const num of chineseNumbers) {
            const titlePattern = `${num}、${targetField}`;
            const idx = currentText.indexOf(titlePattern);
            if (idx !== -1) {
                // 找到标题后的位置
                titleEndIndex = idx + titlePattern.length;
                foundTitle = titlePattern;
                break;
            }
        }

        // 将内容转换为HTML格式（保持换行）
        const contentHtml = this.escapeHtml(content).replace(/\n/g, '<br>');

        if (titleEndIndex !== -1) {
            // 找到了标题，检查标题后是否有实际内容
            const afterTitle = currentText.substring(titleEndIndex).trim();

            if (!afterTitle) {
                // 标题后没有内容，直接在现有HTML后追加
                // 不重建HTML，只追加内容
                const needsBr = !currentHtml.endsWith('<br>') && !currentHtml.endsWith('<br/>');
                el.innerHTML = currentHtml + (needsBr ? '<br>' : '') + contentHtml;
                this.showNotification(`已智能插入到「${targetField}」`, 'success');
            } else {
                // 标题后已有内容，追加到末尾
                const needsBr = !currentHtml.endsWith('<br>') && !currentHtml.endsWith('<br/>');
                el.innerHTML = currentHtml + (needsBr ? '<br>' : '') + contentHtml;
                this.showNotification(`已追加内容到「${targetField}」`, 'success');
            }
        } else {
            // 没有找到标题，直接追加
            const needsBr = !currentHtml.endsWith('<br>') && !currentHtml.endsWith('<br/>');
            el.innerHTML = currentHtml + (needsBr ? '<br>' : '') + contentHtml;
            this.showNotification(`已插入内容到目标位置`, 'success');
        }

        this.isDirty = true;
        this.scheduleAutoSave();

        // 聚焦到该元素
        el.focus();
        this.currentBlockEl = el;
        this.currentBlockId = el.dataset.blockId || el.closest('table')?.dataset.blockId;
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

        // 获取上下文：选中文本所在段落/单元格的内容
        let contextBefore = '';
        let contextAfter = '';

        if (this.savedSelection) {
            try {
                const range = this.savedSelection;
                const container = range.commonAncestorContainer;

                // 找到最近的可编辑块（段落或单元格）
                let editableBlock = container;
                while (editableBlock && !editableBlock.classList?.contains('editor-block') &&
                    !editableBlock.classList?.contains('editor-cell')) {
                    editableBlock = editableBlock.parentElement;
                }

                if (editableBlock) {
                    const fullText = editableBlock.textContent || '';
                    const selectedText = this.selectedText;
                    const selectionStart = fullText.indexOf(selectedText);

                    if (selectionStart !== -1) {
                        // 获取选中文本前后的上下文（各最多200字符）
                        contextBefore = fullText.substring(Math.max(0, selectionStart - 200), selectionStart);
                        contextAfter = fullText.substring(selectionStart + selectedText.length,
                            selectionStart + selectedText.length + 200);
                    }
                }
            } catch (e) {
                console.log('获取上下文失败:', e);
            }
        }

        try {
            const response = await fetch('/api/ai/rewrite', {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({
                    session_id: this.sessionId,
                    selected_text: this.selectedText,
                    instruction: instruction,
                    context_before: contextBefore,
                    context_after: contextAfter,
                    document_context: this.getDocumentText().substring(0, 1500)
                })
            });

            const data = await response.json();

            if (data.success) {
                this.rewriteResult = data.rewritten;
                document.getElementById('floatingResultText').textContent = data.rewritten;
                document.getElementById('floatingResultArea').style.display = 'block';
                document.getElementById('floatingApplyBtn').style.display = 'inline-flex';
                btn.style.display = 'none';

                if (data.billing_info) {
                    const b = data.billing_info;
                    this.showNotification(`重写成功 ${b.is_free ? '✨' : '💎'} ${b.message}`, b.is_free ? 'success' : 'info');
                }
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

            // 插入新内容 - 保持换行格式
            // 先清理LLM返回的markdown格式
            let content = this.cleanLLMMarkdown(this.rewriteResult);
            const lines = content.split('\n');
            const fragment = document.createDocumentFragment();

            for (let i = 0; i < lines.length; i++) {
                if (i > 0) {
                    // 在行之间插入 <br> 元素
                    fragment.appendChild(document.createElement('br'));
                }
                if (lines[i]) {
                    fragment.appendChild(document.createTextNode(lines[i]));
                }
            }

            range.insertNode(fragment);

            // 将光标移动到新插入内容的末尾
            range.collapse(false);

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
