function renderUserAvatar() {
    const avatar = document.getElementById('userAvatar');
    avatar.textContent = currentUser.full_name.trim().charAt(0).toUpperCase() || '?';
    avatar.className = `flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white ${avatarColors[currentUser.avatar_key] || avatarColors.default}`;
}

function configureUserMenu() {
    const menu = document.getElementById('userMenu');
    const menuButton = document.getElementById('userMenuButton');
    const closeMenu = () => {
        menu.classList.add('hidden');
        menuButton.setAttribute('aria-expanded', 'false');
    };
    const openMenu = () => {
        menu.classList.remove('hidden');
        menuButton.setAttribute('aria-expanded', 'true');
    };

    document.getElementById('menuFullName').textContent = currentUser.full_name;
    document.getElementById('menuRole').textContent = currentUser.role === 'guest' ? 'User' : currentUser.role;
    renderUserAvatar();

    menuButton.addEventListener('click', () => {
        if (menu.classList.contains('hidden')) openMenu();
        else closeMenu();
    });
    document.addEventListener('click', event => {
        if (!menu.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeMenu();
    });

    const adminMenu = document.getElementById('adminMenuItems');
    adminMenu.classList.toggle('hidden', !(canUploadRoster() || canManageUsers() || canViewAudit()));
    adminMenu.querySelector('[data-menu-action="add-user"]').classList.toggle('hidden', !canManageUsers());
    document.getElementById('manageUsersLink').classList.toggle('hidden', !canManageUsers());
    document.getElementById('uploadRosterLink').classList.toggle('hidden', !canUploadRoster());

    const picker = document.getElementById('avatarPicker');
    for (const [key, colorClass] of Object.entries(avatarColors)) {
        const option = document.createElement('button');
        option.type = 'button';
        option.title = `${key} profile color`;
        option.setAttribute('aria-label', `${key} profile color`);
        option.setAttribute('aria-pressed', String(currentUser.avatar_key === key));
        option.className = `h-7 w-7 rounded-full border-2 ${colorClass} ${currentUser.avatar_key === key ? 'border-white' : 'border-transparent'}`;
        option.addEventListener('click', async () => {
            try {
                currentUser = await api('/api/v1/auth/me/avatar', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ avatar_key: key })
                });
                renderUserAvatar();
                picker.querySelectorAll('button').forEach(button => {
                    const selected = button === option;
                    button.setAttribute('aria-pressed', String(selected));
                    button.classList.toggle('border-white', selected);
                    button.classList.toggle('border-transparent', !selected);
                });
            } catch (error) {
                setStatus(error.message, true);
            }
        });
        picker.append(option);
    }

    menu.addEventListener('click', async event => {
        const action = event.target.closest('[data-menu-action]')?.dataset.menuAction;
        if (!action) return;
        closeMenu();
        if (action === 'password') {
            document.getElementById('passwordDialog').showModal();
            document.querySelector('#passwordForm [name="current_password"]').focus();
        } else if (action === 'add-user') {
            window.location.href = '/admin.html#userOnboarding';
        } else if (action === 'logout') {
            try {
                await api('/api/v1/auth/logout', { method: 'POST' });
            } catch (error) {
                setStatus(error.message, true);
            } finally {
                sessionStorage.clear();
                window.location.href = '/login.html';
            }
        }
    });
}

function configurePasswordDialog() {
    const form = document.getElementById('passwordForm');
    const dialog = document.getElementById('passwordDialog');
    const current = form.elements.current_password;
    const password = form.elements.new_password;
    const confirmation = form.elements.confirm_password;
    const submit = form.querySelector('.password-submit');
    const helper = document.getElementById('passwordHelp');
    const confirmError = document.getElementById('confirmPasswordError');
    const error = document.getElementById('passwordFormError');
    const checks = {
        length: value => value.length >= 12,
        upper: value => /[A-Z]/.test(value),
        lower: value => /[a-z]/.test(value),
        special: value => /[^A-Za-z0-9]/.test(value),
        number: value => /[0-9]/.test(value)
    };
    const validate = () => {
        const value = password.value;
        const results = Object.entries(checks).map(([name, check]) => {
            const met = check(value);
            const row = document.querySelector(`#passwordRules [data-rule="${name}"]`);
            row.dataset.met = String(met);
            row.dataset.touched = String(Boolean(value));
            return met;
        });
        const passwordValid = results.every(Boolean);
        password.dataset.state = value ? (passwordValid ? 'valid' : 'invalid') : '';
        helper.classList.toggle('hidden', !value || passwordValid);
        current.dataset.state = current.value ? 'valid' : '';
        const matches = Boolean(confirmation.value) && confirmation.value === value;
        confirmation.dataset.state = confirmation.value ? (matches ? 'valid' : 'invalid') : '';
        confirmError.classList.toggle('hidden', !confirmation.value || matches);
        submit.disabled = !(current.value && passwordValid && matches);
    };
    form.querySelectorAll('[data-password-toggle]').forEach(button => {
        button.addEventListener('click', () => {
            const input = form.elements[button.dataset.passwordToggle];
            const visible = input.type === 'password';
            input.type = visible ? 'text' : 'password';
            button.setAttribute('aria-label', `${visible ? 'Hide' : 'Show'} ${button.dataset.passwordToggle.replaceAll('_', ' ')}`);
            button.innerHTML = `<i class="fa-regular ${visible ? 'fa-eye' : 'fa-eye-slash'}"></i>`;
        });
    });
    [current, password, confirmation].forEach(input => input.addEventListener('input', () => {
        error.classList.add('hidden');
        validate();
    }));
    dialog.addEventListener('click', event => {
        if (event.target === dialog) dialog.close();
    });
    validate();
}
