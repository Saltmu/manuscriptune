<script>
    import { onMount } from 'svelte';
    import { selectedNovelFile, selectedReviewHistoryVersion } from '../store.js';
    import { showToast } from '../utils.js';

    let novels = [];
    let loadingNovels = true;
    let versions = [];
    let loadingVersions = false;
    let versionDetail = null;
    let loadingDetail = false;
    let lastLoadedFile = null;

    async function loadNovels() {
        try {
            const res = await fetch('/api/novels');
            if (res.ok) {
                const data = await res.json();
                novels = data.novels || [];
                if (!$selectedNovelFile && novels.length > 0) {
                    selectedNovelFile.set(novels[0].name);
                }
            } else {
                showToast('小説一覧の取得に失敗しました。');
            }
        } catch (err) {
            console.error('Failed to load novels:', err);
            showToast('小説一覧の取得に失敗しました。');
        } finally {
            loadingNovels = false;
        }
    }

    async function loadVersions(file) {
        loadingVersions = true;
        versions = [];
        versionDetail = null;
        selectedReviewHistoryVersion.set(null);
        try {
            const res = await fetch(`/api/review_history?file=${encodeURIComponent(file)}`);
            if (res.ok) {
                const data = await res.json();
                versions = data.versions || [];
            } else {
                showToast('レビュー履歴一覧の取得に失敗しました。');
            }
        } catch (err) {
            console.error('Failed to load review history versions:', err);
            showToast('レビュー履歴一覧の取得に失敗しました。');
        } finally {
            loadingVersions = false;
        }
    }

    async function selectVersion(version) {
        if (!$selectedNovelFile) return;
        selectedReviewHistoryVersion.set(version);
        loadingDetail = true;
        versionDetail = null;
        try {
            const res = await fetch(
                `/api/review_history/detail?file=${encodeURIComponent($selectedNovelFile)}&version=${encodeURIComponent(version)}`
            );
            if (res.ok) {
                versionDetail = await res.json();
            } else {
                showToast('レビュー履歴詳細の取得に失敗しました。');
            }
        } catch (err) {
            console.error('Failed to load review history detail:', err);
            showToast('レビュー履歴詳細の取得に失敗しました。');
        } finally {
            loadingDetail = false;
        }
    }

    function selectNovel(name) {
        selectedNovelFile.set(name);
    }

    function formatMtime(epochSeconds) {
        return new Date(epochSeconds * 1000).toLocaleString('ja-JP');
    }

    $: if ($selectedNovelFile && $selectedNovelFile !== lastLoadedFile) {
        lastLoadedFile = $selectedNovelFile;
        loadVersions($selectedNovelFile);
    }

    onMount(() => {
        loadNovels();
    });
</script>

<div class="view-content active" id="view-review_history">
    {#if loadingNovels}
        <div class="view-loading-overlay active" id="review-history-loading-overlay">
            <div class="spinner"></div>
            <div class="view-loading-text">小説一覧を読み込み中...</div>
        </div>
    {/if}

    <div class="scrollable-view">
        <div class="view-title-area">
            <h2>📜 レビュー履歴</h2>
            <p>過去に実行したレビューの一覧・詳細（レポート内容・指摘一覧）を閲覧します。</p>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <h3>対象の小説を選択</h3>
            <div class="draft-cards-container" id="review-history-novel-cards">
                {#if !loadingNovels && novels.length === 0}
                    <div style="text-align: center; color: var(--text-muted); padding: 20px;">小説ファイルが見つかりません。novels/ フォルダを確認してください。</div>
                {:else}
                    {#each novels as n}
                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                        <!-- svelte-ignore a11y-no-static-element-interactions -->
                        <div class="draft-selection-card {$selectedNovelFile === n.name ? 'active' : ''}" on:click={() => selectNovel(n.name)}>
                            <div class="draft-card-info">
                                <div class="draft-card-name">{n.name}</div>
                                <div class="draft-card-meta">
                                    <span>{(n.size / 1024).toFixed(1)} KB</span>
                                    <span>•</span>
                                    <span>{n.mtime}</span>
                                </div>
                            </div>
                        </div>
                    {/each}
                {/if}
            </div>
        </div>

        {#if $selectedNovelFile}
            <div class="card" style="margin-bottom: 20px;">
                <h3>レビュー履歴一覧 ({$selectedNovelFile})</h3>
                {#if loadingVersions}
                    <div style="text-align: center; color: var(--text-muted); padding: 20px;">読み込み中...</div>
                {:else if versions.length === 0}
                    <div style="text-align: center; color: var(--text-muted); padding: 20px;">この小説にはレビュー履歴がありません。</div>
                {:else}
                    <div class="draft-cards-container" id="review-history-version-cards">
                        {#each versions as v}
                            <!-- svelte-ignore a11y-click-events-have-key-events -->
                            <!-- svelte-ignore a11y-no-static-element-interactions -->
                            <div class="draft-selection-card {$selectedReviewHistoryVersion === v.version ? 'active' : ''}" on:click={() => selectVersion(v.version)}>
                                <div class="draft-card-info">
                                    <div class="draft-card-name">{v.version}</div>
                                    <div class="draft-card-meta">
                                        <span>{formatMtime(v.mtime)}</span>
                                        <span>•</span>
                                        <span>指摘 {v.findings_count} 件</span>
                                    </div>
                                </div>
                                <div class="draft-card-status">
                                    {#if v.has_report}
                                        <span class="badge badge-success">レポートあり</span>
                                    {:else}
                                        <span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">レポートなし</span>
                                    {/if}
                                </div>
                            </div>
                        {/each}
                    </div>
                {/if}
            </div>

            {#if loadingDetail}
                <div class="card">
                    <div style="text-align: center; color: var(--text-muted); padding: 20px;">詳細を読み込み中...</div>
                </div>
            {:else if versionDetail}
                <div class="card" style="margin-bottom: 20px;">
                    <h3>📄 レポート ({versionDetail.version})</h3>
                    {#if versionDetail.report}
                        <div style="white-space: pre-wrap; font-family: 'Sawarabi Mincho', serif; line-height: 1.8; color: #cbd5e1; font-size: 0.9rem; background-color: #0b0f19; border-radius: 8px; padding: 16px; max-height: 400px; overflow-y: auto;">{versionDetail.report}</div>
                    {:else}
                        <div style="text-align: center; color: var(--text-muted); padding: 12px;">レポートがありません。</div>
                    {/if}
                </div>

                <div class="card">
                    <h3>📋 指摘事項一覧 ({versionDetail.findings.length}件)</h3>
                    {#if versionDetail.findings.length === 0}
                        <div style="text-align: center; color: var(--text-muted); padding: 20px;">指摘事項はありません。</div>
                    {:else}
                        <div style="display: flex; flex-direction: column; gap: 12px; max-height: 450px; overflow-y: auto; padding-right: 4px;">
                            {#each versionDetail.findings as f}
                                <div class="finding-card">
                                    <div class="card-header" style="border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px; margin-bottom: 8px;">
                                        <div class="card-meta">
                                            {#if f.id}<span class="badge badge-id">{f.id}</span>{/if}
                                            {#if f.category}<span class="badge badge-category">{f.category}</span>{/if}
                                            {#if f.severity}<span class="badge badge-severity {String(f.severity).toLowerCase()}">{f.severity}</span>{/if}
                                        </div>
                                    </div>
                                    {#if f.location}
                                        <div class="card-location" style="margin-bottom: 8px; font-size: 0.85rem; color: var(--text-accent);">場所: {f.location}</div>
                                    {/if}
                                    {#if f.original}
                                        <div class="card-field" style="margin-bottom: 8px;">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">対象箇所</div>
                                            <div class="field-value" style="font-family: monospace; background: rgba(0,0,0,0.2); padding: 6px; border-radius: 4px; font-size: 0.85rem;">{f.original}</div>
                                        </div>
                                    {/if}
                                    {#if f.analysis}
                                        <div class="card-field" style="margin-bottom: 8px;">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">分析</div>
                                            <div class="field-value" style="font-size: 0.9rem; line-height: 1.5; color: #cbd5e1;">{f.analysis}</div>
                                        </div>
                                    {/if}
                                    {#if f.suggestion}
                                        <div class="card-field">
                                            <div class="field-label" style="font-size: 0.75rem; color: var(--text-success); text-transform: uppercase;">改善案</div>
                                            <div class="field-value" style="font-size: 0.9rem; line-height: 1.5; color: var(--text-success); font-weight: 500;">{f.suggestion}</div>
                                        </div>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    {/if}
                </div>
            {/if}
        {/if}
    </div>
</div>
