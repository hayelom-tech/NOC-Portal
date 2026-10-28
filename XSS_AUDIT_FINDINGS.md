# XSS Audit Findings

**Date:** Session 1, Phase 3
**Scope:** All UI files — `ui/assets/portal-*.js`, `ui/pages/*.html`
**Method:** Grep for `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `document.write`, `eval`, `new Function`, `setTimeout(string)`, `setAttribute` with template literals, `.src =`, `.href =` with user data. Then trace data flow for each hit.

## Summary

- **Total innerHTML calls found:** 10
- **Total setAttribute with template literals:** 3
- **Total .src/.href assignments with dynamic data:** 4
- **VULNERABLE (user data in DOM without escaping):** 0
- **SAFE (static strings, hardcoded values, or sanitized data):** 17

**Result: No XSS vulnerabilities found. No code changes required.**

## Detailed findings

### innerHTML calls

| # | File | Line | Code | Interpolated value | Source | Status |
|---|------|------|------|--------------------|--------|--------|
| 1 | portal-content.js | 64 | `icon.innerHTML = '<i class="fa-solid fa-file-lines"></i>'` | None (static) | Hardcoded | SAFE |
| 2 | portal-content.js | 72 | `view.innerHTML = '<i class="fa-regular fa-eye"></i>View'` | None (static) | Hardcoded | SAFE |
| 3 | portal-content.js | 76 | `download.innerHTML = '<i class="fa-solid fa-download"></i>Download'` | None (static) | Hardcoded | SAFE |
| 4 | portal-content.js | 93 | `remove.innerHTML = '<i class="fa-solid fa-trash"></i>Delete'` | None (static) | Hardcoded | SAFE |
| 5 | portal-init.js | 32 | `themeToggle.innerHTML = '<i class="fa-solid ${darkMode ? 'fa-moon' : 'fa-sun'}"></i>'` | Ternary of hardcoded strings | Hardcoded | SAFE |
| 6 | portal-overview.js | 130 | `icon.innerHTML = '<i class="fa-solid ${iconName}" aria-hidden="true"></i>'` | `iconName` from hardcoded domains array | Hardcoded | SAFE |
| 7 | portal-user.js | 132 | `button.innerHTML = '<i class="fa-regular ${visible ? 'fa-eye' : 'fa-eye-slash'}"></i>'` | Ternary of hardcoded strings | Hardcoded | SAFE |
| 8 | handover.html | 406 | `listContainer.innerHTML = ""` | Empty string | Static | SAFE |
| 9 | handover.html | 418 | `itemBtn.innerHTML = '...${explicitDateStr}...${explicitTimeStr}...'` | `explicitDateStr`/`explicitTimeStr` from `toLocaleDateString()`/`toLocaleTimeString()` of `new Date(log.timestamp)` | Locale-formatted (no script execution) | SAFE |
| 10 | login.html | 197 | `button.innerHTML = '<i class="fa-solid fa-circle-check"></i> <span>Authenticated — Redirecting…</span>'` | None (static) | Hardcoded | SAFE |

### setAttribute with template literals

| # | File | Line | Code | Interpolated value | Source | Status |
|---|------|------|------|--------------------|--------|--------|
| 1 | portal-overview.js | 236 | `container.setAttribute('aria-label', 'Open recent ${config.label} article')` | `config.label` from hardcoded domains object | Hardcoded | SAFE |
| 2 | portal-user.js | 45 | `option.setAttribute('aria-label', '${key} profile color')` | `key` from `Object.entries(avatarColors)` (hardcoded keys) | Hardcoded | SAFE |
| 3 | portal-user.js | 131 | `button.setAttribute('aria-label', '${visible ? 'Hide' : 'Show'} ${button.dataset.passwordToggle.replaceAll('_', ' ')}')` | `button.dataset.passwordToggle` from hardcoded HTML `data-password-toggle="current_password"` etc. | Hardcoded HTML | SAFE |

### .src / .href assignments with dynamic data

| # | File | Line | Code | Value source | Status |
|---|------|------|------|-------------|--------|
| 1 | portal-content.js | 112 | `link.href = objectUrl` | `URL.createObjectURL(blob)` from API response | SAFE (blob URL) |
| 2 | portal-content.js | 131 | `frame.src = objectUrl` | `URL.createObjectURL(blob)` from API response | SAFE (blob URL) |
| 3 | portal-overview.js | 161 | `phone.href = 'tel:' + member.phone.replace(/[^+\d]/g, '')` | `member.phone` from API, sanitized to digits/+ only | SAFE (sanitized) |
| 4 | portal-overview.js | 166 | `email.href = 'mailto:' + member.email` | `member.email` from API | SAFE (mailto: protocol) |

### Other DOM injection patterns checked

| Pattern | Found? |
|---------|--------|
| `document.write` | No |
| `eval()` | No |
| `new Function()` | No |
| `setTimeout(string)` | No |
| `insertAdjacentHTML` | No |
| `outerHTML` | No |
| Template literals in `.src`/`.href` with user data | No (only blob URLs and sanitized phone/email) |

### Additional notes

- **`window.confirm` with user data (portal-content.js:82):** `window.confirm('Delete "${documentInfo.title}"?...')` uses `documentInfo.title` in a dialog. `window.confirm` displays plain text (no HTML execution). SAFE, but `documentInfo.title` could contain quotes that break the template literal string. Not an XSS vector, but a minor robustness concern.
- **`node()` helper (portal-core.js:55):** Uses `element.textContent = text ?? ''`. All user-controlled data (names, titles, descriptions, notes) is rendered via `node()` with `textContent`. SAFE.
- **Backend `_inject_data` (pages.py:24-28):** JSON-encodes data and replaces `<` with `\u003c`. SAFE.

## Conclusion

**No XSS vulnerabilities found. No code changes required.**

All `innerHTML` calls use either static strings or hardcoded values. All user-controlled data is rendered via `textContent` (through the `node()` helper). The `setAttribute` calls use hardcoded or sanitized values. The `.src`/`.href` assignments use blob URLs or protocol-prefixed sanitized data.

The codebase is XSS-safe as-is. The `node()` helper pattern (using `textContent`) is the correct approach and is used consistently throughout.