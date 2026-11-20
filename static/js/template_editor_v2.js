/**
 * 模板编辑器 V2 - 上传Word并插入标签
 */

class TemplateEditorApp {
    constructor() {
        this.sessionId = null;
        this.filename = null;
        this.filepath = null;  // 存储文档路径用于渲染
        this.structure = null;
        this.selectedLocation = null;
        this.insertedTags = [];
        this.tags = [];
        
        this.init();
    }
    
    async init() {
        console.log('📝 模板编辑器初始化...');
        
        // 检查认证状态
        if (!await this.checkAuthStatus()) {
            return; // 如果认证失败，会跳转到登录页面
        }
        
        await this.loadTags();
        this.setupDragDrop();
        
        // 检查是否有从主页传来的文件
        const uploadedFile = sessionStorage.getItem('uploadedFile');
        const uploadedFilePath = sessionStorage.getItem('uploadedFilePath');
        
        if (uploadedFile && uploadedFilePath) {
            console.log('📄 检测到已上传的文件:', uploadedFile);
            // 自动加载该文件
            await this.loadExistingFile(uploadedFile, uploadedFilePath);
            // 清除sessionStorage
            sessionStorage.removeItem('uploadedFile');
            sessionStorage.removeItem('uploadedFilePath');
        }
    }
    
    /**
     * 检查认证状态
     */
    async checkAuthStatus() {
        const authToken = sessionStorage.getItem('auth_token');
        if (!authToken) {
            this.redirectToLogin();
            return false;
        }
        
        try {
            const response = await fetch('/api/auth/verify', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            });
            
            if (!response.ok) {
                this.redirectToLogin();
                return false;
            }
            
            const result = await response.json();
            if (!result.success || !result.valid) {
                this.redirectToLogin();
                return false;
            }
            
            return true;
        } catch (error) {
            console.error('认证检查失败:', error);
            this.redirectToLogin();
            return false;
        }
    }
    
    /**
     * 跳转到登录页面
     */
    redirectToLogin() {
        window.location.href = '/login';
    }
    
    /**
     * 发送API请求（自动添加认证头）
     */
    async apiRequest(url, options = {}) {
        const authToken = sessionStorage.getItem('auth_token');
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...(authToken && { 'Authorization': `Bearer ${authToken}` })
            }
        };
        
        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        };
        
        try {
            const response = await fetch(url, mergedOptions);
            
            // 如果返回401，说明认证失败，跳转到登录页面
            if (response.status === 401) {
                this.redirectToLogin();
                throw new Error('认证失败，请重新登录');
            }
            
            return response;
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    /**
     * 加载可用标签
     */
    async loadTags() {
        try {
            const response = await this.apiRequest('/api/template-editor/tags');
            const data = await response.json();
            
            if (data.success) {
                this.tags = data.categories;
                console.log(`✅ 加载了 ${data.total} 个标签`);
            }
        } catch (error) {
            console.error('❌ 加载标签失败:', error);
            this.showNotification('加载标签失败', 'error');
        }
    }
    
    /**
     * 设置拖拽上传
     */
    setupDragDrop() {
        const uploadBox = document.getElementById('uploadBox');
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadBox.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadBox.addEventListener(eventName, () => {
                uploadBox.classList.add('drag-over');
            });
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            uploadBox.addEventListener(eventName, () => {
                uploadBox.classList.remove('drag-over');
            });
        });
        
        uploadBox.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileUpload(files[0]);
            }
        });
    }
    
    /**
     * 加载已存在的文件（从主页传来）
     */
    async loadExistingFile(filename, filepath) {
        try {
            console.log('📤 开始加载文件:', filename, filepath);
            this.showLoading('正在加载您上传的模板...');
            
            const response = await this.apiRequest('/api/template-editor/load-existing', {
                method: 'POST',
                body: JSON.stringify({
                    filename: filename,
                    filepath: filepath
                })
            });
            
            const data = await response.json();
            console.log('📥 服务器响应:', data);
            
            this.hideLoading();
            
            if (data.success) {
                this.sessionId = data.session_id;
                this.filename = data.filename;
                this.structure = data.structure;
                this.filepath = data.filepath;  // 保存文件路径
                
                console.log('✅ 文档结构:', this.structure);
                console.log('📁 文件路径:', this.filepath);
                
                this.showNotification('已加载您的模板！', 'success');
                this.switchToEditMode();
            } else {
                console.error('❌ 加载失败:', data.error);
                this.showNotification(data.error || '加载失败', 'error');
            }
        } catch (error) {
            this.hideLoading();
            console.error('❌ 加载文件失败:', error);
            this.showNotification('加载失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 处理文件上传
     */
    async handleFileUpload(file) {
        if (!file) return;
        
        if (!file.name.endsWith('.docx')) {
            this.showNotification('只支持.docx格式的Word文档', 'error');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            this.showLoading('正在上传和分析文档...');
            
            const response = await this.apiRequest('/api/template-editor/upload', {
                method: 'POST',
                body: formData,
                headers: {} // 文件上传不需要Content-Type头
            });
            
            const data = await response.json();
            
            this.hideLoading();
            
            if (data.success) {
                this.sessionId = data.session_id;
                this.filename = data.filename;
                this.structure = data.structure;
                this.filepath = data.filepath;  // 保存文件路径
                
                this.showNotification('文档上传成功！', 'success');
                this.switchToEditMode();
            } else {
                this.showNotification(data.error || '上传失败', 'error');
            }
        } catch (error) {
            this.hideLoading();
            console.error('上传失败:', error);
            this.showNotification('上传失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 切换到编辑模式
     */
    switchToEditMode() {
        console.log('🔄 切换到编辑模式');
        // 更新步骤指示器（如果存在）
        const step1 = document.getElementById('step1');
        const step2 = document.getElementById('step2');
        const step3 = document.getElementById('step3');

        if (step1) {
            step1.classList.remove('active');
            step1.classList.add('completed');
        }
        if (step2) {
            step2.classList.add('active');
        }
        if (step3) {
            step3.classList.remove('active');
        }

        // 隐藏上传区，显示编辑区
        document.getElementById('uploadSection').style.display = 'none';
        document.getElementById('editSection').style.display = 'flex';

        // 显示文件信息
        const fileInfo = document.getElementById('fileInfo');
        if (fileInfo) {
            fileInfo.innerHTML = `
                <span>📄 ${this.filename}</span>
                <span>段落: ${this.structure.total_paragraphs || 0}</span>
                <span>表格: ${this.structure.total_tables || 0}</span>
            `;
        }

        // 渲染标签面板
        this.renderTags();

        // 渲染Word文档
        this.renderWordDocument();

        // 启用下载按钮
        const downloadBtn = document.getElementById('downloadBtn');
        if (downloadBtn) {
            downloadBtn.disabled = false;
        }
    }
    
    /**
     * 使用Mammoth.js渲染Word文档
     */
    async renderWordDocument(preserveScroll = false) {
        const viewer = document.getElementById('documentViewer');
        
        // 保存当前滚动位置
        const scrollPosition = preserveScroll ? viewer.scrollTop : 0;
        
        viewer.innerHTML = '<div class="loading">正在加载Word文档...</div>';
        
        try {
            // 获取文档文件
            const response = await this.apiRequest(`/api/template-editor/get-file/${this.sessionId}/${this.filename}`);
            const blob = await response.blob();
            const arrayBuffer = await blob.arrayBuffer();
            
            // 使用mammoth渲染
            const result = await mammoth.convertToHtml({arrayBuffer: arrayBuffer}, {
                styleMap: [
                    "p[style-name='Heading 1'] => h1:fresh",
                    "p[style-name='Heading 2'] => h2:fresh",
                    "p[style-name='Heading 3'] => h3:fresh",
                ]
            });
            
            viewer.innerHTML = result.value;
            
            // 为段落和表格单元格添加点击事件
            this.addClickHandlersToDocument();
            
            // 恢复滚动位置
            if (preserveScroll && scrollPosition > 0) {
                setTimeout(() => {
                    viewer.scrollTop = scrollPosition;
                }, 100);
            }
            
            console.log('✅ Word文档渲染完成');
            
        } catch (error) {
            console.error('❌ 渲染Word文档失败:', error);
            viewer.innerHTML = `
                <div class="error-state">
                    <p>⚠️ 无法渲染Word文档</p>
                    <p style="font-size: 13px; color: var(--secondary-text);">${error.message}</p>
                </div>
            `;
        }
    }
    
    /**
     * 为渲染后的文档添加点击事件和data属性
     * 注意：Mammoth.js渲染的单元格顺序与python-docx的row.cells顺序一致
     */
    addClickHandlersToDocument() {
        const viewer = document.getElementById('documentViewer');
        
        // 首先统计主体段落（不在表格内的段落）
        let mainParaIndex = 0;
        const allElements = viewer.querySelectorAll('p, h1, h2, h3, table');
        
        console.log(`🔍 前端文档结构分析:`);
        console.log(`   总元素数: ${allElements.length}`);
        
        allElements.forEach((element, elementIndex) => {
            if (element.tagName === 'TABLE') {
                // 处理表格
                const tableIndex = Array.from(viewer.querySelectorAll('table')).indexOf(element);
                element.setAttribute('data-table-index', tableIndex);
                
                console.log(`📊 元素${elementIndex}: 表格 ${tableIndex}`);
                
                const rows = element.querySelectorAll('tr');
                rows.forEach((row, rowIndex) => {
                    const cells = row.querySelectorAll('td, th');
                    
                    // 🔥 关键修复：计算真实的python-docx列索引（考虑colspan）
                    let realColIndex = 0;  // python-docx的真实列索引（单元格起始位置）
                    
                    cells.forEach((cell, htmlColIndex) => {
                        const colspan = parseInt(cell.getAttribute('colspan') || '1');
                        const currentColIndex = realColIndex;  // 🔥 捕获当前单元格的起始索引
                        
                        // 给每个单元格添加data属性
                        cell.setAttribute('data-table-index', tableIndex);
                        cell.setAttribute('data-row-index', rowIndex);
                        cell.setAttribute('data-col-index', currentColIndex);  // 使用当前起始索引
                        cell.setAttribute('data-element-type', 'table');
                        cell.setAttribute('data-html-col', htmlColIndex);  // 保存HTML列索引用于调试
                        cell.setAttribute('data-colspan', colspan);
                        
                        cell.style.cursor = 'pointer';
                        cell.style.transition = 'all 0.2s';
                        cell.style.padding = '8px';
                        
                        // 🔥 视觉提示：空白单元格用绿色边框，有内容的用灰色边框
                        const cellText = cell.textContent.trim();
                        const isEmpty = !cellText || cellText.startsWith('{{');
                        if (isEmpty) {
                            cell.style.border = '2px dashed #10a37f';  // 绿色虚线表示空白
                            cell.style.background = 'rgba(16, 163, 127, 0.02)';
                        } else {
                            cell.style.border = '1px solid #ddd';  // 灰色实线表示有内容
                        }
                        
                        cell.addEventListener('mouseenter', () => {
                            cell.style.background = 'rgba(16, 163, 127, 0.08)';
                        });
                        
                        cell.addEventListener('mouseleave', () => {
                            if (!cell.classList.contains('selected')) {
                                cell.style.background = 'transparent';
                            }
                        });
                        
                        cell.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const cellText = cell.textContent.trim().substring(0, 20);
                            console.log(`🖱️ 点击表格单元格: 表格${tableIndex} 行${rowIndex} HTML列${htmlColIndex} → 真实列${currentColIndex} (colspan=${colspan}, 文本: "${cellText}")`);
                            this.selectDocumentElement('table', tableIndex, cell, rowIndex, currentColIndex);
                        });
                        
                        // 累加真实列索引（下一个单元格的起始位置）
                        realColIndex += colspan;
                    });
                });
                
                console.log(`   └─ ${rows.length}行`);
                
            } else {
                // 处理主体段落（不在表格内的）
                const isInTable = element.closest('table') !== null;
                
                if (!isInTable) {
                    const paraText = element.textContent.trim().substring(0, 30);
                    const currentIndex = mainParaIndex;  // 🔥 关键修复：捕获当前索引值
                    
                    console.log(`📝 元素${elementIndex}: 段落 ${currentIndex} (文本: "${paraText}")`);
                    
                    // 只有不在表格内的段落才算主体段落
                    element.setAttribute('data-para-index', currentIndex);
                    element.setAttribute('data-element-type', 'paragraph');
                    
                    element.style.cursor = 'pointer';
                    element.style.padding = '8px';
                    element.style.borderRadius = '4px';
                    element.style.transition = 'all 0.2s';
                    
                    element.addEventListener('mouseenter', () => {
                        element.style.background = 'rgba(16, 163, 127, 0.05)';
                    });
                    
                    element.addEventListener('mouseleave', () => {
                        if (!element.classList.contains('selected')) {
                            element.style.background = 'transparent';
                        }
                    });
                    
                    element.addEventListener('click', () => {
                        console.log(`🖱️ 点击段落: 段落${currentIndex} (文本: "${paraText}")`);
                        // 🔥 关键修复：同时发送段落文本用于后端定位
                        this.selectDocumentElement('paragraph', currentIndex, element, null, null, paraText);  // 使用捕获的值
                    });
                    
                    mainParaIndex++;
                }
            }
        });
        
        console.log(`\n✅ 文档结构加载完成:`);
        console.log(`   📝 主体段落: ${mainParaIndex}个`);
        console.log(`   📊 表格: ${viewer.querySelectorAll('table').length}个`);
    }
    
    /**
     * 选择文档中的元素并弹出标签选择器
     */
    selectDocumentElement(type, index, element, row = null, col = null, text = null) {
        // 移除之前的选中状态
        const viewer = document.getElementById('documentViewer');
        viewer.querySelectorAll('.selected').forEach(el => {
            el.classList.remove('selected');
            el.style.background = 'transparent';
            el.style.border = 'none';
        });
        
        // 添加选中状态
        element.classList.add('selected');
        element.style.background = 'rgba(16, 163, 127, 0.15)';
        element.style.border = '2px solid var(--primary-color)';
        
        // 保存选中位置
        this.selectedLocation = { type, index };
        
        // 🔥 对于段落，保存文本用于后端定位
        if (type === 'paragraph' && text) {
            this.selectedLocation.text = text;
        }
        
        // 更新弹窗中的位置信息
        const modalLocation = document.getElementById('modalLocation');
        if (type === 'table') {
            this.selectedLocation.row = row;
            this.selectedLocation.col = col;
            modalLocation.textContent = `表格 ${index + 1} [行${row + 1}, 列${col + 1}]`;
        } else {
            modalLocation.textContent = `段落 ${index + 1}`;
        }
        
        console.log('选中位置:', this.selectedLocation);
        
        // 显示标签选择弹窗
        this.openTagSelector();
    }
    
    /**
     * 打开标签选择器
     */
    openTagSelector() {
        const modal = document.getElementById('tagSelectorModal');
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // 防止背景滚动
    }
    
    /**
     * 关闭标签选择器
     */
    closeTagSelector() {
        const modal = document.getElementById('tagSelectorModal');
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
    
    /**
     * 渲染完整文档预览（旧方法，保留备用）
     */
    renderStructure() {
        const container = document.getElementById('structureContent');
        
        if (!this.structure) {
            container.innerHTML = '<div class="empty-state">文档结构未加载</div>';
            console.error('❌ structure 为空');
            return;
        }
        
        console.log('📄 开始渲染文档结构:', this.structure);
        
        let html = '<div class="document-preview">';
        
        // 按顺序渲染所有元素
        if (this.structure.elements && this.structure.elements.length > 0) {
            this.structure.elements.forEach((element, idx) => {
                if (element.type === 'paragraph') {
                    // 渲染段落
                    const text = element.text || '(空白段落)';
                    const isEmpty = !element.text.trim();
                    html += `
                        <div class="doc-paragraph ${isEmpty ? 'empty-para' : ''}" 
                             data-type="paragraph" 
                             data-index="${element.index}"
                             onclick="app.selectLocation('paragraph', ${element.index}, null, null, event)"
                             title="点击选择此段落插入标签">
                            <div class="element-badge">段落 ${element.index + 1}</div>
                            <div class="para-content">${text}</div>
                        </div>
                    `;
                } else if (element.type === 'table') {
                    // 渲染表格
                    html += `
                        <div class="doc-table-wrapper">
                            <div class="table-badge">表格 ${element.index + 1} (${element.rows}×${element.cols})</div>
                            <table class="doc-table">
                    `;
                    
                    // 渲染表格行
                    element.cells.forEach((row, rowIdx) => {
                        html += '<tr>';
                        row.forEach(cell => {
                            const text = cell.text || '';
                            const isEmpty = cell.is_empty;
                            const displayText = text || '(空白)';
                            
                            html += `
                                <td class="doc-table-cell ${isEmpty ? 'empty-cell' : ''}" 
                                    data-type="table"
                                    data-table="${element.index}"
                                    data-row="${cell.row}"
                                    data-col="${cell.col}"
                                    onclick="app.selectLocation('table', ${element.index}, ${cell.row}, ${cell.col}, event)"
                                    title="点击选择此单元格插入标签\n位置: [${cell.row}, ${cell.col}]">
                                    <span class="cell-badge">[${cell.row},${cell.col}]</span>
                                    <div class="cell-content">${displayText}</div>
                                </td>
                            `;
                        });
                        html += '</tr>';
                    });
                    
                    html += `
                            </table>
                        </div>
                    `;
                }
            });
        } else {
            html += '<div class="empty-state">无法加载文档结构</div>';
        }
        
        html += '</div>';
        container.innerHTML = html;
    }
    
    /**
     * 渲染标签面板（网格布局）
     */
    renderTags() {
        const container = document.getElementById('tagsContent');
        let html = '';
        
        for (const [category, tags] of Object.entries(this.tags)) {
            // 添加分类标题
            html += `<div class="tag-category-title">${category}</div>`;
            
            // 添加标签卡片
            tags.forEach(tag => {
                html += `
                    <div class="tag-card" onclick="app.insertTag('${tag.tag}')" title="点击插入到选中位置">
                        <div class="tag-card-name">{{${tag.tag}}}</div>
                        <div class="tag-card-desc">${tag.desc}</div>
                    </div>
                `;
            });
        }
        
        container.innerHTML = html;
    }
    
    /**
     * 在弹窗中搜索标签
     */
    searchTagsInModal(query) {
        const allCards = document.querySelectorAll('.tag-card');
        const lowerQuery = query.toLowerCase();
        
        allCards.forEach(card => {
            const tagName = card.querySelector('.tag-card-name').textContent.toLowerCase();
            const tagDesc = card.querySelector('.tag-card-desc').textContent.toLowerCase();
            
            if (tagName.includes(lowerQuery) || tagDesc.includes(lowerQuery)) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });
    }
    
    /**
     * 选择插入位置
     */
    selectLocation(type, index, row = null, col = null, evt = null) {
        try {
            // 移除之前的选中状态
            document.querySelectorAll('.doc-paragraph, .doc-table-cell').forEach(el => {
                el.classList.remove('selected');
            });
            
            // 获取事件对象并添加选中状态
            const targetEvent = evt || window.event;
            if (targetEvent) {
                const target = targetEvent.currentTarget || targetEvent.target;
                if (target && target.classList) {
                    target.classList.add('selected');
                }
            } else {
                // 如果没有事件对象，通过data属性查找元素
                let selector;
                if (type === 'paragraph') {
                    selector = `.doc-paragraph[data-index="${index}"]`;
                } else if (type === 'table') {
                    selector = `.doc-table-cell[data-table="${index}"][data-row="${row}"][data-col="${col}"]`;
                }
                
                if (selector) {
                    const element = document.querySelector(selector);
                    if (element) {
                        element.classList.add('selected');
                    }
                }
            }
            
            // 保存选中位置
            this.selectedLocation = { type, index };
            if (type === 'table') {
                this.selectedLocation.row = row;
                this.selectedLocation.col = col;
                this.showNotification(`✅ 已选择：表格 ${index + 1} 单元格 [${row}, ${col}]`, 'info');
            } else {
                this.showNotification(`✅ 已选择：段落 ${index + 1}`, 'info');
            }
            
            console.log('选中位置:', this.selectedLocation);
        } catch (error) {
            console.error('❌ 选择位置时出错:', error);
            // 即使出错也保存位置信息
            this.selectedLocation = { type, index };
            if (type === 'table') {
                this.selectedLocation.row = row;
                this.selectedLocation.col = col;
            }
        }
    }
    
    /**
     * 插入标签
     */
    async insertTag(tagName) {
        if (!this.selectedLocation) {
            this.showNotification('请先选择要插入标签的位置', 'warning');
            return;
        }
        
        try {
            this.showLoading('正在插入标签...');
            
            const response = await this.apiRequest('/api/template-editor/insert-tag', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: this.sessionId,
                    filename: this.filename,
                    location: this.selectedLocation,
                    tag_name: tagName
                })
            });
            
            const data = await response.json();
            
            this.hideLoading();
            
            if (data.success) {
                this.showNotification(`✅ 标签 {{${tagName}}} 已插入`, 'success');
                
                // 更新结构
                this.structure = data.structure;
                
                // 记录插入历史
                this.insertedTags.push({
                    tag: tagName,
                    location: {...this.selectedLocation},
                    time: new Date().toLocaleTimeString()
                });
                
                // 更新计数器
                const counter = document.getElementById('tagCounter');
                if (counter) {
                    counter.textContent = `已插入 ${this.insertedTags.length} 个标签`;
                }
                
                // 重新渲染Word文档（保持滚动位置）
                await this.renderWordDocument(true);
                
                // 清除选中状态
                this.selectedLocation = null;
                
                // 关闭弹窗
                this.closeTagSelector();
                
                // 更新步骤3
                const step2 = document.getElementById('step2');
                const step3 = document.getElementById('step3');
                if (step2) step2.classList.add('completed');
                if (step3) step3.classList.add('active');
            } else {
                this.showNotification(data.error || '插入失败', 'error');
            }
        } catch (error) {
            this.hideLoading();
            console.error('插入标签失败:', error);
            this.showNotification('插入失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 更新插入历史
     */
    updateHistory() {
        const container = document.getElementById('historyContent');
        const counter = document.getElementById('tagCounter');
        
        counter.textContent = `${this.insertedTags.length}个`;
        
        if (this.insertedTags.length === 0) {
            container.innerHTML = '<div class="empty-state">还未插入任何标签</div>';
            return;
        }
        
        let html = '';
        this.insertedTags.forEach((item, index) => {
            const locationDesc = item.location.type === 'paragraph' 
                ? `段落 ${item.location.index + 1}`
                : `表格 ${item.location.index + 1} [${item.location.row},${item.location.col}]`;
            
            html += `
                <div class="history-item">
                    <div class="history-tag">{{${item.tag}}}</div>
                    <div class="history-info">
                        <div>${locationDesc}</div>
                        <div class="history-time">${item.time}</div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    /**
     * 搜索标签
     */
    searchTags(keyword) {
        const items = document.querySelectorAll('.tag-item');
        keyword = keyword.toLowerCase();
        
        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            if (text.includes(keyword)) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    /**
     * 下载编辑后的模板
     */
    async downloadTemplate() {
        if (!this.sessionId || !this.filename) {
            this.showNotification('没有可下载的文件', 'warning');
            return;
        }
        
        try {
            const url = `/api/template-editor/download/${this.sessionId}/${this.filename}`;
            const a = document.createElement('a');
            a.href = url;
            a.download = `tagged_${this.filename}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            
            this.showNotification('模板下载成功！现在可以在主页使用此模板生成教案', 'success');
        } catch (error) {
            console.error('下载失败:', error);
            this.showNotification('下载失败', 'error');
        }
    }
    
    /**
     * 显示加载状态
     */
    showLoading(message = '加载中...') {
        let overlay = document.getElementById('loadingOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loadingOverlay';
            overlay.className = 'loading-overlay';
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = `
            <div class="loading-spinner"></div>
            <div class="loading-text">${message}</div>
        `;
        overlay.style.display = 'flex';
    }
    
    /**
     * 隐藏加载状态
     */
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    /**
     * 显示通知
     */
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        const colors = {
            'success': '#10a37f',
            'error': '#ef4444',
            'warning': '#f59e0b',
            'info': '#3b82f6'
        };
        
        notification.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 15px 20px;
            background: ${colors[type]};
            color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            font-size: 14px;
            max-width: 350px;
            animation: slideIn 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }
}

// 初始化应用
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new TemplateEditorApp();
});

// 添加动画CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(400px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(400px); opacity: 0; }
    }
    
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 9999;
    }
    
    .loading-spinner {
        width: 50px;
        height: 50px;
        border: 4px solid rgba(255, 255, 255, 0.3);
        border-top-color: white;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    
    .loading-text {
        color: white;
        margin-top: 20px;
        font-size: 16px;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

