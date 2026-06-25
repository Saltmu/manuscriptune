let isRunningProcess = false;
let novelLines = [];
let findings = [];
let activeCategoryFilter = 'all';
let activeSeverityFilter = 'all';
let activeHighlightLine = null;

let selectedNovelFile = localStorage.getItem('selectedNovelFile') || "";

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
        
        const reviewCardsContainer = document.getElementById('review-draft-cards-container');
        if (reviewCardsContainer) {
            reviewCardsContainer.innerHTML = '';
        }
        
        const hiddenInput = document.getElementById('review-file-select');
        const currentSelected = selectedNovelFile || (hiddenInput ? hiddenInput.value : "");
        let selectedFound = false;

        if (data.novels.length === 0) {
            if (reviewCardsContainer) {
                reviewCardsContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">小説が見つかりません。novels/ フォルダを確認してください。</div>`;
            }
        } else {
            data.novels.forEach(n => {
                if (reviewCardsContainer) {
                    const card = document.createElement('div');
                    card.className = 'draft-selection-card';
                    card.dataset.filename = n.name;
                    card.dataset.hasfindings = n.has_findings ? "true" : "false";
                    
                    const badgeHtml = n.has_findings 
                        ? `<span class="badge badge-success">指摘あり</span>` 
                        : `<span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>`;

                    let actionBtnHtml = '';
                    if (n.has_findings) {
                        actionBtnHtml = `<button class="draft-card-action-btn" onclick="event.stopPropagation(); selectAndEditNovel('${n.name}');">📝 校閲する</button>`;
                    }

                    card.innerHTML = `
                        <div class="draft-card-info">
                            <div class="draft-card-name">${n.name}</div>
                            <div class="draft-card-meta">
                                <span>${(n.size / 1024).toFixed(1)} KB</span>
                                <span>•</span>
                                <span>${n.last_modified}</span>
                            </div>
                        </div>
                        <div class="draft-card-status">
                            ${badgeHtml}
                        </div>
                        ${actionBtnHtml}
                    `;

                    card.addEventListener('click', () => {
                        selectDraftCard(n.name, n.has_findings);
                    });

                    reviewCardsContainer.appendChild(card);

                    if (currentSelected === n.name) {
                        card.classList.add('active');
                        selectedFound = true;
                    }
                }
            });

            // 以前の選択肢がリスト内で見つからない、あるいは未選択の場合は最初の要素を選択状態にする
            if (reviewCardsContainer && reviewCardsContainer.children.length > 0) {
                if (!selectedFound) {
                    const firstCard = reviewCardsContainer.children[0];
                    selectDraftCard(firstCard.dataset.filename, firstCard.dataset.hasfindings === "true");
                } else {
                    // すでに選択されている場合もプレビューをロード
                    const activeCard = Array.from(reviewCardsContainer.children).find(c => c.dataset.filename === currentSelected);
                    if (activeCard) {
                        loadPreview(currentSelected);
                    }
                }
            }
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

// Select draft card in Review View
function selectDraftCard(novelName, hasFindings) {
    const container = document.getElementById('review-draft-cards-container');
    if (!container) return;

    Array.from(container.children).forEach(card => {
        if (card.dataset.filename === novelName) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });

    const hiddenInput = document.getElementById('review-file-select');
    if (hiddenInput) {
        hiddenInput.value = novelName;
    }

    selectedNovelFile = novelName;
    localStorage.setItem('selectedNovelFile', selectedNovelFile);

    loadPreview(novelName);
}

// Load novel text preview into the right panel
async function loadPreview(novelName) {
    const header = document.getElementById('review-preview-header');
    const consoleHeader = document.getElementById('review-console-header');
    const previewBody = document.getElementById('review-preview-body');
    const consoleLog = document.getElementById('review-console-log');
    const filenameDisplay = document.getElementById('preview-filename-display');
    
    if (!previewBody) return;
    
    // 表示モードの切り替え
    if (header) header.style.display = 'flex';
    if (consoleHeader) consoleHeader.style.display = 'none';
    previewBody.style.display = 'block';
    if (consoleLog) consoleLog.style.display = 'none';
    
    if (filenameDisplay) filenameDisplay.textContent = novelName;
    previewBody.textContent = 'プレビューを読み込み中...';
    
    // スライドイン表示
    const rightPanel = document.getElementById('review-right-panel');
    if (rightPanel && !rightPanel.classList.contains('show')) {
        rightPanel.classList.add('show');
        updateToggleButtonText('view-review', true);
    }
    
    try {
        const res = await fetch(`/api/preview?file=${encodeURIComponent(novelName)}`);
        if (res.ok) {
            const data = await res.json();
            previewBody.textContent = data.content;
            previewBody.scrollTop = 0; // スクロールを一番上に
        } else {
            previewBody.textContent = 'プレビューの読み込みに失敗しました。';
        }
    } catch (err) {
        console.error(err);
        previewBody.textContent = 'プレビューのロード中にエラーが発生しました。';
    }
}

// Action: Select novel and switch to editor
async function selectAndEditNovel(novelName) {
    try {
        selectedNovelFile = novelName;
        localStorage.setItem('selectedNovelFile', selectedNovelFile);
        // Load Editor Data
        await loadEditorData();
        switchView('editor');
    } catch (err) {
        console.error(err);
        alert('ファイルの選択に失敗しました。');
    }
}

// Action: Select novel and switch to review view
function selectAndReviewNovel(novelName) {
    switchView('review');
    
    // カードリストから該当ファイルを探して選択
    const container = document.getElementById('review-draft-cards-container');
    if (container) {
        const card = Array.from(container.children).find(c => c.dataset.filename === novelName);
        if (card) {
            const hasFindings = card.dataset.hasfindings === "true";
            selectDraftCard(novelName, hasFindings);
            return;
        }
    }
    
    // 見つからない場合のフォールバック
    const hiddenInput = document.getElementById('review-file-select');
    if (hiddenInput) {
        hiddenInput.value = novelName;
    }
}

// Streaming Execution Log Helper using EventSource
function startEventStream(url, consoleId, statusId, onComplete = null) {
    const consoleEl = document.getElementById(consoleId);
    const statusEl = document.getElementById(statusId);
    
    consoleEl.textContent = '--- プロセスを開始します ---\n';
    statusEl.textContent = 'RUNNING';
    statusEl.style.color = '#fbbf24'; // Amber

    // 自動的に右側コンソールパネルを開く
    const rightPanel = consoleEl.closest('.right-panel');
    if (rightPanel) {
        rightPanel.classList.add('show');
        const viewEl = consoleEl.closest('.view-content');
        if (viewEl) {
            updateToggleButtonText(viewEl.id, true);
        }
    }

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

// Helper to update console toggle button text
function updateToggleButtonText(viewId, isShow) {
    const prefix = viewId.replace('view-', '');
    const toggleBtn = document.getElementById(`${prefix}-console-toggle`);
    if (toggleBtn) {
        toggleBtn.textContent = isShow ? '🖥️ コンソール非表示' : '🖥️ コンソール表示';
    }
}

// Manual Toggle for Consoles
function toggleConsole(viewId) {
    const prefix = viewId.replace('view-', '');
    const rightPanel = document.getElementById(`${prefix}-right-panel`);
    if (rightPanel) {
        const isShow = rightPanel.classList.toggle('show');
        updateToggleButtonText(viewId, isShow);
    }
}

// Initialize mouse resizing for sliding panels
function initPanelResizer(resizerId, rightPanelId) {
    const resizer = document.getElementById(resizerId);
    const rightPanel = document.getElementById(rightPanelId);
    if (!resizer || !rightPanel) return;

    resizer.addEventListener('mousedown', function(e) {
        e.preventDefault();
        resizer.classList.add('dragging');
        document.addEventListener('mousemove', resize);
        document.addEventListener('mouseup', stopResize);
    });

    function resize(e) {
        const container = resizer.parentElement;
        const containerWidth = container.clientWidth;
        const containerLeft = container.getBoundingClientRect().left;
        
        // Calculate width from the right edge
        const rightWidth = containerWidth - (e.clientX - containerLeft);
        
        // Constrain width between 300px and 70% of the viewport width
        if (rightWidth >= 300 && rightWidth <= containerWidth * 0.7) {
            rightPanel.style.width = rightWidth + 'px';
            rightPanel.style.flex = 'none'; // Override flex properties
        }
    }

    function stopResize() {
        resizer.classList.remove('dragging');
        document.removeEventListener('mousemove', resize);
        document.removeEventListener('mouseup', stopResize);
    }
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
    const characterVal = document.getElementById('write-character').value;
    const stepByStepVal = document.getElementById('write-step-by-step').checked;
    const selfCheckVal = document.getElementById('write-self-check').checked;

    const btn = document.getElementById('btn-run-write');
    btn.disabled = true;

    let url = `/api/stream/write?episode=${encodeURIComponent(epInput)}`;
    if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
    if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
    if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
    if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
    if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
    if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;
    if (stepByStepVal) url += `&step_by_step=true`;
    if (selfCheckVal) url += `&self_check=true`;

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

    // 表示をコンソールログ表示モードに切り替える
    const header = document.getElementById('review-preview-header');
    const consoleHeader = document.getElementById('review-console-header');
    const previewBody = document.getElementById('review-preview-body');
    const consoleLog = document.getElementById('review-console-log');
    
    if (header) header.style.display = 'none';
    if (consoleHeader) consoleHeader.style.display = 'flex';
    if (previewBody) previewBody.style.display = 'none';
    if (consoleLog) consoleLog.style.display = 'block';

    const btn = document.getElementById('btn-run-review');
    btn.disabled = true;
    btn.innerHTML = '🔍 レビュー実行中...';

    lastReviewedFile = fileName;

    const modelVal = document.getElementById('review-model').value;
    let url = `/api/stream/review?file=${encodeURIComponent(fileName)}`;
    if (modelVal) {
        url += `&model=${encodeURIComponent(modelVal)}`;
    }
    startEventStream(url, 'review-console-log', 'review-console-status', (success) => {
        btn.disabled = false;
        btn.innerHTML = '🔍 レビューパイプラインを実行';
        if (success) {
            showToast('レビューパイプラインが正常に完了しました');
            loadDashboardData();
        } else {
            showToast('レビュー中にエラーが発生しました');
        }
    });
}

// ================= EDITOR VIEW LOGIC (Merged) =================

// Load active editor data
async function loadEditorData() {
    try {
        if (!selectedNovelFile) {
            console.log('No active novel file selected.');
            return;
        }
        const response = await fetch(`/api/data?file=${encodeURIComponent(selectedNovelFile)}`);
        if (!response.ok) throw new Error('Data fetch failed');
        
        const data = await response.json();
        novelLines = data.novel_lines;
        findings = data.findings;
        
        document.getElementById('filename-display').textContent = data.novel_filename;
        
        // Show/hide rollback button based on backup existence
        const rollbackBtn = document.getElementById('btn-rollback');
        if (rollbackBtn) {
            rollbackBtn.style.display = data.has_backup ? 'inline-block' : 'none';
        }
        
        // If in edit mode, ensure textarea has the latest content
        const textarea = document.getElementById('novel-editor-textarea');
        if (textarea && textarea.style.display !== 'none') {
            textarea.value = novelLines.join('\n');
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
        if (!selectedNovelFile) return;
        await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ novel_name: selectedNovelFile, findings: findings })
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
    showModal('apply-progress-modal');

    const closeBtn = document.getElementById('btn-close-apply-progress');
    if (closeBtn) closeBtn.disabled = true;

    if (!selectedNovelFile) {
        showToast('小説ファイルが選択されていません。');
        if (closeBtn) closeBtn.disabled = false;
        closeModal('apply-progress-modal');
        return;
    }

    startEventStream(`/api/stream/apply?file=${encodeURIComponent(selectedNovelFile)}`, 'apply-console-log', 'apply-console-status', (success) => {
        if (closeBtn) closeBtn.disabled = false;
        if (success) {
            showToast('反映処理が完了しました');
        } else {
            showToast('反映処理中にエラーが発生しました');
        }
    });
}

// ================= INLINE EDITOR & ROLLBACK LOGIC =================

let isNovelEditMode = false;

function toggleEditMode() {
    const novelContent = document.getElementById('novel-content');
    const textarea = document.getElementById('novel-editor-textarea');
    const btnToggle = document.getElementById('btn-toggle-edit');
    const btnSave = document.getElementById('btn-save-novel');
    const editBadge = document.getElementById('edit-mode-badge');

    if (!novelContent || !textarea) return;

    isNovelEditMode = !isNovelEditMode;

    if (isNovelEditMode) {
        // Switch to edit mode
        textarea.value = novelLines.join('\n');
        novelContent.style.display = 'none';
        textarea.style.display = 'block';
        btnToggle.textContent = '❌ キャンセル';
        btnToggle.className = 'btn-secondary btn-sm';
        if (btnSave) btnSave.style.display = 'inline-block';
        if (editBadge) editBadge.style.display = 'inline-block';
    } else {
        // Switch to preview mode
        novelContent.style.display = 'block';
        textarea.style.display = 'none';
        btnToggle.textContent = '📝 直接編集';
        btnToggle.className = 'btn-secondary btn-sm';
        if (btnSave) btnSave.style.display = 'none';
        if (editBadge) editBadge.style.display = 'none';
    }
}

async function saveNovel() {
    const textarea = document.getElementById('novel-editor-textarea');
    const btnSave = document.getElementById('btn-save-novel');
    const btnToggle = document.getElementById('btn-toggle-edit');

    if (!textarea) return;

    // Control loader and block inputs
    if (btnSave) btnSave.disabled = true;
    if (btnToggle) btnToggle.disabled = true;
    textarea.disabled = true;

    try {
        if (!selectedNovelFile) {
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
            body: JSON.stringify({ novel_name: selectedNovelFile, content: textarea.value })
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

function confirmRollback() {
    if (confirm('本当に反映前のバックアップ状態に戻しますか？\n（現在の小説本文と指摘の反映ステータスが復元されます）')) {
        executeRollback();
    }
}

async function executeRollback() {
    const rollbackBtn = document.getElementById('btn-rollback');
    if (rollbackBtn) rollbackBtn.disabled = true;

    try {
        if (!selectedNovelFile) {
            showToast('小説ファイルが選択されていません。');
            if (rollbackBtn) rollbackBtn.disabled = false;
            return;
        }
        const response = await fetch(`/api/rollback?file=${encodeURIComponent(selectedNovelFile)}`, {
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

function closeApplyProgressModal() {
    closeModal('apply-progress-modal');
    loadEditorData();
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
        if (data.initial_novel && !selectedNovelFile) {
            selectedNovelFile = data.initial_novel;
            localStorage.setItem('selectedNovelFile', selectedNovelFile);
            loadEditorData();
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
    
    // Initialize resizers
    initPanelResizer('write-resizer', 'write-right-panel');
    initPanelResizer('review-resizer', 'review-right-panel');
    initPanelResizer('sync-resizer', 'sync-right-panel');
});

