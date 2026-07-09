<script>
    import { onMount } from 'svelte';
    import { isRunningProcess, consoleLogMap, consoleStatusMap } from '../store.js';
    import { startEventStream, showToast, initPanelResizer } from '../utils.js';
    import { withFreshToken } from '../lib/apiClient.js';

    let plots = [];
    let selectedPlotFile = localStorage.getItem('plotCreateSelectedFile') || '';
    let plotContent = 'プロットファイルを選択するとプレビューが表示されます。';
    let plotTitle = '-';
    let hasFindings = false;
    let loadingPlots = true;

    let draftContent = '';
    let draftName = '';
    let hasDraft = false;

    // Settings
    let selectedModel = 'Gemini 3.5 Flash (High)';
    const models = [
        'Gemini 3.5 Flash (High)',
        'Gemini 3.5 Flash (Medium)',
        'Gemini 3.5 Flash (Low)'
    ];

    let mode = 'expand'; // 'expand' | 'revise'
    let focusInstructions = '';

    // Right panel state
    let showConsole = false;
    let rightPanelMode = 'preview'; // 'preview' or 'console'
    let previewTab = 'original'; // 'original' or 'draft'
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
                plotContent = data.content || '内容が空です。';
                hasFindings = (data.findings || []).length > 0;
                if (!hasFindings && mode === 'revise') {
                    mode = 'expand';
                }
            }
        } catch (err) {
            console.error(err);
            showToast('プロット詳細の取得に失敗しました。');
        }
        await loadDraft(filename);
    }

    async function loadDraft(filename) {
        hasDraft = false;
        draftContent = '';
        draftName = '';
        try {
            const response = await fetch(`/api/plot/draft?file=${encodeURIComponent(filename)}`);
            if (response.ok) {
                const data = await response.json();
                draftName = data.draft_name;
                draftContent = data.content || '';
                hasDraft = true;
            }
        } catch (err) {
            console.error(err);
        }
    }

    function selectPlot(filename) {
        selectedPlotFile = filename;
        localStorage.setItem('plotCreateSelectedFile', filename);
        loadPlotDetails(filename);
        previewTab = 'original';
        rightPanelMode = 'preview';
        showConsole = true;
    }

    async function runPlotCreate() {
        if (!selectedPlotFile) {
            alert('プロットファイルを選択してください');
            return;
        }
        if (mode === 'revise' && !hasFindings) {
            showToast('このプロットにはまだ統合済みの指摘事項がありません。');
            return;
        }

        rightPanelMode = 'console';
        showConsole = true;

        const endpoint = mode === 'revise' ? 'plot_revise' : 'plot_expand';
        let url = `/api/stream/${endpoint}?file=${encodeURIComponent(selectedPlotFile)}`;
        if (selectedModel) {
            url += `&model=${encodeURIComponent(selectedModel)}`;
        }
        if (mode === 'expand' && focusInstructions.trim()) {
            url += `&focus=${encodeURIComponent(focusInstructions.trim())}`;
        }

        const freshUrl = await withFreshToken(url);
        startEventStream(freshUrl, 'plot_create', async (success) => {
            if (success) {
                showToast('プロットドラフトの生成が正常に完了しました');
                await loadDraft(selectedPlotFile);
                previewTab = 'draft';
                rightPanelMode = 'preview';
            } else {
                showToast('プロットドラフトの生成中にエラーが発生しました。');
            }
        });
    }

    function toggleConsoleView() {
        showConsole = !showConsole;
    }

    onMount(() => {
        loadPlots();
        if (resizerEl && rightPanelEl) {
            initPanelResizer(resizerEl, rightPanelEl);
        }
    });
</script>

<div class="view-content split-view-content active" id="view-plot_create">
    <div class="split-container">
        <!-- 左ペイン: 設定・操作 -->
        <div class="left-panel">
            <div class="left-panel-content">
                <div class="view-title-area">
                    <h2>🪄 プロット作成</h2>
                    <p>選択したプロットの肉付け、またはプロットレビューで検出された指摘事項を反映した改稿を行い、ドラフトを生成します。</p>
                </div>

                <div class="card" style="margin-bottom: 20px; background: rgba(255,193,7,0.06); border: 1px solid rgba(255,193,7,0.3);">
                    <p style="margin: 0; font-size: 0.85rem; color: var(--text-muted);" id="plot-create-source-warning">
                        ⚠️ 生成されたドラフトは <code>data/results/</code> 配下に保存されるのみで、<code>data/sources/</code> へは自動反映されません。設定資料への昇格は手動で行ってください。
                    </p>
                </div>

                <!-- 設定カード -->
                <div class="card" style="margin-bottom: 20px;">
                    <h3>生成パラメーター設定</h3>
                    <div class="form-grid" style="margin-bottom: 16px;">
                        <div class="form-group">
                            <label for="plot-create-model">使用するAIモデル</label>
                            <select id="plot-create-model" bind:value={selectedModel}>
                                {#each models as m}
                                    <option value={m}>{m}</option>
                                {/each}
                            </select>
                        </div>
                    </div>

                    <h3>実行モード</h3>
                    <div class="form-group" style="margin-bottom: 16px; display: flex; gap: 8px;">
                        <button
                            class="filter-btn {mode === 'expand' ? 'active' : ''}"
                            id="plot-create-mode-expand"
                            on:click={() => (mode = 'expand')}
                        >
                            🪄 肉付けする
                        </button>
                        <button
                            class="filter-btn {mode === 'revise' ? 'active' : ''}"
                            id="plot-create-mode-revise"
                            disabled={!hasFindings}
                            title={hasFindings ? '' : 'このプロットには統合済みの指摘事項がありません'}
                            on:click={() => hasFindings && (mode = 'revise')}
                        >
                            🔧 指摘を反映して改稿する
                        </button>
                    </div>

                    {#if mode === 'expand'}
                        <div class="form-group" style="margin-bottom: 16px;">
                            <label for="plot-create-focus">肉付けの方向性（任意）</label>
                            <textarea
                                id="plot-create-focus"
                                rows="4"
                                placeholder="例: 主人公の内面描写を厚くしてほしい、対立構造を強調してほしい、など"
                                bind:value={focusInstructions}
                            ></textarea>
                        </div>
                    {/if}

                    <h3>対象のプロットファイルを選択</h3>
                    <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center;">
                        <button class="btn-primary" id="btn-run-plot-create" disabled={$isRunningProcess} on:click={runPlotCreate}>
                            {$isRunningProcess ? '🪄 生成実行中...' : '🪄 ドラフトを生成'}
                        </button>
                        <button class="console-toggle-btn" on:click={toggleConsoleView}>
                            {showConsole ? '🖥️ コンソール非表示' : '🖥️ コンソール表示'}
                        </button>
                    </div>
                    <div class="form-group">
                        <div class="draft-cards-container" id="plot-create-cards-container">
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
            </div>
        </div>

        <!-- 右ペイン: プレビュー＆リアルタイムコンソール -->
        <div class="right-panel {showConsole ? 'show' : ''}" bind:this={rightPanelEl}>
            {#if rightPanelMode === 'preview'}
                <div class="console-header" id="plot_create-preview-header">
                    <div style="display: flex; gap: 8px;">
                        <button
                            class="filter-btn {previewTab === 'original' ? 'active' : ''}"
                            id="plot-create-tab-original"
                            on:click={() => (previewTab = 'original')}
                        >
                            📄 元プロット
                        </button>
                        <button
                            class="filter-btn {previewTab === 'draft' ? 'active' : ''}"
                            id="plot-create-tab-draft"
                            disabled={!hasDraft}
                            on:click={() => hasDraft && (previewTab = 'draft')}
                        >
                            ✨ 生成ドラフト
                        </button>
                    </div>
                    <span style="font-size: 0.8rem; color: var(--text-muted)">{previewTab === 'original' ? plotTitle : (draftName || '未生成')}</span>
                </div>
                <div id="plot-create-preview-body" style="flex: 1; padding: 20px; overflow-y: auto; white-space: pre-wrap; font-family: 'Sawarabi Mincho', serif; line-height: 1.8; color: #cbd5e1; font-size: 0.95rem; background-color: #0b0f19;">
                    {#if previewTab === 'original'}
                        {plotContent}
                    {:else if hasDraft}
                        {draftContent}
                    {:else}
                        まだドラフトは生成されていません。
                    {/if}
                </div>
            {:else}
                <div class="console-header" id="plot_create-console-header">
                    <span>Plot Create Pipeline Console</span>
                    <span>{$consoleStatusMap.plot_create}</span>
                </div>
                <div class="console-log" id="plot_create-console-log">{$consoleLogMap.plot_create}</div>
            {/if}
        </div>

        <!-- ドラッグリサイザー -->
        <div class="resizer-bar" bind:this={resizerEl}></div>
    </div>
</div>
