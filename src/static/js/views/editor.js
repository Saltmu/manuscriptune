import { state, setSelectedNovelFile } from '../state.js';
import { parseLineNumber, showToast, showModal, closeModal, startEventStream } from '../utils.js';
import { loadDashboardData } from './dashboard.js';

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
        state.metadata = data.metadata || {};

        // Show/hide fallback warning banner
        const banner = document.getElementById('fallback-warning-banner');
        const bannerMsg = document.getElementById('fallback-warning-message');
        if (banner) {
            if (state.metadata && (state.metadata.fallback_mode || state.metadata.completeness === 'low')) {
                banner.style.display = 'flex';
                if (bannerMsg) {
                    const reason = state.metadata.reason || 'LLMによる指摘の統合に失敗したため、機械的なマージを使用しています。重複や矛盾が残っている可能性があります。';
                    bannerMsg.innerHTML = `<strong>⚠️ 品質低下の警告 (低品質):</strong> ${reason}`;
                }
            } else {
                banner.style.display = 'none';
            }
        }

        // Fetch sync status and show/hide sync warning banner
        const syncWarningBanner = document.getElementById('sync-warning-banner');
        const syncWarningMsg = document.getElementById('sync-warning-message');
        if (syncWarningBanner) {
            try {
                const syncResponse = await fetch('/api/sync/status');
                if (syncResponse.ok) {
                    const syncData = await syncResponse.json();
                    if (syncData.metadata && (syncData.metadata.fallback_mode || syncData.metadata.completeness === 'low')) {
                        syncWarningBanner.style.display = 'flex';
                        if (syncWarningMsg) {
                            const reason = syncData.metadata.reason || '設定資料（Google Drive）の同期に失敗しています。';
                            syncWarningMsg.innerHTML = `<strong>⚠️ 同期失敗の警告:</strong> ${reason}`;
                        }
                    } else {
                        syncWarningBanner.style.display = 'none';
                    }
                }
            } catch (syncErr) {
                console.error('Failed to check sync status:', syncErr);
            }
        }
        
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
        updateHeaderStatus();
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
            body: JSON.stringify({
                novel_name: state.selectedNovelFile,
                findings: state.findings,
                metadata: state.metadata
            })
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

export function switchEditorTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('#view-editor .tab-content').forEach(el => {
        el.style.display = 'none';
    });
    // Remove active class from all tab buttons
    document.querySelectorAll('#view-editor .tab-btn').forEach(el => {
        el.classList.remove('active');
    });

    // Show selected tab content
    const targetContent = document.getElementById(`tab-content-${tabName}`);
    if (targetContent) {
        if (tabName === 'logs') {
            targetContent.style.display = 'flex';
        } else {
            targetContent.style.display = 'block';
        }
    }
    // Add active class to selected tab button
    const targetBtn = document.getElementById(`tab-btn-${tabName}`);
    if (targetBtn) {
        targetBtn.classList.add('active');
    }
}

export function updateHeaderStatus() {
    const epDisplay = document.getElementById('episode-selection-display');
    const epInput = document.getElementById('write-episode');
    if (epDisplay && epInput) {
        if (epInput.value) {
            epDisplay.textContent = epInput.value;
            epDisplay.style.display = 'inline-block';
        } else {
            epDisplay.style.display = 'none';
        }
    }
}

export async function loadSourcesForWrite() {
    const overlay = document.getElementById('editor-loading-overlay');
    if (overlay) {
        overlay.classList.add('active');
    }
    try {
        // Load sources
        const response = await fetch('/api/sync/status');
        const data = await response.json();
        
        const selects = [
            'write-plot',
            'write-policy-global',
            'write-policy-chapter',
            'write-character'
        ];
        
        selects.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            
            // Keep the first default option
            el.innerHTML = '<option value="">(デフォルト/自動解決)</option>';
            
            data.sources.forEach(src => {
                const opt = document.createElement('option');
                opt.value = src.name;
                opt.textContent = src.name;
                el.appendChild(opt);
            });
        });

        // Load models
        const modelRes = await fetch('/api/models');
        const modelData = await modelRes.json();
        const modelSelects = [
            document.getElementById('write-model'),
            document.getElementById('review-model')
        ];
        modelSelects.forEach(modelSelect => {
            if (modelSelect && modelData.models) {
                modelSelect.innerHTML = '';
                modelData.models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    // Select Flash High as default
                    if (m.includes('High') || m.includes('Flash (High)')) {
                        opt.selected = true;
                    }
                    modelSelect.appendChild(opt);
                });
            }
        });

        // Restore values from localStorage and attach event listeners to save changes
        const fields = [
            'write-episode',
            'write-title',
            'write-model',
            'write-plot',
            'write-policy-global',
            'write-policy-chapter',
            'write-character',
            'review-model'
        ];

        fields.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;

            // Restore from localStorage
            const savedVal = localStorage.getItem(id);
            if (savedVal !== null) {
                el.value = savedVal;
            }

            // Bind change listener for saving
            if (!el.dataset.listenerRegistered) {
                el.dataset.listenerRegistered = 'true';
                const saveHandler = () => {
                    localStorage.setItem(id, el.value);
                    if (id === 'write-episode') {
                        updateHeaderStatus();
                    }
                };
                el.addEventListener('change', saveHandler);
                if (el.tagName === 'INPUT') {
                    el.addEventListener('input', saveHandler);
                }
            }
        });

        // Restore checkbox states from localStorage
        const cbFields = [
            'write-step-by-step',
            'write-self-check',
            'write-neighbor-plots'
        ];
        cbFields.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;

            const savedVal = localStorage.getItem(id);
            if (savedVal !== null) {
                el.checked = savedVal === 'true';
            }

            if (!el.dataset.listenerRegistered) {
                el.dataset.listenerRegistered = 'true';
                el.addEventListener('change', () => {
                    localStorage.setItem(id, el.checked);
                });
            }
        });

        updateHeaderStatus();

    } catch (err) {
        console.error('Failed to load sources for write:', err);
    } finally {
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
}

export function runAiWriting() {
    const epInput = document.getElementById('write-episode').value.trim();
    if (!epInput) {
        alert('執筆する話を入力してください (例: 第1話)');
        return;
    }

    const titleVal = document.getElementById('write-title').value.trim();
    const modelVal = document.getElementById('write-model').value;
    const plotVal = document.getElementById('write-plot').value;
    const policyGlobalVal = document.getElementById('write-policy-global').value;
    const policyChapterVal = document.getElementById('write-policy-chapter').value;
    const characterVal = document.getElementById('write-character').value;
    const stepByStepVal = document.getElementById('write-step-by-step').checked;
    const selfCheckVal = document.getElementById('write-self-check').checked;
    const includeNeighborPlotsVal = document.getElementById('write-neighbor-plots').checked;

    switchEditorTab('logs');

    const btn = document.getElementById('btn-run-write');
    if (btn) btn.disabled = true;

    const statusBadge = document.getElementById('editor-status-badge');
    if (statusBadge) {
        statusBadge.textContent = '✍️ AI執筆中...';
        statusBadge.style.backgroundColor = 'rgba(251, 191, 36, 0.15)'; // amber
        statusBadge.style.color = '#fbbf24';
        statusBadge.style.display = 'inline-block';
    }

    let url = `/api/stream/write?episode=${encodeURIComponent(epInput)}`;
    if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
    if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
    if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
    if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
    if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
    if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;
    if (stepByStepVal) url += `&step_by_step=true`;
    if (selfCheckVal) url += `&self_check=true`;
    if (includeNeighborPlotsVal) url += `&include_neighbor_plots=true`;

    startEventStream(url, 'editor-console-log', 'editor-console-status', (success) => {
        if (btn) btn.disabled = false;
        if (success) {
            if (statusBadge) {
                statusBadge.textContent = 'READY';
                statusBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.15)'; // green
                statusBadge.style.color = '#34d399';
            }
            showToast('AI執筆が完了しました');
            loadDashboardData();

            const logContent = document.getElementById('editor-console-log').textContent;
            const match = logContent.match(/Success! Novel saved to novels\/([^\s\r\n]+)/);
            if (match) {
                const filename = match[1];
                setSelectedNovelFile(filename);
                window.location.hash = `#/editor/${encodeURIComponent(filename)}`;
                setTimeout(() => {
                    if (confirm(`AI執筆が完了し、新規ファイル「${filename}」がロードされました。すぐに本文レビュー（校閲）を実行しますか？`)) {
                        runReviewPipeline();
                    } else {
                        switchEditorTab('settings');
                    }
                }, 300);
            } else {
                loadEditorData();
                switchEditorTab('settings');
            }
        } else {
            if (statusBadge) {
                statusBadge.textContent = 'FAILED';
                statusBadge.style.backgroundColor = 'rgba(239, 68, 68, 0.15)'; // red
                statusBadge.style.color = '#f87171';
            }
            showToast('執筆中にエラーが発生しました');
        }
    });
}

export async function copyWritingPrompt() {
    const epInput = document.getElementById('write-episode').value.trim();
    if (!epInput) {
        alert('執筆する話を入力してください (例: 第1話)');
        return;
    }

    const titleVal = document.getElementById('write-title').value.trim();
    const modelVal = document.getElementById('write-model').value;
    const plotVal = document.getElementById('write-plot').value;
    const policyGlobalVal = document.getElementById('write-policy-global').value;
    const policyChapterVal = document.getElementById('write-policy-chapter').value;
    const characterVal = document.getElementById('write-character').value;
    const includeNeighborPlotsVal = document.getElementById('write-neighbor-plots').checked;

    const btn = document.getElementById('btn-copy-prompt');
    const writeBtn = document.getElementById('btn-run-write');
    if (btn) btn.disabled = true;
    if (writeBtn) writeBtn.disabled = true;

    // Show loading overlay
    const overlay = document.getElementById('editor-loading-overlay');
    const loadingText = overlay ? overlay.querySelector('.view-loading-text') : null;
    const originalText = loadingText ? loadingText.textContent : '';
    if (loadingText) loadingText.textContent = 'プロンプト生成中...';
    if (overlay) overlay.classList.add('active');

    try {
        let url = `/api/write/prompt?episode=${encodeURIComponent(epInput)}`;
        if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
        if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
        if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
        if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
        if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
        if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;
        if (includeNeighborPlotsVal) url += `&include_neighbor_plots=true`;

        const response = await fetch(url);
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'プロンプト生成に失敗しました');
        }

        const data = await response.json();
        await navigator.clipboard.writeText(data.prompt);
        showToast('プロンプトをクリップボードにコピーしました');
    } catch (err) {
        console.error('Failed to copy prompt:', err);
        showToast(`エラー: ${err.message}`);
    } finally {
        if (btn) btn.disabled = false;
        if (writeBtn) writeBtn.disabled = false;
        if (loadingText) loadingText.textContent = originalText;
        if (overlay) overlay.classList.remove('active');
    }
}

export function runReviewPipeline() {
    const fileName = state.selectedNovelFile;
    if (!fileName) {
        alert('校閲対象の小説ファイルが選択されていません。');
        return;
    }

    switchEditorTab('logs');

    const btn = document.getElementById('btn-run-review');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '🔍 レビュー実行中...';
    }

    const statusBadge = document.getElementById('editor-status-badge');
    if (statusBadge) {
        statusBadge.textContent = '🔍 本文校閲中...';
        statusBadge.style.backgroundColor = 'rgba(251, 191, 36, 0.15)'; // amber
        statusBadge.style.color = '#fbbf24';
        statusBadge.style.display = 'inline-block';
    }

    const modelVal = document.getElementById('review-model').value;
    let url = `/api/stream/review?file=${encodeURIComponent(fileName)}`;
    if (modelVal) {
        url += `&model=${encodeURIComponent(modelVal)}`;
    }
    startEventStream(url, 'editor-console-log', 'editor-console-status', (success) => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '🔍 本文レビューを実行';
        }
        if (success) {
            if (statusBadge) {
                statusBadge.textContent = 'READY';
                statusBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.15)'; // green
                statusBadge.style.color = '#34d399';
            }
            showToast('レビューパイプラインが正常に完了しました');
            loadDashboardData();
            loadEditorData();
            switchEditorTab('findings');
        } else {
            if (statusBadge) {
                statusBadge.textContent = 'FAILED';
                statusBadge.style.backgroundColor = 'rgba(239, 68, 68, 0.15)'; // red
                statusBadge.style.color = '#f87171';
            }
            showToast('レビュー中にエラーが発生しました');
        }
    });
}
