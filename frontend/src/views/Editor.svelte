<script>
    import { onMount, tick } from 'svelte';
    import { 
        selectedNovelFile, 
        activeEditorTab, 
        isRunningProcess, 
        consoleLogMap, 
        consoleStatusMap, 
        selectedPlot,
        novelLines,
        findings,
        activeCategoryFilter,
        activeHighlightLine,
        activeSeverityFilter,
        novelMetadata,
        novelFilename
    } from '../store.js';
    import { startEventStream, showToast, initPanelResizer } from '../utils.js';
    import FindingChat from '../lib/FindingChat.svelte';

    let plots = [];
    let chapters = [];
    let loadingPlots = true;
    let loadingEpisodes = false;
    let loadingEditor = false;
    let activeChatFindingId = null;

    function toggleChat(findingId) {
        if (activeChatFindingId === findingId) {
            activeChatFindingId = null;
        } else {
            activeChatFindingId = findingId;
        }
    }

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

    // Element bindings
    let resizerEl;
    let rightPanelEl;

    // Filters reactively computed
    $: acceptedCount = $findings.filter(f => f.accepted === 'y').length;
    
    $: filteredFindings = $findings.filter(f => {
        const isLogic = isLogicCategory(f.category);
        if ($activeCategoryFilter === 'logic' && !isLogic) return false;
        if ($activeCategoryFilter === 'style' && isLogic) return false;
        if ($activeSeverityFilter !== 'all' && String(f.severity).toLowerCase() !== $activeSeverityFilter) return false;
        return true;
    });

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

    function isLogicCategory(category) {
        const cat = String(category).toLowerCase();
        return cat.includes('ロジック') || cat.includes('設定') || cat.includes('矛盾') || cat.includes('伏線') || cat.includes('整合性') || cat.includes('logic');
    }

    // Load initialization data
    async function loadPlots() {
        try {
            const response = await fetch('/api/plots');
            if (response.ok) {
                const data = await response.json();
                plots = data.plots || [];
                
                if ($selectedPlot) {
                    await loadEpisodeCards($selectedPlot);
                }
            }
        } catch (err) {
            console.error('Failed to load plots:', err);
        } finally {
            loadingPlots = false;
        }
    }

    async function loadEpisodeCards(plotName) {
        if (!plotName) return;
        loadingEpisodes = true;
        selectedPlot.set(plotName);
        try {
            const response = await fetch(`/api/plot/episodes_status?file=${encodeURIComponent(plotName)}`);
            if (response.ok) {
                const data = await response.json();
                chapters = data.chapters || [];
            }
        } catch (err) {
            console.error(err);
            showToast('エピソード情報の取得に失敗しました。');
        } finally {
            loadingEpisodes = false;
        }
    }

    async function selectAndLoadNovelFile(novelFile) {
        if (!novelFile) return;
        loadingEditor = true;
        selectedNovelFile.set(novelFile);
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
        } finally {
            loadingEditor = false;
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
    async function toggleAccept(findingId, isChecked) {
        const list = $findings;
        const finding = list.find(f => f.id === findingId);
        if (finding) {
            finding.accepted = isChecked ? 'y' : 'n';
            findings.set(list);
            await saveChanges();
        }
    }

    async function saveChanges() {
        if (!$selectedNovelFile) return;
        try {
            await fetch('/api/save', {
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
        loadingEditor = true;
        try {
            const response = await fetch('/api/save_novel', {
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
        } finally {
            loadingEditor = false;
        }
    }

    async function executeRollback() {
        if (!$selectedNovelFile) return;
        if (!confirm('本当に反映前のバックアップ状態に戻しますか？\n（現在の小説本文と指摘の反映ステータスが復元されます）')) return;
        
        loadingEditor = true;
        try {
            const response = await fetch(`/api/rollback?file=${encodeURIComponent($selectedNovelFile)}`, {
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
        } finally {
            loadingEditor = false;
        }
    }

    async function executeRestoreHistory() {
        if (!$selectedNovelFile || !selectedVersion) return;
        if (!confirm(`本当にバージョン ${selectedVersion.substring(1)} の状態に復元しますか？\n（小説本文と指摘の反映ステータスがその時点のものに戻ります）`)) return;

        loadingEditor = true;
        try {
            const response = await fetch(`/api/rollback?file=${encodeURIComponent($selectedNovelFile)}&version=${encodeURIComponent(selectedVersion)}`, {
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
        } finally {
            loadingEditor = false;
        }
    }

    // Apply Findings pipeline (SSE)
    function handleApplyFindings() {
        showApplyModal = false;
        showApplyProgressModal = true;
        applyConsoleStatus = 'RUNNING';
        applyConsoleLog = '--- プロセスを開始します ---\n';

        const eventSource = new EventSource(`/api/stream/apply?file=${encodeURIComponent($selectedNovelFile)}`);
        
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
    function runWriteForEpisode(episodeTitle) {
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

        startEventStream(url, 'editor', async (success) => {
            if (success) {
                showToast('AI執筆が完了しました');
                
                const logContent = $consoleLogMap.editor;
                const match = logContent.match(/Success! Novel saved to novels\/([^\s\r\n]+)/);
                if (match) {
                    const filename = match[1];
                    await loadEpisodeCards($selectedPlot);
                    await selectAndLoadNovelFile(filename);
                    
                    setTimeout(async () => {
                        if (confirm(`AI執筆が完了し、新規ファイル「${filename}」がロードされました。すぐに本文レビュー（校閲）を実行しますか？`)) {
                            await runReviewForFile(filename);
                        }
                    }, 300);
                } else {
                    await loadEpisodeCards($selectedPlot);
                }
            } else {
                showToast('執筆中にエラーが発生しました');
            }
        });
    }

    // AI Review File
    function runReviewForFile(novelFile) {
        activeEditorTab.set('logs');
        const modelVal = localStorage.getItem('settings-model') || 'Gemini 3.5 Flash (High)';

        let url = `/api/stream/review?file=${encodeURIComponent(novelFile)}`;
        if (modelVal) {
            url += `&model=${encodeURIComponent(modelVal)}`;
        }

        startEventStream(url, 'editor', async (success) => {
            if (success) {
                showToast('レビューパイプラインが正常に完了しました');
                if ($selectedPlot) {
                    await loadEpisodeCards($selectedPlot);
                }
                await selectAndLoadNovelFile(novelFile);
                activeEditorTab.set('findings');
            } else {
                showToast('レビュー中にエラーが発生しました');
            }
        });
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

    // Lifecycle
    onMount(() => {
        loadPlots();
        if ($selectedNovelFile) {
            selectAndLoadNovelFile($selectedNovelFile);
        }
        if (resizerEl && rightPanelEl) {
            initPanelResizer(resizerEl, rightPanelEl);
        }
    });
</script>

<div class="view-content active" id="view-editor">
    {#if loadingEditor}
        <div class="view-loading-overlay active">
            <div class="spinner"></div>
            <div class="view-loading-text">読み込み中...</div>
        </div>
    {/if}

    <!-- Header for Editor -->
    <div class="editor-header">
        <div>
            <h3 style="font-size:1.15rem; font-weight:700;">エピソード管理・校閲エディタ</h3>
            <p style="font-size:0.8rem; color:var(--text-muted)">プロット連動の執筆・自動校閲・反映</p>
        </div>
        <div style="display:flex; align-items:center; gap:16px;">
            {#if $selectedNovelFile && $findings.length > 0}
                <div class="stats-counter" style="display: block;">
                    採用: <span>{acceptedCount}</span> / <span>{$findings.length}</span> 件
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
                <button class="btn-primary btn-sm" on:click={() => showApplyModal = true}>
                    小説へ反映
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
        <!-- Column 1: Plot Selector & Episode Cards -->
        <div class="plot-panel">
            <div class="panel-header" style="display: flex; flex-direction: column; gap: 8px; align-items: stretch; height: auto; padding: 16px 16px 8px 16px; border-bottom: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="font-size: 1rem;">🗺️ プロット選択</h2>
                    {#if $isRunningProcess}
                        <span class="badge" style="background-color: rgba(251, 191, 36, 0.15); color: #fbbf24; display: inline-block;">RUNNING</span>
                    {:else}
                        <span class="badge" style="background-color: rgba(16, 185, 129, 0.15); color: #34d399; display: inline-block;">READY</span>
                    {/if}
                </div>
                <select bind:value={$selectedPlot} on:change={(e) => loadEpisodeCards(e.target.value)} style="width: 100%; padding: 8px 12px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.85rem;">
                    <option value="">(プロットを選択してください)</option>
                    {#each plots as p}
                        <option value={p.name}>{p.name}</option>
                    {/each}
                </select>
            </div>
            
            <div style="flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px;" id="episode-cards-container">
                {#if loadingEpisodes}
                    <div style="text-align: center; color: var(--text-muted); padding-top: 40px;">読み込み中...</div>
                {:else if chapters.length === 0}
                    <div style="text-align: center; color: var(--text-muted); padding-top: 40px;">
                        プロットファイルを選択してください。
                    </div>
                {:else}
                    {#each chapters as ch}
                        <h3 style="font-size: 0.9rem; color: var(--text-muted); margin-top: 16px; margin-bottom: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 4px;">
                            {ch.title}: {ch.name}
                        </h3>
                        {#each ch.episodes as ep}
                            {@const isActive = $selectedNovelFile === ep.novel_file}
                            <!-- svelte-ignore a11y-click-events-have-key-events -->
                            <div class="draft-selection-card {isActive ? 'active' : ''}" on:click={() => ep.novel_file ? selectAndLoadNovelFile(ep.novel_file) : showToast('このエピソードはまだ執筆されていません。執筆ボタンを押してください。')}>
                                <div class="draft-card-info">
                                    <div class="draft-card-name">{ep.title}: {ep.name}</div>
                                    <div class="draft-card-status" style="margin-top: 6px;">
                                        {#if ep.status === 'unwritten'}
                                            <span class="badge badge-primary">未執筆</span>
                                        {:else if ep.status === 'written'}
                                            <span class="badge badge-warning">執筆済</span>
                                        {:else if ep.status === 'reviewed'}
                                            <span class="badge badge-success">レビュー済 ({ep.findings_count}指摘)</span>
                                        {/if}
                                    </div>
                                </div>
                                <div style="display: flex; gap: 8px; width: 100%; margin-top: 8px;">
                                    {#if ep.status === 'unwritten'}
                                        <button class="draft-card-action-btn" on:click|stopPropagation={() => runWriteForEpisode(ep.title)}>
                                            ✍️ 執筆する
                                        </button>
                                    {:else}
                                        <button class="draft-card-action-btn" style="background-color: rgba(255,255,255,0.05); color: var(--text-main); border: 1px solid var(--border-color); flex: 1;" on:click|stopPropagation={() => runWriteForEpisode(ep.title)}>
                                            🔄 再執筆
                                        </button>
                                        <button class="draft-card-action-btn" style="flex: 1;" on:click|stopPropagation={() => runReviewForFile(ep.novel_file)}>
                                            🔍 レビュー
                                        </button>
                                    {/if}
                                </div>
                                {#if ep.status === 'reviewed' && ep.findings_count > 0}
                                    <button class="draft-card-action-btn" style="background-color: var(--logic-color); width: 100%;" on:click|stopPropagation={() => { selectAndLoadNovelFile(ep.novel_file); activeEditorTab.set('findings'); }}>
                                        📋 指摘確認
                                    </button>
                                {/if}
                            </div>
                        {/each}
                    {/each}
                {/if}
            </div>
        </div>

        <!-- Column 2: Novel Text (Preview / Direct Edit) -->
        <div class="novel-panel">
            <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding: 12px 20px; flex-shrink: 0; background-color: rgba(15, 23, 42, 0.2); height: 50px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <h2 style="display: inline-block; margin-right: 8px; font-size: 1rem; margin-bottom: 0;">{$novelFilename || '-'}</h2>
                    {#if editMode}
                        <span class="badge" style="background-color: rgba(245, 158, 11, 0.15); color: #fbbf24;">直接編集</span>
                    {/if}
                </div>
                {#if $selectedNovelFile}
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <button class="btn-secondary btn-sm" on:click={toggleEditMode} style="padding: 4px 8px; font-size: 0.75rem;">
                            {editMode ? '❌ キャンセル' : '📝 直接編集'}
                        </button>
                        {#if editMode}
                            <button class="btn-primary btn-sm" on:click={saveNovel} style="padding: 4px 8px; font-size: 0.75rem;">
                                💾 保存
                            </button>
                        {/if}
                    </div>
                {/if}
            </div>
            
            <div class="novel-content-container" style="flex: 1; min-height: 0; position: relative; display: flex; flex-direction: column;">
                {#if !editMode}
                    <div class="novel-content" id="novel-content" style="flex: 1; overflow-y: auto;">
                        {#if $novelLines.length === 0}
                            <div style="text-align: center; color: var(--text-muted); padding-top: 60px;">
                                左ペインからエピソードを選択するか、執筆を開始してください。
                            </div>
                        {:else}
                            {#each $novelLines as line, index}
                                {@const lineNo = index + 1}
                                {@const lineFindings = findingsByLine[lineNo]}
                                {@const hasFindings = lineFindings && lineFindings.length > 0}
                                {@const hasLogic = hasFindings && lineFindings.some(f => isLogicCategory(f.category))}
                                {@const hasStyle = hasFindings && lineFindings.some(f => !isLogicCategory(f.category))}
                                {@const isHighlight = $activeHighlightLine === lineNo}
                                
                                <!-- svelte-ignore a11y-click-events-have-key-events -->
                                <div 
                                    class="novel-line-wrapper {hasFindings ? 'has-finding' : ''} {hasLogic ? 'finding-logic' : hasStyle ? 'finding-style' : ''} {isHighlight ? 'highlight' : ''}" 
                                    id="novel-line-{lineNo}"
                                    on:click={() => hasFindings && handleLineClick(lineNo, lineFindings[0].id)}
                                >
                                    <span class="novel-line-number">{lineNo}</span>
                                    <span class="novel-line-text">{line || ' '}</span>
                                </div>
                            {/each}
                        {/if}
                    </div>
                {:else}
                    <textarea 
                        bind:value={editedText} 
                        style="flex: 1; width: 100%; height: 100%; resize: none; background-color: #1e293b; color: #f8fafc; border: 1px solid var(--border-color); padding: 12px; font-family: monospace; font-size: 0.95rem; line-height: 1.6; border-radius: 4px; box-sizing: border-box; outline: none;" 
                        placeholder="ここに本文が表示されます"
                    ></textarea>
                {/if}
            </div>
        </div>

        <!-- Column 3: Findings / Execution Logs -->
        <div class="findings-panel">
            <div class="tabs-header" style="display: flex; gap: 4px; border-bottom: 1px solid var(--border-color); background-color: rgba(15, 23, 42, 0.4); flex-shrink: 0; height: 50px;">
                <button class="tab-btn {$activeEditorTab === 'findings' ? 'active' : ''}" on:click={() => activeEditorTab.set('findings')}>
                    📋 指摘一覧
                </button>
                <button class="tab-btn {$activeEditorTab === 'logs' ? 'active' : ''}" on:click={() => activeEditorTab.set('logs')}>
                    🖥️ ログ表示
                </button>
            </div>

            <!-- Tab Content 1: Findings list inside Column 3 -->
            {#if $activeEditorTab === 'findings'}
                <div class="tab-content" style="display: flex; flex-direction: column; flex: 1; overflow: hidden; height: 100%;">
                    <!-- Filter Options -->
                    <div class="filter-bar" style="display: flex; gap: 8px; padding: 8px 20px; border-bottom: 1px solid var(--border-color); background-color: rgba(15, 23, 42, 0.2); overflow-x: auto; flex-shrink: 0;">
                        <button class="filter-btn {$activeCategoryFilter === 'all' ? 'active' : ''}" on:click={() => activeCategoryFilter.set('all')}>すべて</button>
                        <button class="filter-btn {$activeCategoryFilter === 'logic' ? 'active' : ''}" on:click={() => activeCategoryFilter.set('logic')}>設定監査 (Logic)</button>
                        <button class="filter-btn {$activeCategoryFilter === 'style' ? 'active' : ''}" on:click={() => activeCategoryFilter.set('style')}>文芸表現 (Style)</button>
                        <div style="width: 1px; height: 16px; background-color: var(--border-color); align-self: center; margin: 0 4px;"></div>
                        <button class="filter-btn {$activeSeverityFilter === 'all' ? 'active' : ''}" on:click={() => activeSeverityFilter.set('all')}>全重要度</button>
                        <button class="filter-btn {$activeSeverityFilter === 'high' ? 'active' : ''}" on:click={() => activeSeverityFilter.set('high')}>重大 (High)</button>
                        <button class="filter-btn {$activeSeverityFilter === 'medium' ? 'active' : ''}" on:click={() => activeSeverityFilter.set('medium')}>中 (Medium)</button>
                        <button class="filter-btn {$activeSeverityFilter === 'low' ? 'active' : ''}" on:click={() => activeSeverityFilter.set('low')}>軽微 (Low)</button>
                    </div>
                    
                    <div class="findings-list" style="flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px;">
                        {#if filteredFindings.length === 0}
                            <div style="text-align: center; color: var(--text-muted); padding-top: 60px;">
                                指摘はありません。
                            </div>
                        {:else}
                            {#each filteredFindings as f}
                                {@const isLogic = isLogicCategory(f.category)}
                                {@const lineNo = parseLineNumber(f.location)}
                                {@const isCardHighlight = $activeHighlightLine === lineNo}
                                
                                <!-- svelte-ignore a11y-click-events-have-key-events -->
                                <div 
                                    class="finding-card {isLogic ? 'logic' : 'style'} {isCardHighlight ? 'active' : ''}" 
                                    id="finding-card-{f.id}"
                                    on:click={() => handleFindingCardClick(lineNo, f.id)}
                                >
                                    <div class="card-header">
                                        <div class="card-meta">
                                            <span class="badge badge-id">{f.id}</span>
                                            <span class="badge badge-category {isLogic ? 'logic' : 'style'}">{f.category}</span>
                                            <span class="badge badge-severity {String(f.severity).toLowerCase()}">{f.severity}</span>
                                            {#if f.apply_status === 'success' || f.apply_status === 'applied'}
                                                <span class="badge badge-apply-success">反映済み (applied)</span>
                                            {:else if f.apply_status === 'failed'}
                                                <span class="badge badge-apply-failed">失敗 (failed)</span>
                                            {:else}
                                                <span class="badge badge-apply-pending">未反映 (pending)</span>
                                            {/if}
                                        </div>
                                        <div class="toggle-container" on:click|stopPropagation>
                                            <span class="toggle-label">採用</span>
                                            <label class="toggle-switch">
                                                <input type="checkbox" checked={f.accepted === 'y'} on:change={(e) => toggleAccept(f.id, e.target.checked)}>
                                                <span class="slider"></span>
                                            </label>
                                        </div>
                                    </div>
                                    <div class="card-location">場所: {f.location}</div>
                                    <div class="card-field">
                                        <div class="field-label">分析</div>
                                        <div class="field-value analysis-text">{f.analysis}</div>
                                    </div>
                                    <div class="card-field">
                                        <div class="field-label">対象テキスト</div>
                                        <div class="field-value original-text">「{f.original}」</div>
                                    </div>
                                    <div class="card-field">
                                        <div class="field-label">修正提案</div>
                                        <div class="field-value suggestion-text">{f.suggestion}</div>
                                    </div>
                                    {#if f.apply_status === 'failed'}
                                        <div class="apply-error-msg">
                                            <strong>反映失敗:</strong> {f.apply_result || '原因不明のエラー'}
                                        </div>
                                    {/if}

                                    <!-- svelte-ignore a11y-click-events-have-key-events -->
                                    <!-- svelte-ignore a11y-no-static-element-interactions -->
                                    <div class="card-actions" style="margin-top: 12px; display: flex; gap: 8px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px;" on:click|stopPropagation>
                                        <button class="filter-btn {activeChatFindingId === f.id ? 'active' : ''}" style="padding: 4px 8px; font-size: 0.75rem;" on:click={() => toggleChat(f.id)}>
                                            {activeChatFindingId === f.id ? '相談を閉じる' : '💬 AIと相談する'}
                                        </button>
                                    </div>

                                    {#if activeChatFindingId === f.id}
                                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                                        <!-- svelte-ignore a11y-no-static-element-interactions -->
                                        <div on:click|stopPropagation>
                                            <FindingChat finding={f} />
                                        </div>
                                    {/if}
                                </div>
                            {/each}
                        {/if}
                    </div>
                </div>
            {:else}
                <!-- Tab Content 2: Logs inside Column 3 -->
                <div class="tab-content" style="display: flex; flex-direction: column; overflow: hidden; background-color: #05070c; height: 100%;">
                    <div class="console-header" style="border-top: none; background-color: #0b0f19; padding: 12px 20px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; color: var(--text-muted); font-size: 0.75rem; flex-shrink: 0;">
                        <span>Execution Stream</span>
                        <span>{$consoleStatusMap.editor}</span>
                    </div>
                    <div class="console-log" id="editor-console-log" style="flex: 1; overflow-y: auto; padding: 20px; white-space: pre-wrap; word-break: break-all; color: #10b981; line-height: 1.6; font-family: 'Fira Code', monospace; font-size: 0.85rem;">
                        {$consoleLogMap.editor}
                    </div>
                </div>
            {/if}
        </div>
    </div>
</div>

<!-- ================= MODALS ================= -->

<!-- Confirm Apply Modal -->
{#if showApplyModal}
    <div class="modal-overlay active">
        <div class="modal">
            <h3>変更を小説に反映しますか？</h3>
            <p>採用マークした指摘事項を小説テキストに適用します。適用前にバックアップファイルが自動的に作成されます。</p>
            <div class="modal-buttons">
                <button class="btn-secondary" on:click={() => showApplyModal = false}>キャンセル</button>
                <button class="btn-primary" on:click={handleApplyFindings}>反映を実行</button>
            </div>
        </div>
    </div>
{/if}

<!-- Apply Progress Modal -->
{#if showApplyProgressModal}
    <div class="modal-overlay active">
        <div class="modal" style="max-width: 800px; width: 90%; text-align: left;">
            <h3>小説への反映処理を実行中</h3>
            <p style="margin-bottom: 12px;">指摘事項の自動反映スクリプトを実行しています。LLMによる文章生成やテキスト置換のログが以下にリアルタイム表示されます。</p>
            
            <div class="console-container" style="margin-top: 16px; margin-bottom: 16px;">
                <div class="console-header">
                    <span>Apply Findings Console</span>
                    <span>{applyConsoleStatus}</span>
                </div>
                <div class="console-log" id="apply-progress-console-log" style="height: 300px; overflow-y: auto; font-family: 'Fira Code', monospace; font-size: 0.85rem; background-color: #0f172a; color: #f8fafc; padding: 12px; border-radius: 8px; white-space: pre-wrap; word-break: break-all;">
                    {applyConsoleLog}
                </div>
            </div>
            
            <div class="modal-buttons" style="justify-content: flex-end;">
                <button class="btn-primary" on:click={closeApplyProgress} disabled={applyConsoleStatus === 'RUNNING'}>
                    完了してエディタに戻る
                </button>
            </div>
        </div>
    </div>
{/if}
