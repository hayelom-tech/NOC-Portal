async function loadLibrary() {
    const params = new URLSearchParams();
    const domain = selectedKnowledgeDomain;
    const search = knowledgeArticleQuery.trim();
    if (domain) params.set('domain', domain);
    if (search) params.set('q', search);
    const knowledge = await api(`/api/v1/knowledge-hub${params.size ? `?${params}` : ''}`);

    const knowledgeList = document.getElementById('knowledgeList');
    knowledgeList.replaceChildren();
    if (!knowledge.length) {
        knowledgeList.append(Object.assign(document.createElement('p'), { className: 'text-sm text-slate-500', textContent: 'No matching knowledge articles.' }));
        return;
    }
    for (const item of knowledge) {
        const article = document.createElement('article');
        article.className = 'rounded-lg bg-slate-950 p-3';
        const title = document.createElement('h3');
        title.className = 'font-semibold';
        title.textContent = item.issue_title;
        const meta = document.createElement('p');
        meta.className = 'mt-1 text-xs text-slate-500';
        meta.textContent = domainLabels[item.domain];
        const summary = document.createElement('p');
        summary.className = 'mt-2 whitespace-pre-wrap text-sm text-slate-300';
        summary.textContent = item.symptoms;
        const details = document.createElement('details');
        details.className = 'mt-3 border-t border-slate-800 pt-2 text-sm';
        const summaryLine = node('summary', 'Troubleshooting details', 'cursor-pointer text-slate-400');
        details.append(summaryLine);
        for (const [label, text] of [
            ['Root cause', item.root_cause],
            ['Troubleshooting steps', item.troubleshooting_steps],
            ['Resolution', item.resolution]
        ]) {
            const section = document.createElement('div');
            section.className = 'mt-2';
            section.append(node('h4', label, 'font-semibold text-slate-300'));
            section.append(node('p', text, 'whitespace-pre-wrap text-slate-400'));
            details.append(section);
        }
        article.append(title, meta, summary, details);
        if (canEditContent()) {
            const edit = node('button', 'Edit article', 'mt-3 rounded bg-slate-800 px-3 py-1.5 text-xs');
            edit.type = 'button';
            edit.addEventListener('click', () => showEditor('knowledgeForm', item));
            article.append(edit);
        }
        knowledgeList.append(article);
    }
}

async function loadProcessDocuments() {
    const documents = await api('/api/v1/process-documents');
    const list = document.getElementById('processList');
    list.replaceChildren();
    if (!documents.length) {
        list.append(node('p', 'No NOC reference documents have been published yet.', 'rounded-lg border border-dashed border-slate-700 p-6 text-sm text-slate-400 sm:col-span-2 xl:col-span-3'));
        return;
    }
    for (const documentInfo of documents) {
        const card = node('article', '', 'flex min-w-0 flex-col rounded-xl border border-slate-800 bg-slate-950 p-4');
        const icon = node('div', '', 'mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-900/50 text-emerald-300');
        icon.innerHTML = '<i class="fa-solid fa-file-lines"></i>';
        const title = node('h3', documentInfo.title, 'font-semibold');
        const description = node('p', documentInfo.description || 'NOC reference document', 'mt-1 min-h-10 whitespace-pre-wrap text-sm text-slate-400');
        const fileName = node('p', documentInfo.file_name, 'mt-3 break-all text-xs text-slate-500');
        const actions = node('div', '', 'mt-4 flex gap-2 border-t border-slate-800 pt-3');
        const view = node('button', 'View', 'inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium hover:bg-slate-800');
        view.type = 'button';
        view.addEventListener('click', () => openProcessDocument(documentInfo, 'view'));
        view.innerHTML = '<i class="fa-regular fa-eye"></i>View';
        const download = node('button', 'Download', 'inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-600');
        download.type = 'button';
        download.addEventListener('click', () => openProcessDocument(documentInfo, 'download'));
        download.innerHTML = '<i class="fa-solid fa-download"></i>Download';
        actions.append(view, download);
        if (currentUser?.role === 'admin') {
            const remove = node('button', 'Delete', 'inline-flex items-center gap-2 rounded-lg border border-red-800 px-3 py-2 text-sm font-medium text-red-300 hover:bg-red-950/60');
            remove.type = 'button';
            remove.addEventListener('click', async () => {
                if (!window.confirm(`Delete “${documentInfo.title}”? This cannot be undone.`)) return;
                remove.disabled = true;
                try {
                    await api(`/api/v1/process-documents/${documentInfo.id}`, { method: 'DELETE' });
                    setStatus('NOC document deleted.');
                    await loadProcessDocuments();
                } catch (error) {
                    setStatus(error.message, true);
                    remove.disabled = false;
                }
            });
            remove.innerHTML = '<i class="fa-solid fa-trash"></i>Delete';
            actions.append(remove);
        }
        card.append(icon, title, description, fileName, actions);
        list.append(card);
    }
}

async function openProcessDocument(documentInfo, action) {
    try {
        const response = await fetch(`/api/v1/process-documents/${documentInfo.id}/${action}`, { credentials: 'same-origin' });
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || `Could not ${action} document (${response.status}).`);
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        if (action === 'download') {
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = documentInfo.file_name;
            document.body.append(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
            setStatus('Document download started.');
            return;
        }

        if (processDocumentPreviewUrl) URL.revokeObjectURL(processDocumentPreviewUrl);
        processDocumentPreviewUrl = objectUrl;
        const dialog = document.getElementById('processDocumentViewDialog');
        const frame = document.getElementById('processDocumentPreviewFrame');
        const fallback = document.getElementById('processDocumentPreviewFallback');
        document.getElementById('processDocumentViewTitle').textContent = documentInfo.title;
        const canPreview = ['application/pdf', 'text/plain', 'text/csv'].includes(blob.type);
        frame.classList.toggle('hidden', !canPreview);
        fallback.classList.toggle('hidden', canPreview);
        if (canPreview) frame.src = objectUrl;
        else document.getElementById('downloadFromPreview').onclick = () => openProcessDocument(documentInfo, 'download');
        dialog.showModal();
    } catch (error) {
        setStatus(error.message, true);
    }
}

function showEditor(formId, values = null) {
    const form = document.getElementById(formId);
    form.reset();
    for (const [name, value] of Object.entries(values || {})) {
        const field = form.elements.namedItem(name);
        if (field) field.value = value ?? '';
    }
    const expectedUpdatedAt = form.elements.namedItem('expected_updated_at');
    if (expectedUpdatedAt) expectedUpdatedAt.value = values?.expected_updated_at ?? values?.updated_at ?? '';
    form.classList.remove('hidden');
    form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function configureContentEditors() {
    const canEdit = canEditContent();
    const uploadButton = document.getElementById('uploadProcessDocumentButton');
    const uploadForm = document.getElementById('processDocumentUploadForm');
    uploadButton.classList.toggle('hidden', currentUser.role !== 'admin');
    uploadButton.addEventListener('click', () => {
        uploadForm.classList.toggle('hidden');
        if (!uploadForm.classList.contains('hidden')) {
            uploadStatus.classList.add('hidden');
            uploadForm.querySelector('[name="title"]').focus();
        }
    });
    const uploadStatus = document.getElementById('processDocumentUploadStatus');
    const uploadTitle = uploadForm.querySelector('[name="title"]');
    const uploadFile = uploadForm.querySelector('[name="file"]');
    uploadFile.addEventListener('change', () => {
        const selectedFile = uploadFile.files?.[0];
        if (selectedFile && !uploadTitle.value.trim()) {
            uploadTitle.value = selectedFile.name.replace(/\.[^.]+$/, '');
        }
        uploadStatus.classList.add('hidden');
    });
    document.getElementById('cancelProcessDocumentUpload').addEventListener('click', () => {
        uploadForm.reset();
        uploadForm.classList.add('hidden');
        uploadStatus.classList.add('hidden');
    });
    uploadForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!uploadFile.files?.length) {
            uploadStatus.textContent = 'Choose a document file before publishing.';
            uploadStatus.className = 'text-sm text-red-500';
            uploadFile.focus();
            return;
        }
        const submit = uploadForm.querySelector('[type="submit"]');
        submit.disabled = true;
        uploadStatus.textContent = 'Uploading document…';
        uploadStatus.className = 'text-sm text-sky-500';
        try {
            await api('/api/v1/process-documents', {
                method: 'POST',
                body: new FormData(uploadForm)
            });
            uploadForm.reset();
            uploadStatus.textContent = 'Document published successfully.';
            uploadStatus.className = 'text-sm text-emerald-500';
            setStatus('NOC document published.');
            await loadProcessDocuments();
        } catch (error) {
            uploadStatus.textContent = error.message;
            uploadStatus.className = 'text-sm text-red-500';
            setStatus(error.message, true);
        } finally {
            submit.disabled = false;
        }
    });
    document.querySelectorAll('.create-post-trigger').forEach(button => button.classList.toggle('hidden', !canEdit));
    document.querySelectorAll('.create-post-trigger').forEach(button => {
        button.addEventListener('click', () => {
            activateTab('knowledge');
            openKnowledgePostsView();
            showEditor('knowledgeForm');
        });
    });
    document.querySelectorAll('[data-cancel]').forEach(button => {
        button.addEventListener('click', () => {
            const form = document.getElementById(button.dataset.cancel);
            form.reset();
            form.classList.add('hidden');
        });
    });
    for (const [formId, endpoint, label] of [
        ['knowledgeForm', '/api/v1/knowledge-hub', 'Knowledge article']
    ]) {
        document.getElementById(formId).addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const values = Object.fromEntries(new FormData(form).entries());
            const id = values.id;
            delete values.id;
            if (!values.expected_updated_at) delete values.expected_updated_at;
            values.is_active = true;
            try {
                await api(id ? `${endpoint}/${id}` : endpoint, {
                    method: id ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(values)
                });
                form.reset();
                form.classList.add('hidden');
                const awaitingApproval = formId === 'knowledgeForm' && currentUser.role === 'operator';
                setStatus(awaitingApproval ? 'Post submitted for admin approval.' : `${label} saved.`);
                await loadLibrary();
                if (formId === 'knowledgeForm') await loadRecentKnowledge();
            } catch (error) {
                setStatus(error.message, true);
            }
        });
    }
}

const avatarColors = {
    default: 'bg-slate-700',
    green: 'bg-emerald-600',
    blue: 'bg-blue-600',
    purple: 'bg-purple-600',
    amber: 'bg-amber-600',
    rose: 'bg-rose-600',
    teal: 'bg-teal-600',
    indigo: 'bg-indigo-600'
};
