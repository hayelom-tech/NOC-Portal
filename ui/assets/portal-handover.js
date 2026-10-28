function isShiftActive(shift, now = new Date()) {
    if (!shift.start_time || !shift.end_time) return false;
    const toMinutes = value => {
        const [hours, minutes] = value.split(':').map(Number);
        return hours * 60 + minutes;
    };
    const current = addisHour() * 60 + addisMinutes();
    const start = toMinutes(shift.start_time);
    const end = toMinutes(shift.end_time);
    const today = localDateValue(now);
    if (start <= end) {
        return shift.shift_date === today && current >= start && current < end;
    }
    if (current >= start) return shift.shift_date === today;
    const previousDate = new Date(now);
    previousDate.setDate(previousDate.getDate() - 1);
    return current < end && shift.shift_date === localDateValue(previousDate);
}

async function loadShifts(autoSelectCurrent = false) {
    let rows = await api(`/api/v1/shifts?date=${encodeURIComponent(shiftDate.value)}`);
    let activeShift = autoSelectCurrent ? rows.find(row => isShiftActive(row)) : null;
    if (autoSelectCurrent && !activeShift) {
        const previousDate = new Date(`${shiftDate.value}T12:00:00`);
        previousDate.setDate(previousDate.getDate() - 1);
        const previousDateValue = localDateValue(previousDate);
        const previousRows = await api(`/api/v1/shifts?date=${encodeURIComponent(previousDateValue)}`);
        activeShift = previousRows.find(row => isShiftActive(row));
        if (activeShift) {
            shiftDate.value = previousDateValue;
            rows = previousRows;
        }
    }
    shiftSelect.replaceChildren();
    for (const shift of rows) {
        const option = document.createElement('option');
        option.value = shift.id;
        option.dataset.shiftName = shift.shift_name;
        option.dataset.startTime = shift.start_time || '';
        option.dataset.endTime = shift.end_time || '';
        option.textContent = shiftLabels[shift.shift_name];
        shiftSelect.append(option);
    }
    if (!rows.length) {
        selectedShift = null;
        clearShiftData();
        await loadHomeDomainShiftCards();
        setStatus('No imported shifts for this date.');
        return;
    }
    selectedShift = (autoSelectCurrent && activeShift)
        || rows.find(row => String(row.id) === shiftSelect.value)
        || activeShift
        || rows[0];
    shiftSelect.value = selectedShift.id;
    setStatus(shiftSummary(selectedShift));
    await loadSelectedShift();
    await loadHomeDomainShiftCards();
}

function shiftSummary(shift) {
    const window = shift.start_time && shift.end_time ? ` · ${shift.start_time.slice(0, 5)}–${shift.end_time.slice(0, 5)}` : '';
    return `${shiftLabels[shift.shift_name]} shift · ${shift.shift_date}${window}`;
}

function clearShiftData() {
    document.getElementById('handoverContent').replaceChildren();
    document.getElementById('handoverForm').classList.add('hidden');
    document.getElementById('previousChallenges').textContent = 'Previous shift challenges: —';
    renderPreviousShiftDetails(null);
}

async function loadPreviousHandover(shift) {
    const previousDate = new Date(`${shift.shift_date}T12:00:00`);
    previousDate.setDate(previousDate.getDate() - 1);
    const shifts = await api(
        `/api/v1/shifts?start_date=${localDateValue(previousDate)}&end_date=${encodeURIComponent(shift.shift_date)}&limit=100`
    );
    const ordered = shifts.sort((left, right) =>
        left.shift_date.localeCompare(right.shift_date)
        || shiftOrder[left.shift_name] - shiftOrder[right.shift_name]
    );
    const currentIndex = ordered.findIndex(item => String(item.id) === String(shift.id));
    const previousShift = currentIndex > 0 ? ordered[currentIndex - 1] : null;
    if (!previousShift) return null;
    try {
        return { shift: previousShift, handover: await api(`/api/v1/shifts/${previousShift.id}/handover`) };
    } catch (error) {
        if (error.message.includes('No handover')) return { shift: previousShift, handover: null };
        throw error;
    }
}

function renderPreviousShiftDetails(previous) {
    const container = document.getElementById('previousShiftDetails');
    const label = document.getElementById('previousShiftLabel');
    const section = document.getElementById('previousShiftSection');
    container.replaceChildren();
    section.classList.add('hidden');
    if (!previous) {
        return;
    }

    const record = previous.handover;
    if (!record?.operational_challenges || !canViewChallenge(record)) return;

    const date = new Date(`${previous.shift.shift_date}T12:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    label.textContent = `${date} · ${shiftLabels[previous.shift.shift_name]} shift`;
    section.classList.remove('hidden');

    const teams = (record.field_teams || []).map(team => [`Site ${team.site_id}`, team.name, team.phone].filter(Boolean).join(' · '));
    if (!teams.length && record.active_field_teams) teams.push(record.active_field_teams);
    const regions = (record.regions || []).map(region => {
        const count = region.corrective_maintenance_count ?? 0;
        return `${region.region_name}: ${count}${region.notes ? ` — ${region.notes}` : ''}`;
    });
    const details = [
        ['Operational challenges', record.operational_challenges ? 'Yes' : 'No'],
        ['Update for next shift', record.update_for_next_shift],
        ['Active change requests', record.active_change_requests],
        ['Planned maintenance', record.planned_maintenance],
        ['Active field teams', teams.join('\n')],
        ['Major incidents', record.major_incidents],
        ['Resolved major incidents', record.resolved_major_incidents],
        ['Alarms pending resolution', record.alarms_pending_resolution],
        ['Closed trouble tickets', record.closed_trouble_tickets],
        ['Corrective maintenance by region', regions.join('\n')],
        ['Archived handover index', record.archived_handover_index]
    ].filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '');

    for (const [title, value] of details) {
        const card = node('article', null, 'rounded-lg border border-slate-800 bg-slate-950/70 p-3');
        card.append(
            node('h3', title, 'mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400'),
            node('p', String(value), 'whitespace-pre-wrap break-words text-sm text-slate-100')
        );
        container.append(card);
    }
}

function canViewChallenge(record) {
    if (currentUser?.role === 'admin') return true;
    const domain = record?.challenge_domain;
    if (!domain) return false;
    return selectedShiftRoster.some(member => {
        const team = String(member.team || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        const isTargetDomain = domain === 'power'
            ? team.includes('power') || team === 'pwr'
            : team.includes('transmission') || team === 'tx';
        return isTargetDomain && member.assigned_to_current_user === true;
    });
}

async function loadSelectedShift() {
    if (!selectedShift) return;
    const id = selectedShift.id;
    const handoverDate = new Date(`${selectedShift.shift_date}T12:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    document.getElementById('handoverShiftLabel').textContent = `${handoverDate} · ${shiftLabels[selectedShift.shift_name]} shift`;
    const [handover, previousHandover, rosterRows] = await Promise.all([
        api(`/api/v1/shifts/${id}/handover`).catch(error => (error.message.includes('No handover') || error.message.includes('404')) ? null : Promise.reject(error)),
        loadPreviousHandover(selectedShift),
        api(`/api/v1/roster?date=${encodeURIComponent(selectedShift.shift_date)}`).catch(() => [])
    ]);
    selectedShiftRoster = rosterRows.filter(member => member.shift_name === selectedShift.shift_name);
    const previousChallenges = document.getElementById('previousChallenges');
    const hasPreviousChallenges = Boolean(previousHandover?.handover?.operational_challenges);
    previousChallenges.replaceChildren(
        node('span', 'Previous shift challenges: ', 'text-slate-400'),
        node('span', hasPreviousChallenges ? 'Yes' : 'No', hasPreviousChallenges
            ? 'font-semibold text-rose-400'
            : 'font-semibold text-emerald-400')
    );
    renderPreviousShiftDetails(previousHandover);
    renderHandover(handover);
}

function renderHandover(record) {
    const content = document.getElementById('handoverContent');
    content.replaceChildren();
    if (!record) {
        if (canSubmitHandover()) {
            document.getElementById('handoverForm').classList.remove('hidden');
            fillHandoverForm(null);
        }
        return;
    }
    const values = [
        ['Next shift', shiftLabels[record.next_shift_name]],
        ...(record.operational_challenges && canViewChallenge(record) ? [
            ['Operational challenges', `${record.challenge_domain === 'tx' ? 'Transmission' : 'Power'}: Yes`],
            ['Update for next shift', record.update_for_next_shift],
            ['Active change requests', record.active_change_requests],
            ['Planned maintenance', record.planned_maintenance]
        ] : []),
        ['Active field teams', [
            ...(record.field_teams || []).map(team => [
                `Site ${team.site_id}`,
                team.name,
                team.phone
            ].filter(Boolean).join(' · ')),
            record.active_field_teams
        ].filter(Boolean).join('\n')],
        ['Major incidents', record.major_incidents],
        ['Resolved major incidents', record.resolved_major_incidents],
        ['Alarms pending resolution', record.alarms_pending_resolution],
        ['Closed trouble tickets', String(record.closed_trouble_tickets)],
        ['Archived record index', record.archived_handover_index]
    ];
    for (const [label, value] of values) {
        const card = document.createElement('div');
        card.className = 'rounded-lg bg-slate-950 p-3';
        const heading = document.createElement('h3');
        heading.className = 'mb-1 text-xs font-semibold uppercase text-slate-500';
        heading.textContent = label;
        const body = document.createElement('p');
        body.className = 'whitespace-pre-wrap text-sm';
        body.textContent = value || '—';
        card.append(heading, body);
        content.append(card);
    }
    const acknowledgement = document.createElement('div');
    acknowledgement.className = 'mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm';
    if (record.acknowledged_at) {
        const acknowledgedAt = new Date(record.acknowledged_at).toLocaleString();
        acknowledgement.append(node(
            'p',
            `Acknowledged by user #${record.acknowledged_by_id} · ${acknowledgedAt}`,
            'text-emerald-300'
        ));
    } else {
        acknowledgement.append(node('p', 'Awaiting acknowledgement.', 'text-amber-300'));
        if (canSubmitHandover()) {
            const acknowledgeButton = node('button', 'Acknowledge handover', 'rounded bg-emerald-700 px-3 py-2 text-sm font-semibold');
            acknowledgeButton.type = 'button';
            acknowledgeButton.addEventListener('click', async () => {
                acknowledgeButton.disabled = true;
                try {
                    await api(`/api/v1/shifts/${selectedShift.id}/handover/acknowledge`, { method: 'POST' });
                    setStatus('Handover acknowledged.');
                    await loadSelectedShift();
                } catch (error) {
                    acknowledgeButton.disabled = false;
                    setStatus(error.message, true);
                }
            });
            acknowledgement.append(acknowledgeButton);
        }
    }
    content.append(acknowledgement);
    if (canSubmitHandover() && (!record.operational_challenges || canViewChallenge(record))) {
        document.getElementById('handoverForm').classList.remove('hidden');
        fillHandoverForm(record);
    }
}

function updateChallengeDetails() {
    const hasChallenges = document.getElementById('challengeYes').checked;
    document.getElementById('challengeDetails').classList.toggle('hidden', !hasChallenges);
    document.getElementById('liveNetworkActivity').classList.toggle('hidden', !hasChallenges);
    const challengeDomain = document.getElementById('challengeDomain');
    challengeDomain.required = hasChallenges;
    if (!hasChallenges) {
        challengeDomain.value = '';
        document.getElementById('nextUpdate').value = '';
        document.getElementById('changeRequests').value = '';
        document.getElementById('maintenance').value = '';
    }
}

function fillHandoverForm(record) {
    const handoverForm = document.getElementById('handoverForm');
    if (record?.updated_at) handoverForm.dataset.expectedUpdatedAt = record.updated_at;
    else delete handoverForm.dataset.expectedUpdatedAt;
    const nextShift = document.getElementById('nextShift');
    nextShift.replaceChildren();
    for (const name of Object.keys(shiftLabels)) {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = shiftLabels[name];
        nextShift.append(option);
    }
    const followingShift = { morning: 'afternoon', afternoon: 'night', night: 'morning' };
    nextShift.value = followingShift[selectedShift.shift_name];
    document.getElementById('nextShiftDisplay').textContent = `${shiftLabels[nextShift.value]} shift`;
    document.getElementById('challengeYes').checked = record?.operational_challenges || false;
    document.getElementById('challengeNo').checked = !record?.operational_challenges;
    document.getElementById('challenges').checked = record?.operational_challenges || false;
    document.getElementById('challengeDomain').value = record?.challenge_domain || '';
    document.getElementById('nextUpdate').value = record?.update_for_next_shift || '';
    updateChallengeDetails();
    document.getElementById('changeRequests').value = record?.active_change_requests || '';
    document.getElementById('maintenance').value = record?.planned_maintenance || '';
    const fieldTeamsEditor = document.getElementById('fieldTeamsEditor');
    fieldTeamsEditor.dataset.legacyFieldTeams = record?.active_field_teams || '';
    fieldTeamsEditor.replaceChildren();
    for (const team of record?.field_teams || []) {
        addFieldTeamRow(team);
    }
    updateFieldTeamControls();
    document.getElementById('majorIncidents').value = record?.major_incidents || '';
    document.getElementById('resolvedIncidents').value = record?.resolved_major_incidents || '';
    document.getElementById('pendingAlarms').value = record?.alarms_pending_resolution || '';
    document.getElementById('closedTickets').value = record?.closed_trouble_tickets || 0;
    document.getElementById('archiveIndex').value = record?.archived_handover_index || '';

    const regionEditor = document.getElementById('regionEditor');
    regionEditor.replaceChildren();
    const savedRegions = new Map((record?.regions || []).map(region => [region.region_name, region]));
    const regions = regionNames.map(region_name => ({
        region_name,
        corrective_maintenance_count: 0,
        notes: '',
        ...(savedRegions.get(region_name) || {})
    }));
    for (const region of regions) {
        const row = document.createElement('div');
        row.className = 'grid gap-2 sm:grid-cols-3';
        for (const [key, type, placeholder] of [
            ['region_name', 'fixed', 'Region'],
            ['corrective_maintenance_count', 'number', 'Maintenance count'],
            ['notes', 'text', 'Notes']
        ]) {
            if (type === 'fixed') {
                const label = node('span', region[key], 'flex min-w-0 items-center rounded bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200');
                label.dataset.field = key;
                row.append(label);
            } else {
                const input = document.createElement('input');
                input.type = type;
                input.placeholder = placeholder;
                input.dataset.field = key;
                input.value = region[key] ?? '';
                input.className = 'min-w-0 rounded bg-slate-950 px-3 py-2 text-sm';
                if (type === 'number') {
                    input.min = '0';
                    input.max = '50';
                }
                row.append(input);
            }
        }
        regionEditor.append(row);
    }
    if (!record && restoreHandoverDraft()) {
        showToast('Restored unsaved handover draft from browser storage.');
    }
}

function saveHandoverDraft() {
    if (!selectedShift) return;
    try {
        const draft = {
            nextUpdate: document.getElementById('nextUpdate')?.value || '',
            changeRequests: document.getElementById('changeRequests')?.value || '',
            maintenance: document.getElementById('maintenance')?.value || '',
            majorIncidents: document.getElementById('majorIncidents')?.value || '',
            resolvedIncidents: document.getElementById('resolvedIncidents')?.value || '',
            pendingAlarms: document.getElementById('pendingAlarms')?.value || '',
            closedTickets: document.getElementById('closedTickets')?.value || '',
            challengeYes: document.getElementById('challengeYes')?.checked || false,
            challengeDomain: document.getElementById('challengeDomain')?.value || '',
            timestamp: Date.now()
        };
        localStorage.setItem(`noc_handover_draft_${selectedShift.id}`, JSON.stringify(draft));
    } catch (_) {}
}

function clearHandoverDraft() {
    if (!selectedShift) return;
    try {
        localStorage.removeItem(`noc_handover_draft_${selectedShift.id}`);
    } catch (_) {}
}

function restoreHandoverDraft() {
    if (!selectedShift) return false;
    try {
        const raw = localStorage.getItem(`noc_handover_draft_${selectedShift.id}`);
        if (!raw) return false;
        const draft = JSON.parse(raw);
        if (Date.now() - (draft.timestamp || 0) > 12 * 3600 * 1000) return false;
        let restored = false;
        if (draft.nextUpdate && !document.getElementById('nextUpdate').value) {
            document.getElementById('nextUpdate').value = draft.nextUpdate;
            restored = true;
        }
        if (draft.changeRequests && !document.getElementById('changeRequests').value) {
            document.getElementById('changeRequests').value = draft.changeRequests;
            restored = true;
        }
        if (draft.maintenance && !document.getElementById('maintenance').value) {
            document.getElementById('maintenance').value = draft.maintenance;
            restored = true;
        }
        if (draft.challengeYes) {
            document.getElementById('challengeYes').checked = true;
            document.getElementById('challengeNo').checked = false;
            updateChallengeDetails();
            if (draft.challengeDomain) document.getElementById('challengeDomain').value = draft.challengeDomain;
            restored = true;
        }
        if (draft.majorIncidents && !document.getElementById('majorIncidents').value) {
            document.getElementById('majorIncidents').value = draft.majorIncidents;
            restored = true;
        }
        if (draft.resolvedIncidents && !document.getElementById('resolvedIncidents').value) {
            document.getElementById('resolvedIncidents').value = draft.resolvedIncidents;
            restored = true;
        }
        if (draft.pendingAlarms && !document.getElementById('pendingAlarms').value) {
            document.getElementById('pendingAlarms').value = draft.pendingAlarms;
            restored = true;
        }
        if (draft.closedTickets && !document.getElementById('closedTickets').value) {
            document.getElementById('closedTickets').value = draft.closedTickets;
            restored = true;
        }
        return restored;
    } catch (_) {
        return false;
    }
}

function updateFieldTeamControls() {
    const editor = document.getElementById('fieldTeamsEditor');
    const addButton = document.getElementById('addFieldTeamButton');
    const atLimit = editor.children.length >= 6;
    addButton.disabled = atLimit;
    addButton.classList.toggle('opacity-50', atLimit);
    for (const input of editor.querySelectorAll('[data-field-team-field="site_id"], [data-field-team-field="name"]')) {
        input.required = true;
    }
}

function addFieldTeamRow(team = {}) {
    const editor = document.getElementById('fieldTeamsEditor');
    if (editor.children.length >= 6) return;

    const phoneDigits = (team.phone || '').replace(/^\+251/, '');
    const row = document.createElement('div');
    row.className = 'grid gap-2 sm:grid-cols-[120px_1fr_1fr_auto]';
    for (const [field, labelText, placeholder, pattern] of [
        ['site_id', 'Site ID', '1–6 digits', '[0-9]{1,6}'],
        ['name', 'Team member name', 'Name', null]
    ]) {
        const label = document.createElement('label');
        label.className = 'grid gap-1 text-xs text-slate-400';
        label.textContent = labelText;
        const input = document.createElement('input');
        input.type = 'text';
        input.dataset.fieldTeamField = field;
        input.value = team[field] || '';
        input.placeholder = placeholder;
        input.className = 'min-w-0 rounded bg-slate-950 px-3 py-2 text-sm text-slate-100';
        if (field === 'site_id') {
            input.inputMode = 'numeric';
            input.maxLength = 6;
        } else {
            input.maxLength = 160;
        }
        if (pattern) input.pattern = pattern;
        label.append(input);
        row.append(label);
    }
    const phoneLabel = document.createElement('label');
    phoneLabel.className = 'grid gap-1 text-xs text-slate-400';
    phoneLabel.textContent = 'Phone';
    const phoneGroup = document.createElement('div');
    phoneGroup.className = 'flex items-stretch';
    const phonePrefix = document.createElement('span');
    phonePrefix.className = 'flex items-center rounded-l border border-r-0 border-slate-700 bg-slate-900 px-3 text-sm text-slate-400';
    phonePrefix.textContent = '+251';
    const phoneInput = document.createElement('input');
    phoneInput.type = 'text';
    phoneInput.dataset.fieldTeamField = 'phone_digits';
    phoneInput.value = phoneDigits;
    phoneInput.placeholder = '9 digits';
    phoneInput.inputMode = 'numeric';
    phoneInput.maxLength = 9;
    phoneInput.pattern = '[0-9]{9}';
    phoneInput.className = 'w-full min-w-0 rounded-r bg-slate-950 px-3 py-2 text-sm text-slate-100';
    phoneGroup.append(phonePrefix, phoneInput);
    phoneLabel.append(phoneGroup);
    row.append(phoneLabel);
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.textContent = 'Remove';
    removeButton.setAttribute('aria-label', 'Remove field team');
    removeButton.className = 'self-end rounded bg-slate-700 px-3 py-2 text-xs';
    removeButton.addEventListener('click', () => {
        row.remove();
        updateFieldTeamControls();
    });
    row.append(removeButton);
    editor.append(row);
    updateFieldTeamControls();
}

document.getElementById('handoverForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
        const fieldTeams = [...document.querySelectorAll('#fieldTeamsEditor > div')].map((row, position) => {
            const team = Object.fromEntries([...row.querySelectorAll('[data-field-team-field]')]
                .map(input => [input.dataset.fieldTeamField, input.value.trim()]));
            team.phone = team.phone_digits ? `+251${team.phone_digits}` : null;
            delete team.phone_digits;
            team.position = position;
            return team;
        });
        const legacyFieldTeams = document.getElementById('fieldTeamsEditor').dataset.legacyFieldTeams || '';
        const regions = [...document.querySelectorAll('#regionEditor > div')].map(row => {
            const values = {};
            for (const input of row.querySelectorAll('[data-field]')) {
                values[input.dataset.field] = input.value ?? input.textContent;
            }
            values.corrective_maintenance_count = Number(values.corrective_maintenance_count || 0);
            return values;
        });
        const payload = {
            expected_updated_at: document.getElementById('handoverForm').dataset.expectedUpdatedAt || null,
            next_shift_name: document.getElementById('nextShift').value,
            update_for_next_shift: document.getElementById('nextUpdate').value,
            operational_challenges: document.getElementById('challengeYes').checked,
            challenge_domain: document.getElementById('challengeYes').checked
                ? document.getElementById('challengeDomain').value
                : null,
            active_change_requests: document.getElementById('changeRequests').value,
            planned_maintenance: document.getElementById('maintenance').value,
            active_field_teams: legacyFieldTeams,
            field_teams: fieldTeams,
            major_incidents: document.getElementById('majorIncidents').value,
            resolved_major_incidents: document.getElementById('resolvedIncidents').value,
            alarms_pending_resolution: document.getElementById('pendingAlarms').value,
            closed_trouble_tickets: Number(document.getElementById('closedTickets').value || 0),
            archived_handover_index: document.getElementById('archiveIndex').value || null,
            regions
        };
        await api(`/api/v1/shifts/${selectedShift.id}/handover`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        setStatus('Handover saved.');
        clearHandoverDraft();
        await loadSelectedShift();
    } catch (error) {
        setStatus(error.message, true);
    }
});
document.getElementById('handoverForm')?.addEventListener('input', saveHandoverDraft);
