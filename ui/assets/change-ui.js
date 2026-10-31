// --- CHANGE REQUEST MANAGEMENT LOGIC ---

let currentChangeStatusView = 'scheduled';
let currentEditChangeId = null;
let changeViewLoading = false;
const changeListCache = {};
function changeFormValues() {
    return [
        document.getElementById('cr_cr_id')?.value || '',
        document.getElementById('cr_title')?.value || '',
        document.getElementById('cr_description')?.value || '',
        document.getElementById('cr_domain')?.value || '',
        document.getElementById('cr_status')?.value || '',
        document.getElementById('cr_risk_level')?.value || '',
        document.getElementById('cr_region')?.value || '',
        document.getElementById('cr_window_start')?.value || '',
        document.getElementById('cr_window_end')?.value || '',
        document.getElementById('cr_lead_engineer')?.value || '',
        document.getElementById('cr_approver')?.value || ''
    ];
}

const changeDirty = createDirtyChecker(changeFormValues);

function resetChangeForm() {
    currentEditChangeId = null;
    const fields = ['cr_cr_id', 'cr_title', 'cr_description', 'cr_window_start', 'cr_window_end', 'cr_lead_engineer', 'cr_approver'];
    fields.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const d = document.getElementById('cr_domain'); if (d) d.value = 'Core';
    const s = document.getElementById('cr_status'); if (s) s.value = 'scheduled';
    const r = document.getElementById('cr_risk_level'); if (r) r.value = 'medium';
    const reg = document.getElementById('cr_region'); if (reg) reg.value = '';
    const sel = document.getElementById('changeSelector'); if (sel) sel.value = '';
    changeDirty.snapshot();
}

function toggleChangeSubNav() {
    // no-op kept for compatibility
}

async function switchChangeView(status, options) {
    options = options || {};
    if (changeViewLoading) return;
    if (!options.skipDirtyCheck && changeDirty.isDirty() && !confirm('Discard unsaved changes?')) return;

    changeViewLoading = true;
    currentChangeStatusView = status;
    currentEditChangeId = null;

    ['scheduled', 'in_progress', 'completed', 'cancelled', 'rollback'].forEach(s => {
        const btn = document.getElementById(`change-tab-${s}`);
        if (!btn) return;
        if (s === status) {
            btn.classList.add('bg-slate-800', 'text-white');
            btn.classList.remove('text-slate-400');
        } else {
            btn.classList.remove('bg-slate-800', 'text-white');
            btn.classList.add('text-slate-400');
        }
    });

    const selectorWrap = document.getElementById('changeSelectorWrap');
    if (selectorWrap) selectorWrap.classList.remove('hidden');

    resetChangeForm();
    await fetchChangesForDropdown(status);
    changeViewLoading = false;
}

async function fetchChangesForDropdown(status) {
    const selector = document.getElementById('changeSelector');
    if (!selector) return;
    selector.innerHTML = '<option value="">Loading...</option>';
    selector.disabled = true;

    // Cache hit: render from memory, skip network
    if (changeListCache[status]) {
        const items = changeListCache[status];
        selector.innerHTML = '<option value="">-- Select a change request --</option>';
        if (!Array.isArray(items) || items.length === 0) {
            const label = status.replace(/_/g, ' ');
            selector.innerHTML = `<option value="">No ${label} change requests found</option>`;
            selector.disabled = false;
            return;
        }
        items.forEach(cr => {
            const opt = document.createElement('option');
            opt.value = cr.id;
            opt.textContent = `${cr.cr_id} (${cr.risk_level})`;
            selector.appendChild(opt);
        });
        selector.disabled = false;
        return;
    }

    try {
        const res = await fetch(`/api/v1/change-requests?status=${encodeURIComponent(status)}`, { credentials: 'same-origin' });
        const items = await res.json();
        changeListCache[status] = items;

        selector.innerHTML = '<option value="">-- Select a change request --</option>';

        if (!Array.isArray(items) || items.length === 0) {
            const label = status.replace(/_/g, ' ');
            selector.innerHTML = `<option value="">No ${label} change requests found</option>`;
            return;
        }

        items.forEach(cr => {
            const opt = document.createElement('option');
            opt.value = cr.id;
            opt.textContent = `${cr.cr_id} (${cr.risk_level})`;
            selector.appendChild(opt);
        });
    } catch (err) {
        selector.innerHTML = '<option value="">Error loading data</option>';
    } finally {
        selector.disabled = false;
    }
}
PY

async function loadSelectedChange() {
    const selector = document.getElementById('changeSelector');
    if (!selector) return;
    const id = selector.value;
    if (!id) {
        resetChangeForm();
        return;
    }

    if (changeDirty.isDirty() && !confirm('Discard unsaved changes?')) {
        selector.value = currentEditChangeId || '';
        return;
    }

    try {
        const res = await fetch(`/api/v1/change-requests?status=${encodeURIComponent(currentChangeStatusView)}`, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed to load change requests');
        const items = await res.json();
        const cr = Array.isArray(items) ? items.find(i => String(i.id) === String(id)) : null;

        if (!cr) {
            showToast('Change request no longer available. Refreshing list.', 'error');
            currentEditChangeId = null;
            resetChangeForm();
            delete changeListCache[currentChangeStatusView];
            fetchChangesForDropdown(currentChangeStatusView);
            return;
        }

        currentEditChangeId = cr.id;
        const set = (elId, val) => { const el = document.getElementById(elId); if (el) el.value = val; };
        set('cr_cr_id', cr.cr_id || '');
        set('cr_title', cr.title || '');
        set('cr_description', cr.description || '');
        set('cr_domain', cr.domain || 'Core');
        set('cr_status', cr.status || 'scheduled');
        set('cr_risk_level', cr.risk_level || 'medium');
        set('cr_region', cr.region || '');
        set('cr_window_start', cr.window_start ? String(cr.window_start).slice(0, 16) : '');
        set('cr_window_end', cr.window_end ? String(cr.window_end).slice(0, 16) : '');
        set('cr_lead_engineer', cr.lead_engineer || '');
        set('cr_approver', cr.approver || '');
        changeDirty.snapshot();
    } catch (err) {
        showToast(err.message, 'error');
    }
}


async function submitChange() {
    const payload = {
        cr_id: document.getElementById('cr_cr_id').value,
        title: document.getElementById('cr_title').value,
        description: document.getElementById('cr_description').value,
        domain: document.getElementById('cr_domain').value,
        status: document.getElementById('cr_status').value,
        risk_level: document.getElementById('cr_risk_level').value,
        region: document.getElementById('cr_region').value || null,
        window_start: document.getElementById('cr_window_start').value || null,
        window_end: document.getElementById('cr_window_end').value || null,
        lead_engineer: document.getElementById('cr_lead_engineer').value,
        approver: document.getElementById('cr_approver').value
    };

    if (!payload.cr_id || !payload.title) {
        showToast('CR ID and Title are required.', 'error');
        return;
    }

    try {
        const url = currentEditChangeId
            ? `/api/v1/change-requests/${currentEditChangeId}`
            : '/api/v1/change-requests';
        const method = currentEditChangeId ? 'PATCH' : 'POST';

        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            let detail = 'Failed to save change request';
            try { const d = await res.json(); if (d && d.detail) detail = d.detail; } catch (e) {}
            throw new Error(detail);
        }

        showToast('Change request saved successfully!', 'success');
        delete changeListCache[currentChangeStatusView];
        delete changeListCache[payload.status];
        const newStatus = payload.status;
        resetChangeForm();
        if (newStatus && newStatus !== currentChangeStatusView) {
            switchChangeView(newStatus, { skipDirtyCheck: true });
        } else {
            fetchChangesForDropdown(currentChangeStatusView);
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function downloadChangeImage() {
    captureElement('changeCaptureZone', `ChangeRequest_${document.getElementById('cr_cr_id').value || 'New'}.png`);
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('changePanel')) {
        switchChangeView('scheduled', { skipDirtyCheck: true });
    }
});

