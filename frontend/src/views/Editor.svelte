<script>
    import { onMount } from 'svelte';
    import { 
        selectedNovelFile, 
        activeEditorTab, 
        consoleLogMap, 
        selectedPlot,
        novelLines,
        findings,
        activeHighlightLine,
        novelMetadata,
        novelFilename
    } from '../store.js';
    import { startEventStream, showToast, initPanelResizer } from '../utils.js';
    import { apiFetch, withFreshToken } from '../lib/apiClient.js';
    
    // Sub-components
    import PlotPanel from '../lib/PlotPanel.svelte';
    import NovelPanel from '../lib/NovelPanel.svelte';
    import FindingsPanel from '../lib/FindingsPanel.svelte';
    import EditorModals from '../lib/EditorModals.svelte';

    let plotPanelEl;

    // Direct editing state
    let editMode = false;
    let editedText = '';

    // History restore state
    let historyList = [];
    let selectedVersion = '';

    // Modal visibility states
    let showApplyModal = false;
    let showApplyProgressModal = false;
    let applyConsoleStatus = 'READY';
    let applyConsoleLog = '--- 待機中 ---';
    let showRewriteConfirmModal = false;
    let pendingRewriteEpisode = null;

    // Process cancellation state
    let currentRequestId = null;
    let currentEventSource = null;

    // Element bindings
    let resizerEl;
    let rightPanelEl;

    // Filters reactively computed
    $: acceptedCount  = $findings.filter(f => f.accepted === 'y').length;
    $: dismissedCount = $findings.filter(f => f.accepted === 'n').length;
    $: undecidedCount = $findings.filter(f => f.accepted !== 'y' && f.accepted !== 'n').length;
    
    $: findingsByLine = (() => {
        const map = {};
        $findings.forEach(f => {
            const lineNo = parseLineNumber(f.location);
            if (lineNo) {
                if (!map[lineNo]) map[lineNo] = [];
                map[lineNo].push(f);
            }
        });
        return map;
    })();

    // Helper functions
    function parseLineNumber(locationStr) {
        if (!locationStr) return null;
        const match = String(locationStr).match(/(\d+)/);
        return match ? parseInt(match[0], 10) : null;
    }

    async function selectAndLoadNovelFile(novelFile) {
        if (!novelFile) return;
        editMode = false;
        try {
            const response = await fetch(`/api/data?file=${encodeURIComponent(novelFile)}`);
            if (!response.ok) throw new Error('Data fetch failed');
            
            const data = await response.json();
            novelLines.set(data.novel_lines || []);
            findings.set(data.findings || []);
            novelMetadata.set(data.metadata || {});
            novelFilename.set(data.novel_filename || novelFile);

            // Fetch backup history
            await loadHistory(novelFile);
        } catch (err) {
            console.error(err);
            showToast('データの読み込みに失敗しました。');
        }
    }

    async function loadHistory(novelFile) {
        try {
            const response = await fetch(`/api/history?file=${encodeURIComponent(novelFile)}`);
            if (response.ok) {
                const data = await response.json();
                historyList = data.history || [];
                if (historyList.length > 0) {
                    selectedVersion = historyList[0];
                }
            }
        } catch (err) {
            console.error('Failed to load history:', err);
        }
    }

    // Actions
    async function setDecision(findingId, val) {
        const list = $findings;
        const finding = list.find(f => f.id === findingId);
        if (!finding) return;
        // 同じ判断を再度押したら未判断に戻す
        finding.accepted = (finding.accepted === val) ? null : val;
        findings.set(list);
        await saveChanges();
    }

    async function saveChanges() {
        if (!$selectedNovelFile) return;
        try {
            await apiFetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    novel_name: $selectedNovelFile,
                    findings: $findings,
                    metadata: $novelMetadata
                })
            });
            showToast('自動保存しました');
        } catch (err) {
            console.error('Save failed:', err);
            showToast('自動保存に失敗しました');
        }
    }

    function toggleEditMode() {
        editMode = !editMode;
        if (editMode) {
            editedText = $novelLines.join('\n');
        }
    }

    async function saveNovel() {
        if (!$selectedNovelFile) return;
        try {
            const response = await apiFetch('/api/save_novel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ novel_name: $selectedNovelFile, content: editedText })
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                showToast('小説本文を保存しました');
                editMode = false;
                await selectAndLoadNovelFile($selectedNovelFile);
            } else {
                showToast('保存に失敗しました: ' + (data.detail || ''));
            }
        } catch (err) {
            console.error(err);
            showToast('保存中に通信エラーが発生しました');
        }
    }

    async function executeRollback() {
        if (!$selectedNovelFile) return;
        if (!confirm('本当に反映前のバックアップ状態に戻しますか？\n（現在の小説本文と指摘の反映ステータスが復元されます）')) return;
        
        try {
            const response = await apiFetch(`/api/rollback?file=${encodeURIComponent($selectedNovelFile)}`, {
                method: 'POST'
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                showToast('バックアップから元に戻しました');
                await selectAndLoadNovelFile($selectedNovelFile);
            } else {
                showToast('元に戻す処理に失敗しました: ' + (data.detail || ''));
            }
        } catch (err) {
            console.error(err);
            showToast('通信エラーが発生しました');
        }
    }

    async function executeRestoreHistory() {
        if (!$selectedNovelFile || !selectedVersion) return;
        if (!confirm(`本当にバージョン ${selectedVersion.substring(1)} の状態に復元しますか？\n（小説本文と指摘の反映ステータスがその時点のものに戻ります）`)) return;

        try {
            const response = await apiFetch(`/api/rollback?file=${encodeURIComponent($selectedNovelFile)}&version=${encodeURIComponent(selectedVersion)}`, {
                method: 'POST'
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                showToast(`バージョン ${selectedVersion.substring(1)} に復元しました`);
                await selectAndLoadNovelFile($selectedNovelFile);
            } else {
                showToast('復元処理に失敗しました: ' + (data.detail || ''));
            }
        } catch (err) {
            console.error(err);
            showToast('通信エラーが発生しました');
        }
    }

    // Apply Findings pipeline (SSE)
    async function handleApplyFindings() {
        showApplyModal = false;
        showApplyProgressModal = true;
        applyConsoleStatus = 'RUNNING';
        applyConsoleLog = '--- プロセスを開始します ---\n';

        const url = await withFreshToken(`/api/stream/apply?file=${encodeURIComponent($selectedNovelFile)}`);
        const eventSource = new EventSource(url);

        eventSource.onmessage = function(event) {
            if (event.data.includes('[PROCESS_EXITED]')) {
                const code = event.data.split('code=')[1] || '0';
                applyConsoleLog += `\n--- プロセスが終了しました (終了コード: ${code}) ---\n`;
                applyConsoleStatus = code === '0' ? 'COMPLETED' : 'FAILED';
                eventSource.close();
                
                if (code === '0') {
                    showToast('反映処理が完了しました');
                } else {
                    showToast('反映処理中にエラーが発生しました');
                }
                return;
            }
            applyConsoleLog += event.data + '\n';
            
            // Auto scroll progress console
            setTimeout(() => {
                const consoleEl = document.getElementById('apply-progress-console-log');
                if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
            }, 10);
        };

        eventSource.onerror = function() {
            applyConsoleLog += '\n[ERROR] 接続エラーまたはサーバーが切断されました。\n';
            applyConsoleStatus = 'CONNECTION ERROR';
            eventSource.close();
            showToast('接続エラーが発生しました');
        };
    }

    function closeApplyProgress() {
        showApplyProgressModal = false;
        selectAndLoadNovelFile($selectedNovelFile);
    }

    // AI Write Episode
    function openRewriteConfirm(ep) {
        pendingRewriteEpisode = ep;
        showRewriteConfirmModal = true;
    }

    function confirmRewrite() {
        showRewriteConfirmModal = false;
        if (pendingRewriteEpisode) {
            runWriteForEpisode(pendingRewriteEpisode.title);
        }
        pendingRewriteEpisode = null;
    }

    async function runWriteForEpisode(episodeTitle) {
        const titleVal = localStorage.getItem('settings-title') || '重天の調律師';
        const modelVal = localStorage.getItem('settings-model') || 'Gemini 3.5 Flash (High)';
        const policyGlobal = localStorage.getItem('settings-policy-global') || '';
        const policyChapter = localStorage.getItem('settings-policy-chapter') || '';
        const character = localStorage.getItem('settings-character') || '';

        activeEditorTab.set('logs');

        let url = `/api/stream/write?episode=${encodeURIComponent(episodeTitle)}`;
        if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
        if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
        if ($selectedPlot) url += `&plot=${encodeURIComponent($selectedPlot)}`;
        if (policyGlobal) url += `&policy_global=${encodeURIComponent(policyGlobal)}`;
        if (policyChapter) url += `&policy_chapter=${encodeURIComponent(policyChapter)}`;
        if (character) url += `&character=${encodeURIComponent(character)}`;
        url += `&step_by_step=true&self_check=true`;

        const freshUrl = await withFreshToken(url);
        const result = startEventStream(freshUrl, 'editor', async (success) => {
            currentRequestId = null;
            currentEventSource = null;
            if (success) {
                showToast('AI執筆が完了しました');

                const logContent = $consoleLogMap.editor;
                const match = logContent.match(/Success! Novel saved to novels\/([^\s\r\n]+)/);
                if (match) {
                    const filename = match[1];
                    if (plotPanelEl) {
                        await plotPanelEl.refreshEpisodes();
                    }
                    await selectAndLoadNovelFile(filename);

                    setTimeout(async () => {
                        if (confirm(`AI執筆が完了し、新規ファイル「${filename}」がロードされました。すぐに本文レビュー（校閲）を実行しますか？`)) {
                            await runReviewForFile(filename);
                        }
                    }, 300);
                } else {
                    if (plotPanelEl) {
                        await plotPanelEl.refreshEpisodes();
                    }
                }
            } else {
                showToast('執筆中にエラーが発生しました');
            }
        });
        if (result) {
            currentEventSource = result.eventSource;
            currentRequestId = result.requestId;
        }
    }

    // AI Review File
    async function runReviewForFile(novelFile) {
        activeEditorTab.set('logs');
        const modelVal = localStorage.getItem('settings-model') || 'Gemini 3.5 Flash (High)';

        let url = `/api/stream/review?file=${encodeURIComponent(novelFile)}`;
        if (modelVal) {
            url += `&model=${encodeURIComponent(modelVal)}`;
        }

        const freshUrl = await withFreshToken(url);
        const result = startEventStream(freshUrl, 'editor', async (success) => {
            currentRequestId = null;
            currentEventSource = null;
            if (success) {
                showToast('レビューパイプラインが正常に完了しました');
                if (plotPanelEl) {
                    await plotPanelEl.refreshEpisodes();
                }
                await selectAndLoadNovelFile(novelFile);
                activeEditorTab.set('findings');
            } else {
                showToast('レビュー中にエラーが発生しました');
            }
        });
        if (result) {
            currentEventSource = result.eventSource;
            currentRequestId = result.requestId;
        }
    }

    // UI Interactive helpers
    function handleLineClick(lineNo, firstFindingId) {
        activeHighlightLine.set(lineNo);
        if (firstFindingId) {
            const cardEl = document.getElementById(`finding-card-${firstFindingId}`);
            if (cardEl) {
                cardEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    function handleFindingCardClick(lineNo, findingId) {
        if (lineNo) {
            activeHighlightLine.set(lineNo);
            const lineEl = document.getElementById(`novel-line-${lineNo}`);
            if (lineEl) {
                lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    function handleSelectNovelFileEvent(event) {
        selectAndLoadNovelFile(event.detail);
    }

    function handleShowFindingsEvent(event) {
        selectAndLoadNovelFile(event.detail);
        activeEditorTab.set('findings');
    }

    // Lifecycle
    onMount(() => {
        if ($selectedNovelFile) {
            selectAndLoadNovelFile($selectedNovelFile);
        }
        if (resizerEl && rightPanelEl) {
            initPanelResizer(resizerEl, rightPanelEl);
        }
    });
</script>

<div class="view-content active" id="view-editor">
    <!-- Header for Editor -->
    <div class="editor-header">
        <div>
            <h3 style="font-size:1.15rem; font-weight:700;">エピソード管理・校閲エディタ</h3>
            <p style="font-size:0.8rem; color:var(--text-muted)">プロット連動の執筆・自動校閲・反映</p>
        </div>
        <div style="display:flex; align-items:center; gap:16px;">
            {#if $selectedNovelFile && $findings.length > 0}
                <div class="decision-progress">
                    <div class="dp-counts">
                        <span class="dp-accepted">採用 {acceptedCount}</span>
                        <span class="dp-undecided">未判断 {undecidedCount}</span>
                        <span class="dp-dismissed">見送り {dismissedCount}</span>
                        <span class="dp-total">全 {$findings.length} 件</span>
                    </div>
                    <div class="decision-progress-bar">
                        <div class="seg accepted"  style="flex-grow:{acceptedCount}"></div>
                        <div class="seg undecided" style="flex-grow:{undecidedCount}"></div>
                        <div class="seg dismissed" style="flex-grow:{dismissedCount}"></div>
                    </div>
                </div>
            {/if}
            
            {#if $selectedNovelFile && historyList.length > 0}
                <div style="display: flex; align-items: center; gap: 8px;">
                    <select bind:value={selectedVersion} style="background: var(--panel-bg); color: var(--text-main); border: 1px solid var(--border-color); border-radius: 4px; padding: 4px 8px; font-size: 0.8rem; height: 32px; width: auto;">
                        {#each historyList as version}
                            <option value={version}>{version.substring(1)}</option>
                        {/each}
                    </select>
                    <button class="btn-secondary btn-sm" on:click={executeRestoreHistory} style="background-color: rgba(59, 130, 246, 0.1); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3);">
                        ↩️ 履歴から復元
                    </button>
                </div>
            {/if}

            {#if $selectedNovelFile}
                <button class="btn-secondary btn-sm" on:click={executeRollback} style="background-color: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);">
                    ↩️ 元に戻す
                </button>
                <button class="btn-primary btn-sm" on:click={() => showApplyModal = true} disabled={acceptedCount === 0}>
                    小説へ反映{acceptedCount > 0 ? ` (${acceptedCount}件)` : ''}
                </button>
            {/if}
        </div>
    </div>

    <!-- Fallback/Warning Banners -->
    {#if $selectedNovelFile && $novelMetadata && ($novelMetadata.fallback_mode || $novelMetadata.completeness === 'low')}
        <div class="warning-banner" style="display: flex; margin: 16px 24px 0 24px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span>⚠️</span>
                <span>{$novelMetadata.reason || 'LLMによる指摘の統合に失敗したため、機械的なマージを使用しています。重複や矛盾が残っている可能性があります。'}</span>
            </div>
        </div>
    {/if}

    <!-- Editor split layout -->
    <div class="editor-container">
        <!-- Column 1: Plot Panel -->
        <PlotPanel 
            bind:this={plotPanelEl}
            on:select-novel-file={handleSelectNovelFileEvent}
            on:run-write={(e) => runWriteForEpisode(e.detail)}
            on:open-rewrite={(e) => openRewriteConfirm(e.detail)}
            on:run-review={(e) => runReviewForFile(e.detail)}
            on:show-findings={handleShowFindingsEvent}
        />

        <!-- Column 2: Novel Text (Preview / Direct Edit) -->
        <NovelPanel 
            bind:editMode={editMode}
            bind:editedText={editedText}
            findingsByLine={findingsByLine}
            on:toggle-edit={toggleEditMode}
            on:save-novel={saveNovel}
            on:line-click={(e) => handleLineClick(e.detail.lineNo, e.detail.firstFindingId)}
        />

        <!-- Column 3: Findings / Execution Logs -->
        <FindingsPanel
            on:toggle-decision={(e) => setDecision(e.detail.findingId, e.detail.val)}
            on:finding-card-click={(e) => handleFindingCardClick(e.detail.lineNo, e.detail.findingId)}
        />
    </div>
</div>

<!-- Modals -->
<EditorModals 
    bind:showApplyModal={showApplyModal}
    bind:showApplyProgressModal={showApplyProgressModal}
    bind:showRewriteConfirmModal={showRewriteConfirmModal}
    pendingRewriteEpisode={pendingRewriteEpisode}
    applyConsoleStatus={applyConsoleStatus}
    applyConsoleLog={applyConsoleLog}
    on:close-apply-modal={() => showApplyModal = false}
    on:close-rewrite-modal={() => { showRewriteConfirmModal = false; pendingRewriteEpisode = null; }}
    on:execute-apply={handleApplyFindings}
    on:confirm-rewrite={confirmRewrite}
    on:close-apply-progress={closeApplyProgress}
/>
