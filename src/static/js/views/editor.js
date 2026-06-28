import { state } from '../state.js';
import { parseLineNumber, showToast, showModal, closeModal, startEventStream } from '../utils.js';

// Load active editor data
export async function loadEditorData() {
    try {
        if (!state.selectedNovelFile) {
            console.log('No active novel file selected.');
            return;
        }
        const response = await fetch(`/api/data?file=${encodeURIComponent(state.selectedNovelFile)}`);
        if (!response.ok) throw new Error('Data fetch failed');
        
        const data = await response.json();
        state.novelLines = data.novel_lines;
        state.findings = data.findings;
        
        const filenameDisplay = document.getElementById('filename-display');
        if (filenameDisplay) filenameDisplay.textContent = data.novel_filename;
        
        // Show/hide rollback button based on backup existence
        const rollbackBtn = document.getElementById('btn-rollback');
        if (rollbackBtn) {
            rollbackBtn.style.display = data.has_backup ? 'inline-block' : 'none';
        }

        // Render versioned history list
        const selectHistory = document.getElementById('select-history');
        const historyContainer = document.getElementById('history-restore-container');
        if (selectHistory && historyContainer) {
            if (data.backups && data.backups.length > 0) {
                selectHistory.innerHTML = '';
                const versions = data.backups.filter(b => b.startsWith('v'));
                if (versions.length > 0) {
                    versions.forEach(ver => {
                        const opt = document.createElement('option');
                        opt.value = ver;
                        opt.textContent = `バージョン ${ver.substring(1)}`;
                        selectHistory.appendChild(opt);
                    });
                    historyContainer.style.display = 'flex';
                } else {
                    historyContainer.style.display = 'none';
                }
            } else {
                historyContainer.style.display = 'none';
            }
        }
        
        // If in edit mode, ensure textarea has the latest content
        const textarea = document.getElementById('novel-editor-textarea');
        if (textarea && textarea.style.display !== 'none') {
            textarea.value = state.novelLines.join('\n');
        }
        
        renderNovel();
        renderFindings();
        updateStats();
    } catch (err) {
        console.error(err);
        alert('エディタデータの読み込みに失敗しました。');
    }
}

// Render novel text with inline findings
export function renderNovel() {
    const container = document.getElementById('novel-content');
    if (!container) return;
    container.innerHTML = '';

    const findingsByLine = {};
    state.findings.forEach(f => {
        const lineNo = parseLineNumber(f.location);
        if (lineNo) {
            if (!findingsByLine[lineNo]) findingsByLine[lineNo] = [];
            findingsByLine[lineNo].push(f);
        }
    });

    state.novelLines.forEach((line, index) => {
        const lineNo = index + 1;
        const wrapper = document.createElement('div');
        wrapper.className = 'novel-line-wrapper';
        wrapper.id = `novel-line-${lineNo}`;

        const numSpan = document.createElement('span');
        numSpan.className = 'novel-line-number';
        numSpan.textContent = lineNo;
        wrapper.appendChild(numSpan);

        const textSpan = document.createElement('span');
        textSpan.className = 'novel-line-text';
        textSpan.textContent = line || ' ';
        wrapper.appendChild(textSpan);

        const lineFindings = findingsByLine[lineNo];
        if (lineFindings && lineFindings.length > 0) {
            wrapper.classList.add('has-finding');
            const hasLogic = lineFindings.some(f => isLogicCategory(f.category));
            const hasStyle = lineFindings.some(f => !isLogicCategory(f.category));
            
            if (hasLogic && hasStyle) {
                wrapper.classList.add('finding-logic');
            } else if (hasLogic) {
                wrapper.classList.add('finding-logic');
            } else if (hasStyle) {
                wrapper.classList.add('finding-style');
            }

            wrapper.addEventListener('click', () => {
                highlightLine(lineNo);
                const cardId = `finding-card-${lineFindings[0].id}`;
                const cardEl = document.getElementById(cardId);
                if (cardEl) {
                    cardEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    highlightCard(lineFindings[0].id);
                }
            });
        }
        container.appendChild(wrapper);
    });
}

export function isLogicCategory(category) {
    const cat = String(category).toLowerCase();
    return cat.includes('ロジック') || cat.includes('設定') || cat.includes('矛盾') || cat.includes('伏線') || cat.includes('整合性') || cat.includes('logic');
}

export function highlightLine(lineNo) {
    if (state.activeHighlightLine) {
        const prev = document.getElementById(`novel-line-${state.activeHighlightLine}`);
        if (prev) prev.classList.remove('highlight');
    }
    const current = document.getElementById(`novel-line-${lineNo}`);
    if (current) {
        current.classList.add('highlight');
        state.activeHighlightLine = lineNo;
    }
}

// Highlight card in right panel
export function highlightCard(id) {
    document.querySelectorAll('.finding-card').forEach(c => c.classList.remove('active'));
    const current = document.getElementById(`finding-card-${id}`);
    if (current) {
        current.classList.add('active');
    }
}

export function renderFindings() {
    const container = document.getElementById('findings-list');
    if (!container) return;
    container.innerHTML = '';

    const filtered = state.findings.filter(f => {
        const isLogic = isLogicCategory(f.category);
        if (state.activeCategoryFilter === 'logic' && !isLogic) return false;
        if (state.activeCategoryFilter === 'style' && isLogic) return false;
        if (state.activeSeverityFilter !== 'all' && String(f.severity).toLowerCase() !== state.activeSeverityFilter) return false;
        return true;
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding-top: 40px; font-size: 0.9rem;">該当する指摘事項はありません</div>`;
        return;
    }

    filtered.forEach(f => {
        const card = document.createElement('div');
        const isLogic = isLogicCategory(f.category);
        card.className = `finding-card ${isLogic ? 'logic' : 'style'}`;
        card.id = `finding-card-${f.id}`;

        const lineNo = parseLineNumber(f.location);

        let statusBadgeHtml = '';
        let errorMsgHtml = '';
        if (f.apply_status === 'success' || f.apply_status === 'applied') {
            statusBadgeHtml = `<span class="badge badge-apply-success">反映済み (applied)</span>`;
        } else if (f.apply_status === 'failed') {
            statusBadgeHtml = `<span class="badge badge-apply-failed">失敗 (failed)</span>`;
            errorMsgHtml = `
                <div class="apply-error-msg">
                    <strong>反映失敗:</strong> ${f.apply_result || '原因不明のエラー'}
                </div>
            `;
        } else {
            statusBadgeHtml = `<span class="badge badge-apply-pending">未反映 (pending)</span>`;
        }

        card.innerHTML = `
            <div class="card-header">
                <div class="card-meta">
                    <span class="badge badge-id">${f.id}</span>
                    <span class="badge badge-category ${isLogic ? 'logic' : 'style'}">${f.category}</span>
                    <span class="badge badge-severity ${String(f.severity).toLowerCase()}">${f.severity}</span>
                    ${statusBadgeHtml}
                </div>
                <div class="toggle-container">
                    <span class="toggle-label">採用</span>
                    <label class="toggle-switch">
                        <input type="checkbox" ${f.accepted === 'y' ? 'checked' : ''} onchange="toggleAccept('${f.id}', this.checked)">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            <div class="card-location">場所: ${f.location}</div>
            <div class="card-field">
                <div class="field-label">分析</div>
                <div class="field-value analysis-text">${f.analysis}</div>
            </div>
            <div class="card-field">
                <div class="field-label">対象テキスト</div>
                <div class="field-value original-text">「${f.original}」</div>
            </div>
            <div class="card-field">
                <div class="field-label">修正提案</div>
                <div class="field-value suggestion-text">${f.suggestion}</div>
            </div>
            ${errorMsgHtml}
        `;

        card.addEventListener('click', (e) => {
            if (e.target.closest('.toggle-container') || e.target.closest('.toggle-switch')) return;
            highlightCard(f.id);
            if (lineNo) {
                const lineEl = document.getElementById(`novel-line-${lineNo}`);
                if (lineEl) {
                    lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    highlightLine(lineNo);
                }
            }
        });

        container.appendChild(card);
    });
}

export async function toggleAccept(id, isChecked) {
    const finding = state.findings.find(f => f.id === id);
    if (finding) {
        finding.accepted = isChecked ? 'y' : 'n';
        updateStats();
        await saveChanges();
    }
}

export function updateStats() {
    const accepted = state.findings.filter(f => f.accepted === 'y').length;
    const acceptedCountEl = document.getElementById('accepted-count');
    const totalCountEl = document.getElementById('total-count');
    if (acceptedCountEl) acceptedCountEl.textContent = accepted;
    if (totalCountEl) totalCountEl.textContent = state.findings.length;
}

export async function saveChanges() {
    try {
        if (!state.selectedNovelFile) return;
        await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ novel_name: state.selectedNovelFile, findings: state.findings })
        });
        showToast('自動保存しました');
    } catch (err) {
        console.error(err);
    }
}

export function filterCategory(cat, btn) {
    document.querySelectorAll('.filter-bar button').forEach(b => {
        if (b.onclick.toString().includes('filterCategory')) b.classList.remove('active');
    });
    btn.classList.add('active');
    state.activeCategoryFilter = cat;
    renderFindings();
}

export function filterSeverity(sev, btn) {
    document.querySelectorAll('.filter-bar button').forEach(b => {
        if (b.onclick.toString().includes('filterSeverity')) b.classList.remove('active');
    });
    btn.classList.add('active');
    state.activeSeverityFilter = sev;
    renderFindings();
}

export function confirmApply() { showModal('apply-modal'); }

export async function executeApply() {
    closeModal('apply-modal');
    showModal('apply-progress-modal');

    const closeBtn = document.getElementById('btn-close-apply-progress');
    if (closeBtn) closeBtn.disabled = true;

    if (!state.selectedNovelFile) {
        showToast('小説ファイルが選択されていません。');
        if (closeBtn) closeBtn.disabled = false;
        closeModal('apply-progress-modal');
        return;
    }

    startEventStream(`/api/stream/apply?file=${encodeURIComponent(state.selectedNovelFile)}`, 'apply-console-log', 'apply-console-status', (success) => {
        if (closeBtn) closeBtn.disabled = false;
        if (success) {
            showToast('反映処理が完了しました');
        } else {
            showToast('反映処理中にエラーが発生しました');
        }
    });
}

// ================= INLINE EDITOR & ROLLBACK LOGIC =================

export let isNovelEditMode = false;

export function toggleEditMode() {
    const novelContent = document.getElementById('novel-content');
    const textarea = document.getElementById('novel-editor-textarea');
    const btnToggle = document.getElementById('btn-toggle-edit');
    const btnSave = document.getElementById('btn-save-novel');
    const editBadge = document.getElementById('edit-mode-badge');

    if (!novelContent || !textarea) return;

    isNovelEditMode = !isNovelEditMode;

    if (isNovelEditMode) {
        // Switch to edit mode
        textarea.value = state.novelLines.join('\n');
        novelContent.style.display = 'none';
        textarea.style.display = 'block';
        if (btnToggle) {
            btnToggle.textContent = '❌ キャンセル';
            btnToggle.className = 'btn-secondary btn-sm';
        }
        if (btnSave) btnSave.style.display = 'inline-block';
        if (editBadge) editBadge.style.display = 'inline-block';
    } else {
        // Switch to preview mode
        novelContent.style.display = 'block';
        textarea.style.display = 'none';
        if (btnToggle) {
            btnToggle.textContent = '📝 直接編集';
            btnToggle.className = 'btn-secondary btn-sm';
        }
        if (btnSave) btnSave.style.display = 'none';
        if (editBadge) editBadge.style.display = 'none';
    }
}

export async function saveNovel() {
    const textarea = document.getElementById('novel-editor-textarea');
    const btnSave = document.getElementById('btn-save-novel');
    const btnToggle = document.getElementById('btn-toggle-edit');

    if (!textarea) return;

    // Control loader and block inputs
    if (btnSave) btnSave.disabled = true;
    if (btnToggle) btnToggle.disabled = true;
    textarea.disabled = true;

    try {
        if (!state.selectedNovelFile) {
            showToast('小説ファイルが選択されていません。');
            if (btnSave) btnSave.disabled = false;
            if (btnToggle) btnToggle.disabled = false;
            textarea.disabled = false;
            return;
        }
        const response = await fetch('/api/save_novel', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ novel_name: state.selectedNovelFile, content: textarea.value })
        });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            showToast('小説本文を保存しました');
            // Exit edit mode and reload
            isNovelEditMode = false;
            
            // Switch UI back
            const novelContent = document.getElementById('novel-content');
            const editBadge = document.getElementById('edit-mode-badge');
            if (novelContent) novelContent.style.display = 'block';
            textarea.style.display = 'none';
            if (btnToggle) {
                btnToggle.textContent = '📝 直接編集';
                btnToggle.className = 'btn-secondary btn-sm';
                btnToggle.disabled = false;
            }
            if (btnSave) {
                btnSave.style.display = 'none';
                btnSave.disabled = false;
            }
            if (editBadge) editBadge.style.display = 'none';
            textarea.disabled = false;

            await loadEditorData();
        } else {
            showToast('保存に失敗しました: ' + (data.detail || ''));
            if (btnSave) btnSave.disabled = false;
            if (btnToggle) btnToggle.disabled = false;
            textarea.disabled = false;
        }
    } catch (err) {
        console.error(err);
        showToast('保存中に通信エラーが発生しました');
        if (btnSave) btnSave.disabled = false;
        if (btnToggle) btnToggle.disabled = false;
        textarea.disabled = false;
    }
}

export function confirmRollback() {
    if (confirm('本当に反映前のバックアップ状態に戻しますか？\n（現在の小説本文と指摘の反映ステータスが復元されます）')) {
        executeRollback();
    }
}

export async function executeRollback() {
    const rollbackBtn = document.getElementById('btn-rollback');
    if (rollbackBtn) rollbackBtn.disabled = true;

    try {
        if (!state.selectedNovelFile) {
            showToast('小説ファイルが選択されていません。');
            if (rollbackBtn) rollbackBtn.disabled = false;
            return;
        }
        const response = await fetch(`/api/rollback?file=${encodeURIComponent(state.selectedNovelFile)}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            showToast('バックアップから元に戻しました');
            await loadEditorData();
        } else {
            showToast('元に戻す処理に失敗しました: ' + (data.detail || ''));
        }
    } catch (err) {
        console.error(err);
        showToast('通信エラーが発生しました');
    } finally {
        if (rollbackBtn) rollbackBtn.disabled = false;
    }
}

export function closeApplyProgressModal() {
    closeModal('apply-progress-modal');
    loadEditorData();
}

export function confirmRestoreHistory() {
    const selectHistory = document.getElementById('select-history');
    if (!selectHistory) return;
    const version = selectHistory.value;
    if (!version) return;
    if (confirm(`本当にバージョン ${version.substring(1)} の状態に復元しますか？\n（小説本文と指摘の反映ステータスがその時点のものに戻ります）`)) {
        executeRestoreHistory(version);
    }
}

export async function executeRestoreHistory(version) {
    const restoreBtn = document.getElementById('btn-restore-history');
    if (restoreBtn) restoreBtn.disabled = true;

    try {
        if (!state.selectedNovelFile) {
            showToast('小説ファイルが選択されていません。');
            if (restoreBtn) restoreBtn.disabled = false;
            return;
        }
        const response = await fetch(`/api/rollback?file=${encodeURIComponent(state.selectedNovelFile)}&version=${encodeURIComponent(version)}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            showToast(`バージョン ${version.substring(1)} に復元しました`);
            await loadEditorData();
        } else {
            showToast('復元処理に失敗しました: ' + (data.detail || ''));
        }
    } catch (err) {
        console.error(err);
        showToast('通信エラーが発生しました');
    } finally {
        if (restoreBtn) restoreBtn.disabled = false;
    }
}
