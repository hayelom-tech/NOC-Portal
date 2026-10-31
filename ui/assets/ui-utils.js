// Shared UI utilities — dirty-check helpers, toasts, html2canvas wrapper.
// Loaded before domain modules (incident-ui.js, change-ui.js).

function createDirtyChecker(getValues) {
    let baseline = null;
    return {
        snapshot() { baseline = getValues().slice(); },
        isDirty() {
            if (!baseline) return false;
            const cur = getValues();
            return cur.some((v, i) => String(v) !== String(baseline[i]));
        }
    };
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    if (!toast) { alert(message); return; }
    toast.textContent = message;
    toast.className = toast.className.replace(/text-(red|emerald|slate)-\d+/g, '');
    toast.classList.add(type === 'error' ? 'text-red-300' : 'text-emerald-300');
    toast.classList.remove('hidden');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.add('hidden'), 3000);
}

function captureElement(elementId, filename) {
    const target = document.getElementById(elementId);
    if (!target || typeof html2canvas === 'undefined') {
        alert('Image export is unavailable.');
        return;
    }
    html2canvas(target, { scale: 2, backgroundColor: '#ffffff', useCORS: true })
        .then(canvas => {
            const link = document.createElement('a');
            link.download = filename;
            link.href = canvas.toDataURL('image/png');
            link.click();
        });
}
