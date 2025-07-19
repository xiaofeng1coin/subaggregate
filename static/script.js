document.addEventListener('DOMContentLoaded', function () {
    // --- 动态背景逻辑 ---
    const canvas = document.getElementById('particle-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        const setCanvasSize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
        setCanvasSize();
        let particles = [];
        const mouse = { x: null, y: null, radius: 100 };
        window.addEventListener('mousemove', (e) => { mouse.x = e.x; mouse.y = e.y; });
        window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });
        window.addEventListener('resize', () => { setCanvasSize(); initParticles(); });
        class Particle {
            constructor(x, y, size, color) { this.x = x; this.y = y; this.size = size; this.color = color; this.baseX = this.x; this.baseY = this.y; this.density = (Math.random() * 30) + 1; }
            draw() { ctx.fillStyle = this.color; ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2); ctx.closePath(); ctx.fill(); }
            update() { let dx = mouse.x - this.x; let dy = mouse.y - this.y; let distance = Math.sqrt(dx * dx + dy * dy); let force = (mouse.radius - distance) / mouse.radius; if (distance < mouse.radius) { this.x -= (dx / distance) * force * this.density; this.y -= (dy / distance) * force * this.density; } else { if (this.x !== this.baseX) this.x -= (this.x - this.baseX) / 10; if (this.y !== this.baseY) this.y -= (this.y - this.baseY) / 10; } }
        }
        const initParticles = () => { particles = []; let num = (canvas.width * canvas.height) / 9000; for (let i = 0; i < num; i++) particles.push(new Particle(Math.random() * canvas.width, Math.random() * canvas.height, (Math.random() * 1.5) + 1, 'rgba(255, 255, 255, 0.8)')); };
        const animate = () => { ctx.clearRect(0, 0, canvas.width, canvas.height); particles.forEach(p => { p.update(); p.draw(); }); connectParticles(); requestAnimationFrame(animate); };
        const connectParticles = () => { for (let a = 0; a < particles.length; a++) for (let b = a; b < particles.length; b++) { let dist = Math.sqrt(Math.pow(particles[a].x - particles[b].x, 2) + Math.pow(particles[a].y - particles[b].y, 2)); if (dist < 90) { ctx.strokeStyle = `rgba(255, 255, 255, ${1 - dist / 90})`; ctx.lineWidth = 0.5; ctx.beginPath(); ctx.moveTo(particles[a].x, particles[a].y); ctx.lineTo(particles[b].x, particles[b].y); ctx.stroke(); } } };
        initParticles();
        animate();
    }

    // --- 主应用逻辑 ---
    const api = {
        async request(method, url, data) {
            const options = { method, headers: { 'Content-Type': 'application/json' } };
            if (data) options.body = JSON.stringify(data);
            const response = await fetch(url, options);
            let resData;
            try { resData = await response.json(); } catch (e) { resData = { message: '服务器响应格式错误' }; }
            if (!response.ok) throw new Error(resData.message || '请求失败');
            return resData;
        },
        get: (url) => api.request('GET', url),
        post: (url, data) => api.request('POST', url, data),
        put: (url, data) => api.request('PUT', url, data),
        delete: (url) => api.request('DELETE', url)
    };

    let ALL_DATA = {};
    const subListEl = document.getElementById('sub-list');
    const globalFilterKeywordsEl = document.getElementById('globalFilterKeywords');
    const globalFilterEnabledEl = document.getElementById('globalFilterEnabled');

    const render = (data) => {
        ALL_DATA = data;
        const { subscriptions = [], aggregation_enabled = [], global_filter_keywords = '', global_filter_enabled = false } = data;
        globalFilterKeywordsEl.value = global_filter_keywords;
        globalFilterEnabledEl.checked = global_filter_enabled;

        subListEl.innerHTML = '';
        if (subscriptions.length === 0) {
            subListEl.innerHTML = `<div class="loading-state">还没有任何订阅，请在右侧添加一个。</div>`;
            return;
        }
        subscriptions.forEach(sub => {
            const isEnabled = aggregation_enabled.includes(sub.id);
            const item = document.createElement('div');
            item.className = 'sub-item';
            item.dataset.id = sub.id;
            item.innerHTML = `
                <div class="checkbox-col">
                    <input type="checkbox" class="enabled-sub" id="sub-check-${sub.id}" value="${sub.id}" ${isEnabled ? 'checked' : ''}>
                    <label for="sub-check-${sub.id}" class="custom-checkbox"></label>
                </div>
                <div class="name-col">${escapeHTML(sub.name)}</div>
                <div class="url-col">${escapeHTML(sub.url)}</div>
                <div class="actions-col">
                    <button class="btn-action filter-btn" title="过滤"><i class="fa-solid fa-filter"></i></button>
                    <button class="btn-action edit-btn" title="编辑"><i class="fa-solid fa-pencil"></i></button>
                    <button class="btn-action delete-btn" title="删除"><i class="fa-regular fa-trash-can"></i></button>
                </div>`;
            subListEl.appendChild(item);
        });
    };

    const loadAndRender = async () => {
        try {
            render(await api.get('/api/data'));
        } catch (error) {
            showToast(error.message, 'error');
            subListEl.innerHTML = `<div class="loading-state" style="color:var(--danger-color)">数据加载失败</div>`;
        }
    };

    document.getElementById('add-form').addEventListener('submit', async function (e) {
        e.preventDefault();
        const btn = this.querySelector('button[type="submit"]');
        toggleSpinner(btn, true);
        try {
            const result = await api.post('/api/subscriptions', { name: this.elements.name.value, url: this.elements.url.value });
            showToast(result.message, 'success');
            this.reset();
            this.elements.name.focus();
            await loadAndRender();
        } catch (error) { showToast(error.message, 'error'); } finally { toggleSpinner(btn, false); }
    });

    subListEl.addEventListener('click', (e) => {
        const targetBtn = e.target.closest('button.btn-action');
        if (!targetBtn) return;
        const subId = targetBtn.closest('.sub-item').dataset.id;
        const sub = ALL_DATA.subscriptions.find(s => s.id == subId);
        if (!sub) return;
        if (targetBtn.classList.contains('edit-btn')) openModal('editModal', sub);
        else if (targetBtn.classList.contains('delete-btn')) {
            if (confirm(`确定要删除订阅 "${sub.name}" 吗？`)) deleteSubscription(subId);
        } else if (targetBtn.classList.contains('filter-btn')) openModal('filterModal', sub);
    });
    
    const deleteSubscription = async (id) => {
        try {
            const result = await api.delete(`/api/subscriptions/${id}`);
            showToast(result.message, 'success');
            await loadAndRender();
        } catch (error) { showToast(error.message, 'error'); }
    };
    
    document.getElementById('checkAll').addEventListener('change', (e) => {
        document.querySelectorAll('.enabled-sub').forEach(cb => cb.checked = e.target.checked);
    });
    
    const handleApiCall = (apiFunc) => async function () {
        toggleSpinner(this, true);
        try {
            const result = await apiFunc();
            showToast(result.message, 'success');
        } catch (error) { showToast(error.message, 'error'); } finally { toggleSpinner(this, false); }
    };
    
    document.getElementById('saveAggregationBtn').addEventListener('click', handleApiCall(async () => {
        const enabled_ids = Array.from(document.querySelectorAll('.enabled-sub:checked')).map(cb => cb.value);
        return await api.post('/api/aggregation', { enabled_ids });
    }));

    document.getElementById('saveGlobalFilterBtn').addEventListener('click', handleApiCall(async () => {
        const keywords = globalFilterKeywordsEl.value;
        const enabled = globalFilterEnabledEl.checked;
        return await api.post('/api/global_filter', { keywords, enabled });
    }));

    const modalBackdrop = document.getElementById('modalBackdrop');
    const openModal = (modalId, sub) => {
        const modal = document.getElementById(modalId);
        if (modalId === 'editModal') {
            document.getElementById('editSubId').value = sub.id;
            document.getElementById('editSubName').value = sub.name;
            document.getElementById('editSubUrl').value = sub.url;
        } else if (modalId === 'filterModal') {
            document.getElementById('filterModalTitle').innerHTML = `为 “${escapeHTML(sub.name)}” 设置过滤器`;
            document.getElementById('filterSubId').value = sub.id;
            document.getElementById('filterKeywords').value = sub.filter_keywords || '';
            document.getElementById('singleFilterEnabled').checked = sub.filter_enabled || false;
        }
        modalBackdrop.classList.add('show');
        modal.classList.add('show');
    };
    const closeModal = () => {
        document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
        modalBackdrop.classList.remove('show');
    };
    modalBackdrop.addEventListener('click', closeModal);
    document.getElementById('cancelEditBtn').addEventListener('click', closeModal);
    document.getElementById('cancelFilterBtn').addEventListener('click', closeModal);
    
    document.getElementById('saveEditBtn').addEventListener('click', handleApiCall(async () => {
        const id = document.getElementById('editSubId').value;
        const name = document.getElementById('editSubName').value;
        const url = document.getElementById('editSubUrl').value;
        const originalSub = ALL_DATA.subscriptions.find(s => s.id == id);
        const result = await api.put(`/api/subscriptions/${id}`, { name, url, filter_keywords: originalSub.filter_keywords, filter_enabled: originalSub.filter_enabled });
        closeModal();
        await loadAndRender();
        return result;
    }));
    
    document.getElementById('saveFilterBtn').addEventListener('click', handleApiCall(async () => {
        const id = document.getElementById('filterSubId').value;
        const keywords = document.getElementById('filterKeywords').value;
        const enabled = document.getElementById('singleFilterEnabled').checked;
        const originalSub = ALL_DATA.subscriptions.find(s => s.id == id);
        const result = await api.put(`/api/subscriptions/${id}`, { name: originalSub.name, url: originalSub.url, filter_keywords: keywords, filter_enabled: enabled });
        closeModal();
        ALL_DATA.subscriptions.find(s => s.id == id).filter_enabled = enabled;
        ALL_DATA.subscriptions.find(s => s.id == id).filter_keywords = keywords;
        return result;
    }));

    const copyBtn = document.getElementById('copyBtn');
    copyBtn.addEventListener('click', () => {
        const urlInput = document.getElementById('aggregatedUrl');
        navigator.clipboard.writeText(urlInput.value).then(() => {
            showToast('聚合地址已复制', 'success');
            const iconContainer = document.getElementById('copy-icon-container');
            const textEl = document.getElementById('copy-text');
            const originalIconHTML = iconContainer.innerHTML;
            const originalText = textEl.textContent;
            
            iconContainer.innerHTML = '<i class="fa-solid fa-check"></i>';
            textEl.textContent = '已复制!';
            copyBtn.classList.add('btn-primary');
            
            setTimeout(() => {
                iconContainer.innerHTML = originalIconHTML;
                textEl.textContent = originalText;
                copyBtn.classList.remove('btn-primary');
            }, 2000);
        }).catch(err => showToast('复制失败: ' + err, 'error'));
    });
    
    const showToast = (message, type = 'success') => {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerHTML = `<span class="icon"><i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark'}"></i></span><span>${escapeHTML(message)}</span>`;
        container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => { toast.classList.remove('show'); toast.addEventListener('transitionend', () => toast.remove()); }, 3000);
    };

    const escapeHTML = (str) => String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'})[m]);
    
    const toggleSpinner = (btn, show) => {
        if (!btn) return;
        btn.disabled = show;
        const textEl = btn.querySelector('.btn-text');
        const spinnerEl = btn.querySelector('.spinner');
        if (textEl) textEl.style.display = show ? 'none' : 'inline-flex';
        if (spinnerEl) spinnerEl.style.display = show ? 'inline-block' : 'none';
    };
    
    loadAndRender();
});
