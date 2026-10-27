const shiftDate = document.getElementById('shiftDate');
const shiftSelect = document.getElementById('shiftSelect');
const statusText = document.getElementById('status');
const shiftLabels = { morning: 'Morning', afternoon: 'Afternoon', night: 'Night' };
const shiftOrder = { morning: 0, afternoon: 1, night: 2 };
const regionNames = ['Afar', 'East 1', 'East 2', 'North', 'North East', 'North West', 'West'];
const domainLabels = { tx: 'TX', ran: 'RAN', power: 'Power', core: 'Core' };
let selectedShift = null;
let selectedShiftRoster = [];
let currentUser = null;
let currentPermissions = {};
let toastTimer;
let portalSearchRequestId = 0;
let homeRosterRequestId = 0;
let knowledgeArticleQuery = '';
let selectedKnowledgeDomain = '';
let processDocumentPreviewUrl = null;

function showToast(message, kind = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'pointer-events-none fixed right-6 top-6 z-[100] rounded-xl border px-4 py-3 text-sm shadow-2xl ' +
        (kind === 'error'
            ? 'border-red-700 bg-red-900/90 text-red-100'
            : 'border-emerald-700 bg-emerald-900/90 text-emerald-100');
    toast.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add('hidden'), 3500);
}

function permissionGranted(name) {
    return ['yes', 'limited'].includes(currentPermissions?.[name]);
}

function canSubmitHandover() {
    return permissionGranted('submit_handovers');
}

function canEditContent() {
    return permissionGranted('edit_process_articles');
}

function canUploadRoster() {
    return currentUser?.role === 'admin';
}

function canManageUsers() {
    return permissionGranted('manage_users');
}

function canViewAudit() {
    return permissionGranted('view_audit_history');
}

function node(tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text ?? '';
    if (className) element.className = className;
    return element;
}

function setStatus(message, isError = false) {
    statusText.textContent = message;
    statusText.className = `pb-2 text-sm ${isError ? 'text-red-400' : 'text-slate-400'}`;
    if (message) showToast(message, isError ? 'error' : 'success');
}

function activateTab(tabName) {
    const sectionTitles = {
        home: 'Home',
        handover: 'Shift Handover',
        l2: 'L2 Support',
        process: 'NOC Process',
        knowledge: 'Knowledge Hub'
    };
    document.getElementById('portalSectionTitle').textContent = sectionTitles[tabName] || 'Home';
    for (const button of document.querySelectorAll('[data-tab]')) {
        const active = button.dataset.tab === tabName;
        button.setAttribute('aria-selected', String(active));
        button.tabIndex = active ? 0 : -1;
        button.classList.toggle('bg-emerald-600', active);
        button.classList.toggle('text-white', active);
        button.classList.toggle('font-bold', active);
        button.classList.toggle('shadow-md', active);
        button.classList.toggle('text-slate-400', !active);
        button.classList.toggle('font-medium', !active);
    }
    for (const panel of document.querySelectorAll('[data-tab-panel]')) {
        panel.hidden = panel.dataset.tabPanel !== tabName;
    }
    const knowledgeActive = tabName === 'knowledge';
    document.getElementById('portalSearchWrap').classList.toggle('hidden', !knowledgeActive);
    document.getElementById('portalHeader').classList.toggle('knowledge-toolbar', knowledgeActive);
    if (!knowledgeActive) hidePortalSearchResults();
    if (knowledgeActive && currentUser?.role === 'admin') {
        loadPendingKnowledge().catch(error => setStatus(error.message, true));
    }
    if (tabName === 'process') {
        loadProcessDocuments().catch(error => setStatus(error.message, true));
    }
    const domainNav = document.getElementById('knowledgeDomainNav');
    domainNav.classList.toggle('is-expanded', knowledgeActive);
    domainNav.setAttribute('aria-hidden', String(!knowledgeActive));
    document.getElementById('knowledgeTab').setAttribute('aria-expanded', String(knowledgeActive));
    document.getElementById('knowledgeChevron').classList.toggle('rotate-180', knowledgeActive);
}

function configureTabNavigation() {
    const buttons = [...document.querySelectorAll('[data-tab]')];
    const tabNames = new Set(buttons.map(button => button.dataset.tab));
    const activateHashTab = () => {
        const tabName = window.location.hash.slice(1);
        activateTab(tabNames.has(tabName) ? tabName : 'home');
    };

    window.addEventListener('hashchange', activateHashTab);
    activateHashTab();
    for (const [index, button] of buttons.entries()) {
        button.addEventListener('click', () => {
            const domainNav = document.getElementById('knowledgeDomainNav');
            const isOpenKnowledgeTab = button.dataset.tab === 'knowledge'
                && button.getAttribute('aria-selected') === 'true'
                && domainNav.classList.contains('is-expanded');
            if (isOpenKnowledgeTab) {
                domainNav.classList.remove('is-expanded');
                domainNav.setAttribute('aria-hidden', 'true');
                button.setAttribute('aria-expanded', 'false');
                document.getElementById('knowledgeChevron').classList.remove('rotate-180');
                openKnowledgeDashboardView();
                return;
            }
            window.location.hash = button.dataset.tab;
            activateTab(button.dataset.tab);
            if (button.dataset.tab === 'knowledge') openKnowledgeDashboardView();
        });
        button.addEventListener('keydown', event => {
            let nextIndex;
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                nextIndex = (index + 1) % buttons.length;
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                nextIndex = (index - 1 + buttons.length) % buttons.length;
            } else if (event.key === 'Home') {
                nextIndex = 0;
            } else if (event.key === 'End') {
                nextIndex = buttons.length - 1;
            } else {
                return;
            }
            event.preventDefault();
            buttons[nextIndex].focus();
            window.location.hash = buttons[nextIndex].dataset.tab;
            activateTab(buttons[nextIndex].dataset.tab);
        });
    }
    document.querySelectorAll('[data-knowledge-domain]').forEach(button => {
        button.addEventListener('click', () => openKnowledgeDomain(button.dataset.knowledgeDomain));
    });
    document.querySelectorAll('[data-recent-domain]').forEach(button => {
        button.addEventListener('click', () => openKnowledgeDomain(button.dataset.recentDomain));
    });
    document.querySelector('[data-view-all-knowledge]').addEventListener('click', () => {
        selectedKnowledgeDomain = '';
        knowledgeArticleQuery = '';
        updateKnowledgePostsHeading('');
        document.getElementById('knowledgeForm').classList.add('hidden');
        activateTab('knowledge');
        openKnowledgePostsView();
        loadLibrary().catch(error => setStatus(error.message, true));
    });
}

function errorMessage(detail, fallback) {
    if (Array.isArray(detail)) return detail.map(item => item.msg || String(item)).join('; ') || fallback;
    return detail || fallback;
}

async function api(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 401) {
        sessionStorage.clear();
        window.location.replace('/login.html');
        throw new Error('Your session has expired. Sign in again.');
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(body.detail, `Request failed (${response.status})`));
    return body;
}

function hidePortalSearchResults() {
    document.getElementById('portalSearchResults').classList.add('hidden');
}

function showPortalSearchResults(results, query) {
    const panel = document.getElementById('portalSearchResults');
    panel.replaceChildren();
    if (!results.length) {
        panel.append(node('p', `No results found for “${query}”.`, 'px-3 py-4 text-sm text-slate-400'));
        panel.classList.remove('hidden');
        return;
    }
    for (const result of results.slice(0, 12)) {
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('role', 'option');
        button.className = 'block w-full rounded-lg px-3 py-2 text-left hover:bg-slate-800';
        button.append(
            node('span', result.title, 'block text-sm font-medium text-slate-100'),
            node('span', result.subtitle, 'mt-0.5 block text-xs text-slate-400')
        );
        button.addEventListener('click', () => {
            hidePortalSearchResults();
            document.getElementById('portalSearch').blur();
            result.open();
        });
        panel.append(button);
    }
    panel.classList.remove('hidden');
}

async function searchPortal(query) {
    const term = query.trim();
    const panel = document.getElementById('portalSearchResults');
    if (term.length < 2) {
        portalSearchRequestId += 1;
        hidePortalSearchResults();
        return;
    }
    const requestId = ++portalSearchRequestId;
    panel.replaceChildren(node('p', 'Searching portal…', 'px-3 py-4 text-sm text-slate-400'));
    panel.classList.remove('hidden');
    try {
        const encoded = encodeURIComponent(term);
        const date = shiftDate.value || localDateValue();
        const [articles, processDocuments, frontRoster, l2Roster] = await Promise.all([
            api(`/api/v1/knowledge-hub?q=${encoded}&limit=50`),
            api('/api/v1/process-documents'),
            api(`/api/v1/roster?date=${encodeURIComponent(date)}`),
            api('/api/v1/l2-roster')
        ]);
        if (requestId !== portalSearchRequestId) return;
        const lowered = term.toLowerCase();
        const results = articles.map(article => ({
            title: article.issue_title,
            subtitle: `Knowledge article · ${domainLabels[article.domain] || article.domain}`,
            open: () => {
                activateTab('knowledge');
                selectedKnowledgeDomain = article.domain;
                knowledgeArticleQuery = term;
                updateKnowledgePostsHeading(article.domain);
                document.getElementById('knowledgeForm').classList.add('hidden');
                openKnowledgePostsView();
                loadLibrary().catch(error => setStatus(error.message, true));
            }
        }));
        for (const processDocument of processDocuments) {
            const searchable = [processDocument.title, processDocument.description, processDocument.file_name].join(' ').toLowerCase();
            if (!searchable.includes(lowered)) continue;
            results.push({
                title: processDocument.title,
                subtitle: `NOC reference · ${processDocument.file_name}`,
                open: () => activateTab('process')
            });
        }
        for (const member of frontRoster) {
            const searchable = [member.member_name, member.location, member.team].join(' ').toLowerCase();
            if (!searchable.includes(lowered)) continue;
            results.push({
                title: member.member_name,
                subtitle: `Front office roster · ${member.location || member.team || 'Roster member'}`,
                open: () => {
                    activateTab('home');
                    loadHomeDomainShiftCards().catch(error => setStatus(error.message, true));
                }
            });
        }
        for (const member of l2Roster) {
            const searchable = [member.engineer_name, member.department, member.phone, member.email].join(' ').toLowerCase();
            if (!searchable.includes(lowered)) continue;
            results.push({
                title: member.engineer_name,
                subtitle: `L2 roster · ${member.department}`,
                open: () => {
                    activateTab('l2');
                    loadL2Roster().catch(error => setStatus(error.message, true));
                }
            });
        }
        showPortalSearchResults(results, term);
    } catch (error) {
        if (requestId !== portalSearchRequestId) return;
        panel.replaceChildren(node('p', error.message, 'px-3 py-4 text-sm text-red-300'));
        panel.classList.remove('hidden');
    }
}
