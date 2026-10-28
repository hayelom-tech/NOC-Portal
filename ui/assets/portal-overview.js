function renderTableRows(target, rows, columns) {
    target.replaceChildren();
    if (!rows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.textContent = 'No records for this shift.';
        td.className = 'py-3 text-slate-500';
        td.colSpan = columns.length;
        tr.append(td);
        target.append(tr);
        return;
    }
    for (const row of rows) {
        const tr = document.createElement('tr');
        tr.className = 'border-t border-slate-800';
        for (const column of columns) {
            const td = document.createElement('td');
            td.className = 'py-2 pr-3';
            td.textContent = column(row) || '—';
            tr.append(td);
        }
        target.append(tr);
    }
}

function localDateValue(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

async function loadHomeDomainShiftCards() {
    const requestId = ++homeRosterRequestId;
    const now = new Date();
    const currentHour = addisHour();
    const fallbackShiftName = currentHour >= 6 && currentHour < 14
        ? 'morning'
        : currentHour >= 14 && currentHour < 22 ? 'afternoon' : 'night';
    const addisNow = addisDate();
    const fallbackDate = currentHour < 6
        ? localDateValue(new Date(addisNow.getFullYear(), addisNow.getMonth(), addisNow.getDate() - 1))
        : localDateValue(addisNow);
    const dateValue = selectedShift?.shift_date || fallbackDate;
    const shiftName = fallbackShiftName;
    const dateLabel = dateValue
        ? new Date(`${dateValue}T12:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
        : '—';
    const shiftLabel = shiftName ? shiftLabels[shiftName] : '—';
    document.getElementById('homeCurrentDate').textContent = 'Date: ' + dateLabel;
    document.getElementById('homeCurrentShift').textContent = 'Shift: ' + shiftLabel;
    const domains = [
        { key: 'power', date: 'homePowerDate', shift: 'homePowerShift', people: 'homePowerPeople' },
        { key: 'tx', date: 'homeTxDate', shift: 'homeTxShift', people: 'homeTxPeople' },
    ];
    for (const domain of domains) {
        document.getElementById(domain.date).textContent = `Date: ${dateLabel}`;
        document.getElementById(domain.shift).textContent = `Shift: ${shiftLabel}`;
        document.getElementById(domain.people).replaceChildren(
            node('p', shiftName ? 'Loading shift roster…' : 'No active shift is available for this date.', 'text-slate-400')
        );
    }
    if (!shiftName || !dateValue) return;
    try {
        const rows = await api(`/api/v1/roster?date=${encodeURIComponent(dateValue)}`);
        if (requestId !== homeRosterRequestId) return;
        const normalize = value => String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        for (const domain of domains) {
            const target = document.getElementById(domain.people);
            const members = rows.filter(row => {
                const team = normalize(row.team);
                const teamDomain = ['tx', 'transmission'].includes(team) ? 'tx' : team;
                return row.shift_name === shiftName && teamDomain === domain.key;
            });
            target.replaceChildren();
            if (!members.length) {
                target.append(node('p', `No ${domain.key === 'tx' ? 'TX' : 'Power'} staff assigned to this shift.`, 'rounded-lg border border-white/5 bg-slate-950/30 px-3 py-3 text-sm text-slate-400'));
                continue;
            }
            for (const member of members) {
                const line = node('div', member.member_name, 'rounded-lg border border-white/5 bg-slate-950/30 px-3 py-3 font-medium text-slate-100');
                target.append(line);
            }
        }
    } catch (error) {
        if (requestId !== homeRosterRequestId) return;
        for (const domain of domains) {
            document.getElementById(domain.people).replaceChildren(
                node('p', error.message, 'rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-3 text-sm text-red-300')
            );
        }
    }
}

async function loadL2Roster() {
    const roster = await api('/api/v1/l2-roster');
    const groups = document.getElementById('l2Groups');
    groups.replaceChildren();
    const domains = [
        ['power', 'Power', ['power', 'pwr'], 'fa-bolt', 'amber'],
        ['ran', 'RAN', ['ran', 'radio access network', 'radio access network ran'], 'fa-tower-cell', 'emerald'],
        ['tx', 'TX', ['tx', 'transmission'], 'fa-route', 'sky'],
        ['ps_core_sdm', 'PS Core & SDM', ['pscoresdm', 'ps core', 'ps core sdm'], 'fa-network-wired', 'violet'],
        ['cs_core_volte', 'CS Core & VoLTE', ['cscorevolte', 'cs core', 'cs core volte'], 'fa-server', 'rose'],
    ];
    groups.className = 'grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3';
    const domainColors = {
        amber: ['border-amber-900/60 bg-gradient-to-br from-amber-950/50 to-slate-900', 'bg-amber-900/50 text-amber-300'],
        emerald: ['border-emerald-900/60 bg-gradient-to-br from-emerald-950/45 to-slate-900', 'bg-emerald-900/50 text-emerald-300'],
        sky: ['border-sky-900/60 bg-gradient-to-br from-sky-950/45 to-slate-900', 'bg-sky-900/50 text-sky-300'],
        violet: ['border-violet-900/60 bg-gradient-to-br from-violet-950/45 to-slate-900', 'bg-violet-900/50 text-violet-300'],
        rose: ['border-rose-900/60 bg-gradient-to-br from-rose-950/40 to-slate-900', 'bg-rose-900/50 text-rose-300'],
    };
    for (const [domain, label, aliases, iconName, color] of domains) {
        const normalize = value => String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        const acceptedNames = new Set([domain, ...aliases].map(normalize));
        const members = roster
            .filter(row => acceptedNames.has(normalize(row.department)))
            .map((member, index) => ({ member, index }))
            .sort((a, b) => {
                const tierOrder = tier => tier === 'primaryl2' ? 0 : ['secondaryl2', 'secondarycover'].includes(tier) ? 1 : 2;
                return tierOrder(normalize(a.member.tier)) - tierOrder(normalize(b.member.tier)) || a.index - b.index;
            })
            .map(({ member }) => member);
        const section = document.createElement('section');
        section.className = `rounded-2xl border p-4 shadow-lg shadow-black/10 ${domainColors[color][0]}`;
        const titleRow = document.createElement('div');
        titleRow.className = 'mb-4 flex items-center gap-3';
        const icon = node('div', '', `flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-lg ${domainColors[color][1]}`);
        icon.innerHTML = `<i class="fa-solid ${iconName}" aria-hidden="true"></i>`;
        const heading = document.createElement('h3');
        heading.className = 'font-semibold text-slate-100';
        heading.textContent = label;
        const subtitle = node('p', `${members.length} ${members.length === 1 ? 'contact' : 'contacts'}`, 'mt-0.5 text-xs text-slate-400');
        const headingText = document.createElement('div');
        headingText.append(heading, subtitle);
        titleRow.append(icon, headingText);
        const list = document.createElement('ul');
        list.className = 'space-y-2';
        if (!members.length) {
            const empty = document.createElement('li');
            empty.className = 'rounded-xl border border-white/5 bg-slate-950/25 px-3 py-3 text-sm text-slate-400';
            empty.textContent = 'No roster members listed.';
            list.append(empty);
        }
        for (const member of members) {
            const item = document.createElement('li');
            item.className = 'rounded-xl border border-white/5 bg-slate-950/35 px-3 py-3';
            const personHead = document.createElement('div');
            personHead.className = 'flex flex-wrap items-center justify-between gap-2';
            const name = node('div', member.engineer_name, 'text-sm font-semibold text-slate-100');
            personHead.append(name);
            if (member.tier) {
                personHead.append(node('span', member.tier, `rounded-full px-2.5 py-1 text-[11px] font-medium ${domainColors[color][1]}`));
            }
            const details = document.createElement('div');
            details.className = 'mt-2 grid gap-1 text-xs text-slate-300';
            if (member.week) details.append(node('div', `Week ${member.week}`, 'text-slate-400'));
            if (member.phone) {
                const phone = node('a', member.phone, 'hover:text-white');
                phone.href = `tel:${member.phone.replace(/[^+\d]/g, '')}`;
                details.append(phone);
            }
            if (member.email) {
                const email = node('a', member.email, 'break-all hover:text-white');
                email.href = `mailto:${member.email}`;
                details.append(email);
            }
            item.append(personHead, details);
            list.append(item);
        }
        section.append(titleRow, list);
        groups.append(section);
    }
}

function openKnowledgeDomain(domain) {
    const form = document.getElementById('knowledgeForm');
    form.reset();
    form.classList.add('hidden');
    selectedKnowledgeDomain = domain;
    knowledgeArticleQuery = '';
    updateKnowledgePostsHeading(domain);
    activateTab('knowledge');
    document.getElementById('portalSectionTitle').textContent = domainLabels[domain] || 'Knowledge Hub';
    setKnowledgeSubnavActive(document.querySelector(`[data-knowledge-domain="${domain}"]`));
    openKnowledgePostsView();
    loadLibrary().catch(error => setStatus(error.message, true));
}

function updateKnowledgePostsHeading(domain) {
    const label = domain ? domainLabels[domain] || domain : '';
    document.getElementById('knowledgePostsHeading').textContent = label ? `${label} Articles` : 'All Knowledge Articles';
    document.getElementById('knowledgePostsDescription').textContent = label
        ? `Published posts in the ${label} domain.`
        : 'Browse published posts from every domain.';
}

function setKnowledgeSubnavActive(activeItem) {
    for (const item of document.querySelectorAll('[data-knowledge-domain]')) {
        const active = item === activeItem;
        item.classList.toggle('bg-blue-600', active);
        item.classList.toggle('text-white', active);
        item.classList.toggle('font-medium', active);
        item.classList.toggle('shadow-md', active);
        if (active) item.setAttribute('aria-current', 'page');
        else item.removeAttribute('aria-current');
    }
}

function openKnowledgePostsView() {
    document.getElementById('knowledgeDashboardView').classList.add('hidden');
    document.getElementById('knowledgePostsView').classList.remove('hidden');
    document.getElementById('knowledgePostsView').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openKnowledgeDashboardView() {
    document.getElementById('portalSectionTitle').textContent = 'Knowledge Hub';
    document.getElementById('knowledgePostsView').classList.add('hidden');
    document.getElementById('knowledgeDashboardView').classList.remove('hidden');
    setKnowledgeSubnavActive(null);
}

async function loadRecentKnowledge() {
    const recent = await api('/api/v1/knowledge-hub/recent');
    const domains = {
        power: { label: 'Power', badge: 'domain-power' },
        ran: { label: 'RAN', badge: 'domain-ran' },
        tx: { label: 'TX', badge: 'domain-tx' },
        core: { label: 'Core', badge: 'domain-core' },
    };
    for (const [domain, config] of Object.entries(domains)) {
        const container = document.getElementById(`recent-post-${domain}`);
        const article = recent[domain];
        container.replaceChildren();
        container.setAttribute('aria-label', `Open recent ${config.label} article`);
        container.append(node('span', config.label, `domain-badge ${config.badge}`));
        if (!article) {
            container.append(node('p', 'No recent posts yet.', 'text-sm text-slate-500'));
            continue;
        }
        const summary = article.symptoms || article.resolution || 'Open this article to view its troubleshooting details.';
        const createdAt = article.created_at ? new Date(article.created_at) : null;
        const dateLabel = createdAt && !Number.isNaN(createdAt.getTime())
            ? createdAt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
            : 'Recently added';
        container.append(
            node('h4', article.issue_title, 'line-clamp-2 text-sm font-semibold'),
            node('p', summary, 'line-clamp-3 text-xs opacity-80'),
            node('span', `Recently added · ${dateLabel}`, 'mt-auto text-[11px] opacity-70')
        );
    }
}

async function loadNotifications() {
    if (currentUser?.role !== 'admin') return;
    const notifications = await api('/api/v1/notifications');
    const list = document.getElementById('notificationList');
    const badge = document.getElementById('notificationBadge');
    const unread = notifications.filter(item => !item.is_read).length;
    badge.textContent = unread > 99 ? '99+' : String(unread);
    badge.classList.toggle('hidden', unread === 0);
    list.replaceChildren();
    if (!notifications.length) {
        list.append(node('p', 'No notifications yet.', 'px-3 py-4 text-sm text-slate-400'));
        return;
    }
    for (const notification of notifications) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = `block w-full rounded-lg px-3 py-2 text-left hover:bg-slate-800 ${notification.is_read ? 'opacity-70' : ''}`;
        item.append(
            node('span', notification.article_title, 'block text-sm font-medium text-slate-100'),
            node('span', notification.message, 'mt-0.5 block text-xs text-slate-400'),
            node('span', `${domainLabels[notification.domain] || notification.domain} · ${new Date(notification.created_at).toLocaleString()}`, 'mt-1 block text-[11px] text-slate-500')
        );
        item.addEventListener('click', async () => {
            if (!notification.is_read) {
                await api(`/api/v1/notifications/${notification.id}/read`, { method: 'PATCH' });
            }
            document.getElementById('notificationMenu').classList.add('hidden');
            document.getElementById('notificationButton').setAttribute('aria-expanded', 'false');
            activateTab('knowledge');
            openKnowledgeDashboardView();
            await loadPendingKnowledge();
            await loadNotifications();
        });
        list.append(item);
    }
}

async function loadPendingKnowledge() {
    if (currentUser?.role !== 'admin') return;
    const pending = await api('/api/v1/knowledge-hub/pending');
    const section = document.getElementById('adminApprovalSection');
    const list = document.getElementById('pendingPostsList');
    list.replaceChildren();
    section.classList.toggle('hidden', pending.length === 0);
    const badgeClasses = {
        power: 'domain-power', ran: 'domain-ran', tx: 'domain-tx', core: 'domain-core'
    };
    for (const article of pending) {
        const card = document.createElement('article');
        card.className = 'rounded-lg border border-amber-200 bg-white p-4 text-slate-900 dark:border-amber-900/50 dark:bg-slate-900 dark:text-slate-100';
        const titleRow = document.createElement('div');
        titleRow.className = 'flex flex-wrap items-center justify-between gap-2';
        titleRow.append(
            node('h4', article.issue_title, 'font-semibold'),
            node('span', domainLabels[article.domain] || article.domain, `domain-badge ${badgeClasses[article.domain] || 'domain-core'}`)
        );
        const author = node('p', `Submitted by ${article.author_name} (@${article.author_username}) · ${new Date(article.created_at).toLocaleString()}`, 'mt-1 text-xs text-slate-500 dark:text-slate-400');
        const summary = node('p', article.symptoms, 'mt-3 whitespace-pre-wrap text-sm');
        const details = document.createElement('details');
        details.className = 'mt-3 text-sm';
        details.append(node('summary', 'Review full post', 'cursor-pointer font-medium text-sky-700 dark:text-sky-300'));
        for (const [label, value] of [
            ['Root cause', article.root_cause],
            ['Troubleshooting steps', article.troubleshooting_steps],
            ['Resolution', article.resolution],
        ]) {
            details.append(node('h5', label, 'mt-2 font-semibold'));
            details.append(node('p', value, 'whitespace-pre-wrap text-slate-600 dark:text-slate-300'));
        }
        const actions = document.createElement('div');
        actions.className = 'mt-4 flex gap-2';
        const approve = node('button', 'Approve', 'rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-600');
        const reject = node('button', 'Reject', 'rounded-lg bg-rose-700 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-600');
        approve.type = reject.type = 'button';
        approve.addEventListener('click', () => reviewKnowledgeArticle(article.id, 'approve', approve, reject));
        reject.addEventListener('click', () => reviewKnowledgeArticle(article.id, 'reject', approve, reject));
        actions.append(approve, reject);
        card.append(titleRow, author, summary, details, actions);
        list.append(card);
    }
}

async function reviewKnowledgeArticle(articleId, action, approveButton, rejectButton) {
    approveButton.disabled = rejectButton.disabled = true;
    try {
        await api(`/api/v1/knowledge-hub/${articleId}/${action}`, { method: 'POST' });
        setStatus(action === 'approve' ? 'Post approved and published.' : 'Post rejected.');
        await Promise.all([loadPendingKnowledge(), loadNotifications(), loadRecentKnowledge()]);
    } catch (error) {
        approveButton.disabled = rejectButton.disabled = false;
        setStatus(error.message, true);
    }
}

function configureNotifications() {
    if (currentUser?.role !== 'admin') return;
    const control = document.getElementById('notificationControl');
    const button = document.getElementById('notificationButton');
    const menu = document.getElementById('notificationMenu');
    control.classList.remove('hidden');
    button.addEventListener('click', async () => {
        const isOpen = !menu.classList.contains('hidden');
        menu.classList.toggle('hidden', isOpen);
        button.setAttribute('aria-expanded', String(!isOpen));
        if (!isOpen) {
            try { await loadNotifications(); }
            catch (error) { setStatus(error.message, true); }
        }
    });
    document.addEventListener('click', event => {
        if (!control.contains(event.target)) {
            menu.classList.add('hidden');
            button.setAttribute('aria-expanded', 'false');
        }
    });
    window.addEventListener('focus', () => loadNotifications().catch(() => {}));
    window.setInterval(() => loadNotifications().catch(() => {}), 30000);
    loadNotifications().catch(error => setStatus(error.message, true));
}
