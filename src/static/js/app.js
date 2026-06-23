let isRunningProcess = false;
let novelLines = [];
let findings = [];
let activeCategoryFilter = 'all';
let activeSeverityFilter = 'all';
let activeHighlightLine = null;

let selectedNovelFile = "";

// Switch Tabs/Views
function switchView(viewId) {
    if (isRunningProcess) {
        showToast('プロセス実行中は画面を切り替えられません。');
        return;
    }
    document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    
    document.getElementById(`view-${viewId}`).classList.add('active');
    
    // Highlight nav link
    const navLink = Array.from(document.querySelectorAll('.nav-item')).find(item => item.textContent.includes(
        viewId === 'dashboard' ? 'ダッシュボード' :
        viewId === 'sync' ? '設定資料同期' :
        viewId === 'write' ? 'AI小説執筆' :
        viewId === 'review' ? 'レビュー実行' : '校閲'
    ));
    if (navLink) navLink.classList.add('active');

    // Hook for loading dashboards
    if (viewId === 'dashboard') {
        loadDashboardData();
    }
}

// Parse line number from location
function parseLineNumber(locationStr) {
    if (!locationStr) return null;
    const match = String(locationStr).match(/(\d+)/);
    return match ? parseInt(match[0], 10) : null;
}

// Fetch Dashboard Data
async function loadDashboardData() {
    try {
        // Load novels
        const response = await fetch('/api/novels');
        const data = await response.json();
        
        const tableBody = document.querySelector('#novels-table tbody');
        tableBody.innerHTML = '';
        
        const reviewSelect = document.getElementById('review-file-select');
        reviewSelect.innerHTML = '';

        if (data.novels.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted)">小説が見つかりません。novels/ フォルダを確認してください。</td></tr>`;
        } else {
            data.novels.forEach(n => {
                const tr = document.createElement('tr');
                
                const badgeHtml = n.has_findings 
                    ? `<span class="badge badge-success">指摘あり</span>` 
                    : `<span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>`;
                
                const actionsHtml = n.has_findings
                    ? `<button class="btn-primary btn-sm btn-sm" onclick="selectAndEditNovel('${n.name}')">📝 校閲する</button>`
                    : `<button class="btn-secondary btn-sm" onclick="selectAndReviewNovel('${n.name}')">🔍 レビュー実行</button>`;

                tr.innerHTML = `
                    <td style="font-weight: 500;">${n.name}</td>
                    <td>${(n.size / 1024).toFixed(1)} KB</td>
                    <td style="color:var(--text-muted); font-size:0.8rem;">${n.last_modified}</td>
                    <td>${badgeHtml}</td>
                    <td>${actionsHtml}</td>
                `;
                tableBody.appendChild(tr);

                // Populate select in review view
                const opt = document.createElement('option');
                opt.value = n.name;
                opt.textContent = n.name;
                reviewSelect.appendChild(opt);
            });
        }

        // Load Sync Status
        const syncResponse = await fetch('/api/sync/status');
        const syncData = await syncResponse.json();
        const statusArea = document.getElementById('drive-sync-status-area');
        statusArea.innerHTML = '';

        if (syncData.sources.length === 0) {
            statusArea.innerHTML = '<li>同期された設定資料はありません。</li>';
        } else {
            syncData.sources.forEach(s => {
                const li = document.createElement('div');
                li.style.display = 'flex';
                li.style.justifyContent = 'space-between';
                li.innerHTML = `
                    <span>${s.name}</span>
                    <span style="font-size:0.8rem; color:var(--text-muted);">${s.last_updated}</span>
                `;
                statusArea.appendChild(li);
            });
        }

    } catch (err) {
        console.error(err);
    }
}

// Action: Select novel and switch to editor
async function selectAndEditNovel(novelName) {
    try {
        const res = await fetch('/api/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ novel_name: novelName })
        });
        const data = await res.json();
        if (data.status === 'success') {
            selectedNovelFile = novelName;
            // Load Editor Data
            await loadEditorData();
            switchView('editor');
        }
    } catch (err) {
        console.error(err);
        alert('ファイルの選択に失敗しました。');
    }
}

// Action: Select novel and switch to review view
function selectAndReviewNovel(novelName) {
    switchView('review');
    document.getElementById('review-file-select').value = novelName;
}

// Streaming Execution Log Helper using EventSource
function startEventStream(url, consoleId, statusId, onComplete = null) {
    const consoleEl = document.getElementById(consoleId);
    const statusEl = document.getElementById(statusId);
    
    consoleEl.textContent = '--- プロセスを開始します ---\n';
    statusEl.textContent = 'RUNNING';
    statusEl.style.color = '#fbbf24'; // Amber

    document.body.classList.add('process-running');
    isRunningProcess = true;

    const eventSource = new EventSource(url);

    eventSource.onmessage = function(event) {
        if (event.data.includes('[PROCESS_EXITED]')) {
            const code = event.data.split('code=')[1] || '0';
            consoleEl.textContent += `\n--- プロセスが終了しました (終了コード: ${code}) ---\n`;
            statusEl.textContent = code === '0' ? 'COMPLETED' : 'FAILED';
            statusEl.style.color = code === '0' ? '#34d399' : '#f87171';
            eventSource.close();
            
            document.body.classList.remove('process-running');
            isRunningProcess = false;

            if (onComplete) onComplete(code === '0');
            return;
        }
        consoleEl.textContent += event.data + '\n';
        consoleEl.scrollTop = consoleEl.scrollHeight; // Auto scroll
    };

    eventSource.onerror = function(err) {
        consoleEl.textContent += '\n[ERROR] 接続エラーまたはサーバーが切断されました。\n';
        statusEl.textContent = 'CONNECTION ERROR';
        statusEl.style.color = '#f87171';
        eventSource.close();
        
        document.body.classList.remove('process-running');
        isRunningProcess = false;

        if (onComplete) onComplete(false);
    };
}

// Trigger Google Drive Sync
function runDriveSync() {
    const btn = document.getElementById('btn-run-sync');
    btn.disabled = true;

    startEventStream('/api/stream/sync', 'sync-console-log', 'sync-console-status', (success) => {
        btn.disabled = false;
        if (success) {
            showToast('同期が正常に完了しました');
            loadDashboardData();
        } else {
            showToast('同期中にエラーが発生しました');
        }
    });
}

async function loadSourcesForWrite() {
    const overlay = document.getElementById('write-loading-overlay');
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
            'write-settings',
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
        const modelSelect = document.getElementById('write-model');
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

        // Restore values from localStorage and attach event listeners to save changes
        const fields = [
            'write-episode',
            'write-title',
            'write-model',
            'write-plot',
            'write-policy-global',
            'write-policy-chapter',
            'write-settings',
            'write-character'
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
                };
                el.addEventListener('change', saveHandler);
                if (el.tagName === 'INPUT') {
                    el.addEventListener('input', saveHandler);
                }
            }
        });

    } catch (err) {
        console.error('Failed to load sources for write:', err);
    } finally {
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
}


// Trigger AI Novel Writing
function runAiWriting() {
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
    const settingsVal = document.getElementById('write-settings').value;
    const characterVal = document.getElementById('write-character').value;

    const btn = document.getElementById('btn-run-write');
    btn.disabled = true;

    let url = `/api/stream/write?episode=${encodeURIComponent(epInput)}`;
    if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
    if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
    if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
    if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
    if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
    if (settingsVal) url += `&settings=${encodeURIComponent(settingsVal)}`;
    if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;

    startEventStream(url, 'write-console-log', 'write-console-status', (success) => {
        btn.disabled = false;
        if (success) {
            showToast('AI執筆が完了しました');
            loadDashboardData();
        } else {
            showToast('執筆中にエラーが発生しました');
        }
    });
}

// Trigger Review Pipeline
let lastReviewedFile = "";
function runReviewPipeline() {
    const selectEl = document.getElementById('review-file-select');
    const fileName = selectEl.value;
    if (!fileName) {
        alert('ファイルを選択してください');
        return;
    }

    const btn = document.getElementById('btn-run-review');
    const actionsArea = document.getElementById('review-complete-actions');
    btn.disabled = true;
    actionsArea.style.display = 'none';

    lastReviewedFile = fileName;

    const url = `/api/stream/review?file=${encodeURIComponent(fileName)}`;
    startEventStream(url, 'review-console-log', 'review-console-status', (success) => {
        btn.disabled = false;
        if (success) {
            showToast('レビューパイプラインが正常に完了しました');
            actionsArea.style.display = 'block';
            loadDashboardData();
        } else {
            showToast('レビュー中にエラーが発生しました');
        }
    });
}

// Move to editor from review completed screen
function goToEditorFromReview() {
    if (lastReviewedFile) {
        selectAndEditNovel(lastReviewedFile);
    }
}

// ================= EDITOR VIEW LOGIC (Merged) =================

// Load active editor data
async function loadEditorData() {
    try {
        const response = await fetch('/api/data');
        if (!response.ok) throw new Error('Data fetch failed');
        
        const data = await response.json();
        novelLines = data.novel_lines;
        findings = data.findings;
        
        document.getElementById('filename-display').textContent = data.novel_filename;
        
        renderNovel();
        renderFindings();
        updateStats();
    } catch (err) {
        console.error(err);
        alert('エディタデータの読み込みに失敗しました。');
    }
}

// Render novel text with inline findings
function renderNovel() {
    const container = document.getElementById('novel-content');
    container.innerHTML = '';

    const findingsByLine = {};
    findings.forEach(f => {
        const lineNo = parseLineNumber(f.location);
        if (lineNo) {
            if (!findingsByLine[lineNo]) findingsByLine[lineNo] = [];
            findingsByLine[lineNo].push(f);
        }
    });

    novelLines.forEach((line, index) => {
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

function isLogicCategory(category) {
    const cat = String(category).toLowerCase();
    return cat.includes('ロジック') || cat.includes('設定') || cat.includes('矛盾') || cat.includes('伏線') || cat.includes('整合性') || cat.includes('logic');
}

function highlightLine(lineNo) {
    if (activeHighlightLine) {
        const prev = document.getElementById(`novel-line-${activeHighlightLine}`);
        if (prev) prev.classList.remove('highlight');
    }
    const current = document.getElementById(`novel-line-${lineNo}`);
    if (current) {
        current.classList.add('highlight');
        activeHighlightLine = lineNo;
    }
}

// Highlight card in right panel
function highlightCard(id) {
    document.querySelectorAll('.finding-card').forEach(c => c.classList.remove('active'));
    const current = document.getElementById(`finding-card-${id}`);
    if (current) {
        current.classList.add('active');
    }
}

function renderFindings() {
    const container = document.getElementById('findings-list');
    container.innerHTML = '';

    const filtered = findings.filter(f => {
        const isLogic = isLogicCategory(f.category);
        if (activeCategoryFilter === 'logic' && !isLogic) return false;
        if (activeCategoryFilter === 'style' && isLogic) return false;
        if (activeSeverityFilter !== 'all' && String(f.severity).toLowerCase() !== activeSeverityFilter) return false;
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

        card.innerHTML = `
            <div class="card-header">
                <div class="card-meta">
                    <span class="badge badge-id">${f.id}</span>
                    <span class="badge badge-category ${isLogic ? 'logic' : 'style'}">${f.category}</span>
                    <span class="badge badge-severity ${String(f.severity).toLowerCase()}">${f.severity}</span>
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

async function toggleAccept(id, isChecked) {
    const finding = findings.find(f => f.id === id);
    if (finding) {
        finding.accepted = isChecked ? 'y' : 'n';
        updateStats();
        await saveChanges();
    }
}

function updateStats() {
    const accepted = findings.filter(f => f.accepted === 'y').length;
    document.getElementById('accepted-count').textContent = accepted;
    document.getElementById('total-count').textContent = findings.length;
}

async function saveChanges() {
    try {
        await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ findings: findings })
        });
        showToast('自動保存しました');
    } catch (err) {
        console.error(err);
    }
}

function filterCategory(cat, btn) {
    document.querySelectorAll('.filter-bar button').forEach(b => {
        if (b.onclick.toString().includes('filterCategory')) b.classList.remove('active');
    });
    btn.classList.add('active');
    activeCategoryFilter = cat;
    renderFindings();
}

function filterSeverity(sev, btn) {
    document.querySelectorAll('.filter-bar button').forEach(b => {
        if (b.onclick.toString().includes('filterSeverity')) b.classList.remove('active');
    });
    btn.classList.add('active');
    activeSeverityFilter = sev;
    renderFindings();
}

// Modals & Shutdowns
function showModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function confirmApply() { showModal('apply-modal'); }
function confirmGlobalShutdown() { showModal('shutdown-global-modal'); }

async function executeApply() {
    closeModal('apply-modal');
    showToast('変更を小説に反映中...', 10000);
    try {
        const response = await fetch('/api/apply', { method: 'POST' });
        if (!response.ok) throw new Error('Apply failed');
        showToast('反映が完了しました。シャットダウンします。');
        setTimeout(() => {
            window.close();
            document.body.innerHTML = `<div style="display:flex; justify-content:center; align-items:center; height:100vh; font-size:1.2rem; color:var(--text-muted)">反映が完了しました。ブラウザタブを閉じてください。</div>`;
        }, 1500);
    } catch (err) {
        alert('反映に失敗しました。');
        console.error(err);
    }
}

function shutdownServerGlobal() {
    confirmGlobalShutdown();
}

async function executeGlobalShutdown() {
    closeModal('shutdown-global-modal');
    try {
        await fetch('/api/shutdown', { method: 'POST' });
        window.close();
        document.body.innerHTML = `<div style="display:flex; justify-content:center; align-items:center; height:100vh; font-size:1.2rem; color:var(--text-muted)">サーバーを停止しました。ブラウザタブを閉じてください。</div>`;
    } catch (err) {
        console.error(err);
        window.close();
    }
}

function showToast(message, duration = 1500) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => { toast.classList.remove('show'); }, duration);
}

async function loadProjectConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (data.novel_title) {
            const titleEl = document.getElementById('novel-title-display');
            if (titleEl) titleEl.textContent = data.novel_title;
        }
    } catch (err) {
        console.error('Failed to load project config:', err);
    }
}

// Init Load
window.addEventListener('DOMContentLoaded', () => {
    loadProjectConfig();
    loadSourcesForWrite();
    loadDashboardData();
});
