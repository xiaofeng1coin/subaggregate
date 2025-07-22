/*
 * 文件名: static/mobile.js
 * 描述: 完全独立的移动端交互脚本，不依赖 script.js。
 * [已修复 V2] 修复了异步操作后按钮持续加载的 Bug。
 */
document.addEventListener('DOMContentLoaded', () => {

    // --- 核心工具函数 (本地副本，实现完全隔离) ---
    const api = {
        async request(method, url, data) {
            const options = {
                method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (data) options.body = JSON.stringify(data);
            try {
                const response = await fetch(url, options);
                const resData = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(resData.message || `请求失败: ${response.status}`);
                }
                return resData;
            } catch (e) {
                throw new Error(e.message || '网络错误，请检查连接');
            }
        },
        get: (url) => api.request('GET', url, undefined),
        post: (url, data) => api.request('POST', url, data),
        put: (url, data) => api.request('PUT', url, data),
        delete: (url) => api.request('DELETE', url, undefined)
    };

    const showToast = (message, type = 'success') => {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerHTML = `<span>${message}</span>`;
        container.appendChild(toast);
        toast.getBoundingClientRect();
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => toast.remove());
        }, 3000);
    };

    // ---------- [唯一、决定性的修改处] ----------
    /**
     * 切换按钮的加载状态。
     * [关键修复] 恢复状态时，先解除 disabled 状态，再恢复 innerHTML，避免浏览器渲染问题。
     * @param {HTMLElement} btn - 目标按钮元素。
     * @param {boolean} isLoading - 是否进入加载状态。
     */
    const toggleButtonLoading = (btn, isLoading) => {
        if (!btn) return;

        if (isLoading) {
            btn.dataset.originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner"></div>';
        } else {
            // **关键改动**: 先将按钮设为可用状态，然后再修改其内容。
            btn.disabled = false;
            if (btn.dataset.originalHtml) {
                btn.innerHTML = btn.dataset.originalHtml;
                delete btn.dataset.originalHtml;
            }
        }
    };
    // ---------- [修改结束] ----------

    const escapeHTML = (str) => {
        if (typeof str !== 'string') str = String(str);
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    };

    let ALL_DATA = {};

    // --- 移动端 UI 渲染 ---
    const renderMobileUI = (data) => {
        const { subscriptions = [], aggregation_enabled = [] } = data;
        const subListEl = document.getElementById('sub-list');
        const checkAll = document.getElementById('checkAll');
        if (!subListEl) return;

        subListEl.innerHTML = '';
        if (subscriptions.length === 0) {
            subListEl.innerHTML = `<div class="loading-state">无订阅，点击右下角 <i class="fa-solid fa-plus"></i> 添加</div>`;
            return;
        }

        const enabled_ids = new Set(aggregation_enabled);
        subscriptions.forEach(sub => {
            const isEnabled = enabled_ids.has(sub.id);
            const item = document.createElement('div');
            item.className = 'sub-item';
            item.dataset.id = sub.id;
            item.innerHTML = `
                <div class="custom-checkbox-container">
                    <input type="checkbox" class="custom-checkbox-input enabled-sub" id="sub-check-${sub.id}" value="${sub.id}" ${isEnabled ? 'checked' : ''}>
                    <label for="sub-check-${sub.id}"></label>
                </div>
                <div class="sub-info">
                    <div class="sub-name">${escapeHTML(sub.name)}</div>
                    <div class="sub-url">${escapeHTML(sub.url)}</div>
                </div>
                <button class="btn-action-menu" data-id="${sub.id}" aria-label="操作菜单"><i class="fa-solid fa-ellipsis-v"></i></button>`;
            subListEl.appendChild(item);
        });

        const allChecks = document.querySelectorAll('.enabled-sub');
        if(checkAll) {
            checkAll.checked = allChecks.length > 0 && Array.from(allChecks).every(c => c.checked);
        }
    };

    const renderGlobalFilter = (data) => {
        const enabledEl = document.getElementById('globalFilterEnabled');
        const keywordsEl = document.getElementById('globalFilterKeywords');
        if(enabledEl) enabledEl.checked = data.global_filter_enabled || false;
        if(keywordsEl) keywordsEl.value = data.global_filter_keywords || '';
    };

    const loadAndRender = async () => {
        const loadingState = document.querySelector('#sub-list .loading-state');
        if (loadingState) loadingState.style.display = 'flex';
        try {
            const data = await api.get('/api/data');
            ALL_DATA = data;
            renderMobileUI(data);
            renderGlobalFilter(data);
        } catch (error) {
            showToast(error.message, 'error');
            const subListEl = document.getElementById('sub-list');
            if (subListEl) subListEl.innerHTML = `<div class="loading-state">${error.message}</div>`;
        } finally {
            if (loadingState) loadingState.style.display = 'none';
        }
    };

    // --- 交互逻辑 ---
    const modalView = document.getElementById('modal-view');
    const modalTitleEl = document.getElementById('modal-title');
    const modalContentEl = document.querySelector('.modal-view-content');
    const saveModalBtn = document.getElementById('saveModalBtn');
    let currentModalAction = null;

    const openMobileModal = (modalType, sub) => {
        let contentHTML = '';
        switch(modalType) {
            case 'add':
                modalTitleEl.textContent = '添加新订阅';
                contentHTML = `<div class="form-group"><label for="modalSubName">订阅名称</label><input type="text" class="form-control" id="modalSubName" placeholder="例如：我的主力机场" required></div><div class="form-group"><label for="modalSubUrl">订阅地址</label><input type="url" class="form-control" id="modalSubUrl" placeholder="https://" required></div>`;
                currentModalAction = async () => {
                    const name = document.getElementById('modalSubName').value.trim();
                    const url = document.getElementById('modalSubUrl').value.trim();
                    if (!name || !url) throw new Error("名称和地址不能为空");
                    return api.post('/api/subscriptions', { name, url });
                };
                break;
            case 'edit':
                modalTitleEl.textContent = '编辑订阅';
                contentHTML = `<div class="form-group"><label for="modalSubName">订阅名称</label><input type="text" class="form-control" id="modalSubName" value="${escapeHTML(sub.name)}" required></div><div class="form-group"><label for="modalSubUrl">订阅地址</label><input type="url" class="form-control" id="modalSubUrl" value="${escapeHTML(sub.url)}" required></div>`;
                currentModalAction = async () => {
                    const name = document.getElementById('modalSubName').value.trim();
                    const url = document.getElementById('modalSubUrl').value.trim();
                    if (!name || !url) throw new Error("名称和地址不能为空");
                    return api.put(`/api/subscriptions/${sub.id}`, { name, url });
                };
                break;
            case 'filter':
                modalTitleEl.textContent = '独立过滤器';
                contentHTML = `
                    <p style="text-align:center; margin-bottom:1.5rem; font-weight:500;">为 "${escapeHTML(sub.name)}" 设置</p>
                    <div class="toggle-switch-wrapper" style="background:rgba(0,0,0,0.1); padding:0.75rem 1rem; border-radius:8px; margin-bottom:1rem;"><label for="modalFilterEnabled">启用独立过滤</label><div class="toggle-switch"><input type="checkbox" id="modalFilterEnabled" ${sub.filter_enabled ? 'checked' : ''}><label for="modalFilterEnabled" class="slider"></label></div></div>
                    <div class="form-group"><label for="modalFilterKeywords">过滤关键词</label><textarea class="form-control" id="modalFilterKeywords" rows="5" placeholder="一行一个，或用逗号/空格分隔">${escapeHTML(sub.filter_keywords || '')}</textarea></div>`;
                currentModalAction = async () => {
                    const keywords = document.getElementById('modalFilterKeywords').value;
                    const enabled = document.getElementById('modalFilterEnabled').checked;
                    return api.put(`/api/subscriptions/${sub.id}`, { filter_keywords: keywords, filter_enabled: enabled });
                };
                break;
        }
        modalContentEl.innerHTML = contentHTML;
        modalView.classList.add('show');
    };

    const closeModal = () => modalView.classList.remove('show');

    const openActionSheet = (sub) => {
        document.querySelector('.action-sheet-backdrop')?.remove();
        document.querySelector('.action-sheet')?.remove();
        const backdrop = document.createElement('div');
        backdrop.className = 'action-sheet-backdrop';
        const sheet = document.createElement('div');
        sheet.className = 'action-sheet';
        sheet.innerHTML = `<h3 style="text-align:center; margin-bottom:1rem; padding-bottom:1rem; border-bottom:1px solid var(--card-border-color);">${escapeHTML(sub.name)}</h3><button class="edit-action"><i class="fa-solid fa-pencil"></i> 编辑信息</button><button class="filter-action"><i class="fa-solid fa-filter"></i> 节点过滤</button><button class="delete-action"><i class="fa-regular fa-trash-can"></i> 删除订阅</button>`;
        document.body.appendChild(backdrop);
        document.body.appendChild(sheet);
        const closeSheet = () => { backdrop.remove(); sheet.remove(); };
        backdrop.addEventListener('click', closeSheet);
        sheet.querySelector('.edit-action').addEventListener('click', () => { closeSheet(); openMobileModal('edit', sub); });
        sheet.querySelector('.filter-action').addEventListener('click', () => { closeSheet(); openMobileModal('filter', sub); });
        sheet.querySelector('.delete-action').addEventListener('click', async () => {
            closeSheet();
            if (confirm(`确定要删除订阅 "${sub.name}" 吗？`)) {
                try {
                    const result = await api.delete(`/api/subscriptions/${sub.id}`);
                    showToast(result.message || "删除成功");
                    await loadAndRender();
                } catch(e) { showToast(e.message, 'error')}
            }
        });
    };

    // --- 事件监听绑定 ---
    document.getElementById('showAddModalBtn').addEventListener('click', () => openMobileModal('add'));
    document.getElementById('closeModalBtn').addEventListener('click', closeModal);

    // [鲁棒性增强] 使用按钮自身的变量引用，而不是 e.currentTarget
    saveModalBtn.addEventListener('click', async () => {
        if (!currentModalAction) return;
        toggleButtonLoading(saveModalBtn, true);
        try {
            const result = await currentModalAction();
            showToast(result.message || '操作成功');
            closeModal();
            await loadAndRender();
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            toggleButtonLoading(saveModalBtn, false);
        }
    });

    document.getElementById('sub-list').addEventListener('click', e => {
        const menuBtn = e.target.closest('.btn-action-menu');
        if (menuBtn) {
            const sub = ALL_DATA.subscriptions.find(s => s.id === menuBtn.dataset.id);
            if(sub) openActionSheet(sub);
        } else if (e.target.closest('.sub-item') && !e.target.closest('.custom-checkbox-container')) {
            const subItem = e.target.closest('.sub-item');
            const checkbox = subItem.querySelector('.enabled-sub');
            if (checkbox) {
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    });

    const checkAllEl = document.getElementById('checkAll');
    if (checkAllEl) {
        checkAllEl.addEventListener('change', e => {
            document.querySelectorAll('.enabled-sub').forEach(cb => cb.checked = e.target.checked);
        });
    }

    document.getElementById('sub-list').addEventListener('change', e => {
        if (e.target.classList.contains('enabled-sub')) {
            const allChecks = document.querySelectorAll('.enabled-sub');
             if(checkAllEl) {
                checkAllEl.checked = allChecks.length > 0 && Array.from(allChecks).every(c => c.checked);
            }
        }
    });

    const saveAggregationBtn = document.getElementById('saveAggregationBtn');
    if (saveAggregationBtn) {
        saveAggregationBtn.addEventListener('click', async () => {
            const enabled_ids = Array.from(document.querySelectorAll('.enabled-sub:checked')).map(cb => cb.value);
            toggleButtonLoading(saveAggregationBtn, true);
            try {
                const result = await api.post('/api/aggregation', { enabled_ids });
                showToast(result.message || '聚合选择已保存');
            } catch (error) { showToast(error.message, 'error'); } finally { toggleButtonLoading(saveAggregationBtn, false); }
        });
    }

    const saveGlobalFilterBtn = document.getElementById('saveGlobalFilterBtn');
    if (saveGlobalFilterBtn){
        saveGlobalFilterBtn.addEventListener('click', async () => {
            const enabled = document.getElementById('globalFilterEnabled').checked;
            const keywords = document.getElementById('globalFilterKeywords').value;
            toggleButtonLoading(saveGlobalFilterBtn, true);
            try {
                const result = await api.post('/api/filters/global', { enabled, keywords });
                showToast(result.message || '全局设置已保存');
            } catch (error) { showToast(error.message, 'error'); } finally { toggleButtonLoading(saveGlobalFilterBtn, false); }
        });
    }

// ---------- [唯一修改处开始] ----------
    // 兼容HTTP环境的复制功能
    function copyTextToClipboard(text) {
        // 优先使用现代、安全的剪贴板API
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        } else {
            // 为不安全的上下文(http)或旧浏览器提供后备方案
            return new Promise((resolve, reject) => {
                const textArea = document.createElement("textarea");
                textArea.value = text;
                // 使文本区域不可见
                textArea.style.position = 'fixed';
                textArea.style.top = '-9999px';
                textArea.style.left = '-9999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    const successful = document.execCommand('copy');
                    document.body.removeChild(textArea);
                    if (successful) {
                        resolve();
                    } else {
                        reject(new Error('无法使用后备方案复制文本'));
                    }
                } catch (err) {
                    document.body.removeChild(textArea);
                    reject(err);
                }
            });
        }
    }
 
    const copyBtn = document.getElementById('copyBtn');
    if (copyBtn) {
        copyBtn.addEventListener('click', function() {
            copyTextToClipboard(document.getElementById('aggregatedUrl').value).then(() => {
                showToast('聚合链接已复制!', 'success');
                const iconCopy = this.querySelector('.icon-copy');
                const iconCheck = this.querySelector('.icon-check');
                if (iconCopy && iconCheck) {
                    iconCopy.style.display = 'none';
                    iconCheck.style.display = 'inline';
                    setTimeout(() => { iconCopy.style.display = 'inline'; iconCheck.style.display = 'none'; }, 2000);
                }
            }).catch(err => showToast('复制失败: ' + err.message, 'error'));
        });
    }
    // ---------- [唯一修改处结束] ----------

    // --- 启动应用 ---
    loadAndRender();
});
