<script>
    import { onMount } from 'svelte';
    import { isRunningProcess, consoleLogMap, consoleStatusMap } from '../store.js';
    import { startEventStream, showToast, initPanelResizer } from '../utils.js';
    import { withFreshToken } from '../lib/apiClient.js';
    import FindingChat from '../lib/FindingChat.svelte';

    let plots = [];
    let selectedPlotFile = localStorage.getItem('selectedPlotFile') || '';
    let plotContent = 'プロットファイルを選択するとプレビューが表示されます。';
    let plotTitle = '-';
    let findings = [];
    let loadingPlots = true;
    let activeChatFindingId = null;

    function toggleChat(findingId) {
        if (activeChatFindingId === findingId) {
            activeChatFindingId = null;
        } else {
            activeChatFindingId = findingId;
        }
    }

    // Filters
    let severityFilter = 'all';
    let categoryFilter = 'all';
    let categories = [];

    // Settings
    let selectedModel = 'Gemini 3.5 Flash (High)';
    const models = [
        'Gemini 3.5 Flash (High)',
        'Gemini 3.5 Flash (Medium)',
        'Gemini 3.5 Flash (Low)'
    ];

    // Right Panel state
    let showConsole = false;
    let rightPanelMode = 'preview'; // 'preview' or 'console'
    let resizerEl;
    let rightPanelEl;

    async function loadPlots() {
        try {
            const res = await fetch('/api/plots');
            if (res.ok) {
                const data = await res.json();
                plots = data.plots || [];

                if (plots.length > 0) {
                    if (!selectedPlotFile || !plots.some(p => p.name === selectedPlotFile)) {
                        selectPlot(plots[0].name);
                    } else {
                        loadPlotDetails(selectedPlotFile);
                    }
                }
            }
        } catch (err) {
            console.error(err);
            showToast('プロット一覧の取得に失敗しました。');
        } finally {
            loadingPlots = false;
        }
    }

    async function loadPlotDetails(filename) {
        try {
            const response = await fetch(`/api/plot?file=${encodeURIComponent(filename)}`);
            if (response.ok) {
                const data = await response.json();
                plotTitle = data.plot_name;
                plotContent = data.content || "内容が空です。";
                findings = data.findings || [];

                // Extract unique categories
                const cats = new Set();
                findings.forEach(f => {
                    if (f.category) cats.add(f.category);
                });
                categories = Array.from(cats);
            }
        } catch (err) {
            console.error(err);
            showToast('プロット詳細の取得に失敗しました。');
        }
    }

    function selectPlot(filename) {
        selectedPlotFile = filename;
        localStorage.setItem('selectedPlotFile', filename);
        loadPlotDetails(filename);
        rightPanelMode = 'preview';
        showConsole = true; // Show preview
    }

    async function runPlotReview() {
        if (!selectedPlotFile) {
            alert('プロットファイルを選択してください');
            return;
        }

        rightPanelMode = 'console';
        showConsole = true;

        let url = `/api/stream/plot_review?file=${encodeURIComponent(selectedPlotFile)}`;
        if (selectedModel) {
            url += `&model=${encodeURIComponent(selectedModel)}`;
        }

        const freshUrl = await withFreshToken(url);
        startEventStream(freshUrl, 'plot_review', (success) => {
            if (success) {
                showToast('プロットレビューパイプラインが正常に完了しました');
                rightPanelMode = 'preview';
                loadPlots(); // Reload list and findings
            } else {
                showToast('プロットレビュー中にエラーが発生しました。');
            }
        });
    }

    function toggleConsoleView() {
        showConsole = !showConsole;
    }

    // Filter findings
    $: filteredFindings = findings.filter(f => {
        if (severityFilter !== 'all' && String(f.severity).toLowerCase() !== severityFilter) return false;
        if (categoryFilter !== 'all' && f.category !== categoryFilter) return false;
        return true;
    });

    onMount(() => {
        loadPlots();
        if (resizerEl && rightPanelEl) {
            initPanelResizer(resizerEl, rightPanelEl);
        }
    });
</script>

<div class="view-content split-view-content active" id="view-plot_review">
    <div class="split-container">
        <!-- 左ペイン: 設定・操作・指摘一覧 -->
        <div class="left-panel">
            <div class="left-panel-content">
                <div class="view-title-area">
                    <h2>🗺️ プロット構成レビュー</h2>
                    <p>プロット内のGMCOフレームワーク（目標・障害・葛藤・結果）の検証、および三幕構成や感情の波（山場）を監査し、構成上の弱点と具体的な改善案を提示します。</p>
                </div>

                <!-- 設定カード -->
                <div class="card" style="margin-bottom: 20px;">
                    <h3>校閲パラメーター設定</h3>
                    <div class="form-grid" style="margin-bottom: 16px;">
                        <div class="form-group">
                            <label for="plot-review-model">使用するAIモデル</label>
                            <select id="plot-review-model" bind:value={selectedModel}>
                                {#each models as m}
                                    <option value={m}>{m}</option>
                                {/each}
                            </select>
                        </div>
                    </div>

                    <h3>対象のプロットファイルを選択</h3>
                    <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center;">
                        <button class="btn-primary" id="btn-run-plot-review" disabled={$isRunningProcess} on:click={runPlotReview}>
                            {$isRunningProcess ? '🔍 レビュー実行中...' : '🔍 プロットレビューを実行'}
                        </button>
                        <button class="console-toggle-btn" on:click={toggleConsoleView}>
                            {showConsole ? '🖥️ コンソール非表示' : '🖥️ コンソール表示'}
                        </button>
                    </div>
                    <div class="form-group">
                        <div class="draft-cards-container" id="plot-cards-container">
                            {#if loadingPlots}
                                <div style="text-align: center; color: var(--text-muted); padding: 20px;">読み込み中...</div>
                            {:else if plots.length === 0}
                                <div style="text-align: center; color: var(--text-muted); padding: 20px;">プロットファイルが見つかりません。data/sources/ フォルダを確認してください。</div>
                            {:else}
                                {#each plots as p}
                                    <!-- svelte-ignore a11y-click-events-have-key-events -->
                                    <div class="draft-selection-card {selectedPlotFile === p.name ? 'active' : ''}" on:click={() => selectPlot(p.name)}>
                                        <div class="draft-card-info">
                                            <div class="draft-card-name">{p.name}</div>
                                            <div class="draft-card-meta">
                                                <span>{(p.size / 1024).toFixed(1)} KB</span>
                                                <span>•</span>
                                                <span>{p.mtime}</span>
                                            </div>
                                        </div>
                                        <div class="draft-card-status">
                                            {#if p.has_findings}
                                                <span class="badge badge-success">指摘あり</span>
                                            {:else}
                                                <span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    </div>
                </div>

                <!-- 指摘事項表示カード（レビュー完了後に表示） -->
                {#if findings.length > 0}
                    <div class="card" id="plot-findings-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <h3 style="margin: 0;">📋 検出された構成指摘事項 ({findings.length}件)</h3>
                        </div>

                        <!-- フィルタツールバー -->
                        <div class="filter-toolbar" style="margin-bottom: 16px; display: flex; gap: 12px; background: rgba(255,255,255,0.02); padding: 8px 12px; border-radius: 6px;">
                            <div class="form-group" style="margin: 0; flex: 1;">
                                <label for="plot-filter-severity" style="font-size: 0.75rem; margin-bottom: 4px;">重要度で絞り込み</label>
                                <select id="plot-filter-severity" bind:value={severityFilter} style="padding: 4px 8px; font-size: 0.85rem;">
                                    <option value="all">すべて表示</option>
                                    <option value="high">🚨 重大 (High)</option>
                                    <option value="medium">⚠️ 中程度 (Medium)</option>
                                    <option value="low">💡 軽微 (Low)</option>
                                    <option value="info">ℹ️ 参考 (Info)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin: 0; flex: 1;">
                                <label for="plot-filter-category" style="font-size: 0.75rem; margin-bottom: 4px;">カテゴリで絞り込み</label>
                                <select id="plot-filter-category" bind:value={categoryFilter} style="padding: 4px 8px; font-size: 0.85rem;">
                                    <option value="all">すべて表示</option>
                                    {#each categories as cat}
                                        <option value={cat}>{cat}</option>
                                    {/each}
                                </select>
                            </div>
                        </div>

                        <!-- 指摘リストコンテナ -->
                        <div id="plot-findings-list" style="display: flex; flex-direction: column; gap: 12px; max-height: 450px; overflow-y: auto; padding-right: 4px;">
                            {#if filteredFindings.length === 0}
                                <div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 0.9rem;">該当する指摘事項はありません</div>
                            {:else}
                                {#each filteredFindings as f}
                                    {@const isConflict = String(f.category).includes('対立') || String(f.category).includes('葛藤') || String(f.category).includes('GMCO')}
                                    <div class="finding-card {isConflict ? 'logic' : 'style'}" id="plot-finding-card-{f.id}">
                                        <div class="card-header" style="border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px; margin-bottom: 8px;">
                                            <div class="card-meta">
                                                <span class="badge badge-id">{f.id}</span>
                                                <span class="badge badge-category {isConflict ? 'logic' : 'style'}">{f.category}</span>
                                                <span class="badge badge-severity {String(f.severity).toLowerCase()}">{f.severity}</span>
                                            </div>
                                        </div>
                                        <div class="card-location" style="margin-bottom: 8px; font-size: 0.85rem; color: var(--text-accent);">場所: {f.location}</div>
                                        <div class="card-field" style="margin-bottom: 8px;">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">対象プロット記述</div>
                                            <div class="field-value original-text" style="font-family: monospace; background: rgba(0,0,0,0.2); padding: 6px; border-radius: 4px; font-size: 0.85rem;">{f.original}</div>
                                        </div>
                                        <div class="card-field" style="margin-bottom: 8px;">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">分析</div>
                                            <div class="field-value analysis-text" style="font-size: 0.9rem; line-height: 1.5; color: #cbd5e1;">{f.analysis}</div>
                                        </div>
                                        <div class="card-field">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-success); text-transform: uppercase;">構成改善案</div>
                                            <div class="field-value suggestion-text" style="font-size: 0.9rem; line-height: 1.5; color: var(--text-success); font-weight: 500;">{f.suggestion}</div>
                                        </div>

                                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                                        <!-- svelte-ignore a11y-no-static-element-interactions -->
                                        <div class="card-actions" style="margin-top: 12px; display: flex; gap: 8px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px;">
                                            <button class="filter-btn {activeChatFindingId === f.id ? 'active' : ''}" style="padding: 4px 8px; font-size: 0.75rem;" on:click={() => toggleChat(f.id)}>
                                                {activeChatFindingId === f.id ? '相談を閉じる' : '💬 AIと相談する'}
                                            </button>
                                        </div>

                                        {#if activeChatFindingId === f.id}
                                            <!-- svelte-ignore a11y-click-events-have-key-events -->
                                            <!-- svelte-ignore a11y-no-static-element-interactions -->
                                            <div on:click|stopPropagation>
                                                <FindingChat 
                                                    finding={f} 
                                                    novelName={selectedPlotFile}
                                                    on:update={(e) => {
                                                        findings = findings.map(item => item.id === e.detail.id ? e.detail : item);
                                                    }}
                                                />
                                            </div>
                                        {/if}
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    </div>
                {/if}
            </div>
        </div>

        <!-- 右ペイン: プレビュー＆リアルタイムコンソール -->
        <div class="right-panel {showConsole ? 'show' : ''}" bind:this={rightPanelEl}>
            {#if rightPanelMode === 'preview'}
                <div class="console-header" id="plot_review-preview-header">
                    <span>📄 プロット本文プレビュー: <span id="plot-preview-filename">{plotTitle}</span></span>
                    <span style="font-size: 0.8rem; color: var(--text-muted)">プレビュー表示中</span>
                </div>
                <div id="plot-preview-body" style="flex: 1; padding: 20px; overflow-y: auto; white-space: pre-wrap; font-family: 'Sawarabi Mincho', serif; line-height: 1.8; color: #cbd5e1; font-size: 0.95rem; background-color: #0b0f19;">
                    {plotContent}
                </div>
            {:else}
                <div class="console-header" id="plot_review-console-header">
                    <span>Plot Review Pipeline Console</span>
                    <span>{$consoleStatusMap.plot_review}</span>
                </div>
                <div class="console-log" id="plot_review-console-log">{$consoleLogMap.plot_review}</div>
            {/if}
        </div>

        <!-- ドラッグリサイザー -->
        <div class="resizer-bar" bind:this={resizerEl}></div>
    </div>
</div>
