async function initPortal() {
    configureTabNavigation();
    const portalSearch = document.getElementById('portalSearch');
    let portalSearchTimeout;
    portalSearch.addEventListener('input', () => {
        clearTimeout(portalSearchTimeout);
        portalSearchTimeout = setTimeout(() => searchPortal(portalSearch.value), 250);
    });
    portalSearch.addEventListener('keydown', event => {
        if (event.key === 'Escape') hidePortalSearchResults();
    });
    document.addEventListener('click', event => {
        if (!document.getElementById('portalSearchWrap').contains(event.target)) hidePortalSearchResults();
    });
    document.querySelectorAll('[data-close-password]').forEach(button => {
        button.addEventListener('click', () => document.getElementById('passwordDialog').close());
    });
    const documentViewDialog = document.getElementById('processDocumentViewDialog');
    document.getElementById('closeProcessDocumentView').addEventListener('click', () => documentViewDialog.close());
    documentViewDialog.addEventListener('close', () => {
        document.getElementById('processDocumentPreviewFrame').src = 'about:blank';
        if (processDocumentPreviewUrl) URL.revokeObjectURL(processDocumentPreviewUrl);
        processDocumentPreviewUrl = null;
    });
    configurePasswordDialog();
    const themeToggle = document.getElementById('themeToggle');
    const syncThemeToggle = () => {
        const darkMode = document.documentElement.classList.contains('dark');
        themeToggle.setAttribute('aria-pressed', String(darkMode));
        themeToggle.setAttribute('aria-label', darkMode ? 'Disable night mode' : 'Enable night mode');
        themeToggle.title = darkMode ? 'Disable night mode' : 'Enable night mode';
        themeToggle.innerHTML = `<i class="fa-solid ${darkMode ? 'fa-moon' : 'fa-sun'}"></i>`;
    };
    syncThemeToggle();
    themeToggle.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
        syncThemeToggle();
    });
    currentUser = await api('/api/v1/auth/me');
    currentPermissions = await api('/api/v1/auth/permissions');
    document.getElementById('userLabel').textContent = currentUser.full_name;
    document.getElementById('userEmail').textContent = currentUser.email;
    configureUserMenu();
    configureNotifications();
    if (currentUser.role === 'admin') loadPendingKnowledge().catch(error => setStatus(error.message, true));
    configureContentEditors();
    shiftDate.value = localDateValue();

    document.getElementById('passwordForm').addEventListener('submit', async event => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
        delete payload.confirm_password;
        const formError = document.getElementById('passwordFormError');
        formError.classList.add('hidden');
        try {
            await api('/api/v1/auth/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            event.currentTarget.reset();
            document.getElementById('passwordDialog').close();
            setStatus('Password updated.');
        } catch (error) {
            formError.textContent = error.message;
            formError.classList.remove('hidden');
            setStatus(error.message, true);
        }
    });

    document.getElementById('backToKnowledgeDashboard').addEventListener('click', openKnowledgeDashboardView);
    document.getElementById('addFieldTeamButton').addEventListener('click', () => addFieldTeamRow());

    shiftSelect.addEventListener('change', async () => {
        try {
            const shift = (await api(`/api/v1/shifts?date=${encodeURIComponent(shiftDate.value)}`)).find(item => String(item.id) === shiftSelect.value);
            if (!shift) return;
            selectedShift = shift;
            setStatus(shiftSummary(shift));
            await loadSelectedShift();
            await loadHomeDomainShiftCards();
                } catch (error) {
            setStatus(error.message, true);
        }
    });

    shiftDate.addEventListener('change', () => loadShifts().catch(error => setStatus(error.message, true)));
    document.querySelectorAll('[name="challengeChoice"]').forEach(radio => {
        radio.addEventListener('change', () => {
            document.getElementById('challenges').checked = document.getElementById('challengeYes').checked;
            updateChallengeDetails();
        });
    });
    await loadShifts(true);
    await loadLibrary();
    await Promise.all([loadL2Roster(), loadRecentKnowledge()]);
}

initPortal().catch(error => setStatus(error.message, true));
