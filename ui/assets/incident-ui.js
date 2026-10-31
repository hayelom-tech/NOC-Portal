// --- INCIDENT MANAGEMENT LOGIC ---

let currentIncidentStatusView = 'ongoing';
let currentEditIncidentId = null;
let incidentViewLoading = false;
const incidentListCache = {};
function incidentFormValues() {
    return [
        document.getElementById('inc_priority')?.value || '',
        document.getElementById('inc_ref')?.value || '',
        document.getElementById('inc_desc')?.value || '',
        document.getElementById('inc_biz_impact')?.value || '',
        document.getElementById('inc_sys_impact')?.value || '',
        document.getElementById('inc_owner')?.value || '',
        document.getElementById('inc_start')?.value || '',
        document.getElementById('inc_end')?.value || '',
        document.getElementById('inc_mttr')?.value || '',
        document.getElementById('inc_status')?.value || '',
        document.getElementById('inc_reported')?.value || '',
        document.getElementById('inc_support')?.value || '',
        document.getElementById('inc_problem')?.value || '',
        document.getElementById('inc_update')?.value || '',
        document.getElementById('inc_root')?.value || '',
        document.getElementById('inc_resolution')?.value || ''
    ];
}

const incidentDirty = createDirtyChecker(incidentFormValues);

function resetIncidentForm() {
    currentEditIncidentId = null;
    const fields = ['inc_ref', 'inc_desc', 'inc_biz_impact', 'inc_sys_impact', 'inc_owner', 'inc_start', 'inc_end', 'inc_mttr', 'inc_reported', 'inc_support', 'inc_problem', 'inc_update', 'inc_root', 'inc_resolution'];
    fields.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const p = document.getElementById('inc_priority'); if (p) p.value = 'P3';
    const s = document.getElementById('inc_status'); if (s) s.value = 'ongoing';
    const sel = document.getElementById('incidentSelector'); if (sel) sel.value = '';
    incidentDirty.snapshot();
}


async function switchIncidentView(status, options) {
    options = options || {};
    if (incidentViewLoading) return;
    if (!options.skipDirtyCheck && incidentDirty.isDirty() && !confirm('Discard unsaved changes?')) return;

    incidentViewLoading = true;
    currentIncidentStatusView = status;
    currentEditIncidentId = null;

    ['ongoing', 'closed', 'resolved'].forEach(s => {
        const btn = document.getElementById(`incident-tab-${s}`);
        if (!btn) return;
        if (s === status) {
            btn.classList.add('bg-slate-800', 'text-white');
            btn.classList.remove('text-slate-400');
        } else {
            btn.classList.remove('bg-slate-800', 'text-white');
            btn.classList.add('text-slate-400');
        }
    });

    const selectorWrap = document.getElementById('incidentSelectorWrap');
    if (selectorWrap) selectorWrap.classList.remove('hidden');

    resetIncidentForm();
    await fetchIncidentsForDropdown(status);
    incidentViewLoading = false;
}

async function fetchIncidentsForDropdown(status) {
    const selector = document.getElementById('incidentSelector');
    if (!selector) return;
    selector.innerHTML = '<option value="">Loading...</option>';
    selector.disabled = true;

    // Cache hit: render from memory, skip network
    if (incidentListCache[status]) {
        const incidents = incidentListCache[status];
        selector.innerHTML = '<option value="">-- Select an incident --</option>';
        if (!Array.isArray(incidents) || incidents.length === 0) {
            const msg = status === 'resolved'
                ? 'No resolved incidents in the last 3 days'
                : 'No incidents found';
            selector.innerHTML = `<option value="">${msg}</option>`;
            selector.disabled = false;
            return;
        }
        incidents.forEach(inc => {
            const opt = document.createElement('option');
            opt.value = inc.id;
            opt.textContent = `${inc.reference} (${inc.priority})`;
            selector.appendChild(opt);
        });
        selector.disabled = false;
        return;
    }

    try {
        const res = await fetch(`/api/v1/incidents?status=${encodeURIComponent(status)}`, { credentials: 'same-origin' });
        const incidents = await res.json();
        incidentListCache[status] = incidents;

        selector.innerHTML = '<option value="">-- Select an incident --</option>';

        if (!Array.isArray(incidents) || incidents.length === 0) {
            const msg = status === 'resolved'
                ? 'No resolved incidents in the last 3 days'
                : 'No incidents found';
            selector.innerHTML = `<option value="">${msg}</option>`;
            return;
        }

        incidents.forEach(inc => {
            const opt = document.createElement('option');
            opt.value = inc.id;
            opt.textContent = `${inc.reference} (${inc.priority})`;
            selector.appendChild(opt);
        });
    } catch (err) {
        selector.innerHTML = '<option value="">Error loading data</option>';
    } finally {
        selector.disabled = false;
    }
}
PY

async function loadSelectedIncident() {
    const selector = document.getElementById('incidentSelector');
    if (!selector) return;
    const id = selector.value;
    if (!id) {
        resetIncidentForm();
        return;
    }

    if (incidentDirty.isDirty() && !confirm('Discard unsaved changes?')) {
        selector.value = currentEditIncidentId || '';
        return;
    }

    try {
        const res = await fetch(`/api/v1/incidents?status=${encodeURIComponent(currentIncidentStatusView)}`, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed to load incidents');
        const incidents = await res.json();
        const inc = Array.isArray(incidents) ? incidents.find(i => String(i.id) === String(id)) : null;

        if (!inc) {
            showToast('Incident no longer available. Refreshing list.', 'error');
            currentEditIncidentId = null;
            resetIncidentForm();
            delete incidentListCache[currentIncidentStatusView];
            fetchIncidentsForDropdown(currentIncidentStatusView);
            return;
        }

        currentEditIncidentId = inc.id;
        const set = (elId, val) => { const el = document.getElementById(elId); if (el) el.value = val; };
        set('inc_priority', inc.priority || 'P3');
        set('inc_ref', inc.reference || '');
        set('inc_desc', inc.description || '');
        set('inc_biz_impact', inc.business_impact || '');
        set('inc_sys_impact', inc.system_impact || '');
        set('inc_owner', inc.incident_owner || '');
        set('inc_start', inc.start_time ? String(inc.start_time).slice(0, 16) : '');
        set('inc_end', inc.end_time ? String(inc.end_time).slice(0, 16) : '');
        set('inc_mttr', inc.mttr || '');
        set('inc_status', inc.status || 'ongoing');
        set('inc_reported', inc.reported_by || '');
        set('inc_support', inc.support_group || '');
        set('inc_problem', inc.problem_statement || '');
        set('inc_update', inc.update || '');
        set('inc_root', inc.root_cause || '');
        set('inc_resolution', inc.resolution || '');
        incidentDirty.snapshot();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function submitIncident() {
    const payload = {
        priority: document.getElementById('inc_priority').value,
        reference: document.getElementById('inc_ref').value,
        description: document.getElementById('inc_desc').value,
        business_impact: document.getElementById('inc_biz_impact').value,
        system_impact: document.getElementById('inc_sys_impact').value,
        incident_owner: document.getElementById('inc_owner').value,
        start_time: document.getElementById('inc_start').value || null,
        end_time: document.getElementById('inc_end').value || null,
        mttr: document.getElementById('inc_mttr').value,
        status: document.getElementById('inc_status').value,
        reported_by: document.getElementById('inc_reported').value,
        support_group: document.getElementById('inc_support').value,
        problem_statement: document.getElementById('inc_problem').value,
        update: document.getElementById('inc_update').value,
        root_cause: document.getElementById('inc_root').value,
        resolution: document.getElementById('inc_resolution').value
    };

    if (!payload.reference) {
        showToast('Reference is required.', 'error');
        return;
    }

    try {
        const url = currentEditIncidentId
            ? `/api/v1/incidents/${currentEditIncidentId}`
            : '/api/v1/incidents';
        const method = currentEditIncidentId ? 'PATCH' : 'POST';

        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            let detail = 'Failed to save incident';
            try { const d = await res.json(); if (d && d.detail) detail = d.detail; } catch (e) {}
            throw new Error(detail);
        }

        showToast('Incident saved successfully!', 'success');
        delete incidentListCache[currentIncidentStatusView];
        delete incidentListCache[payload.status];
        const newStatus = payload.status;
        resetIncidentForm();
        if (newStatus && newStatus !== currentIncidentStatusView) {
            switchIncidentView(newStatus, { skipDirtyCheck: true });
        } else {
            fetchIncidentsForDropdown(currentIncidentStatusView);
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function downloadIncidentImage() {
    captureElement('incidentCaptureZone', `Incident_${document.getElementById('inc_ref').value || 'New'}.png`);
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('incidentPanel')) {
        switchIncidentView('ongoing', { skipDirtyCheck: true });
    }
});



