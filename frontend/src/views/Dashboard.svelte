<script>
    import { onMount } from 'svelte';
    import { activeView, selectedNovelFile, activeEditorTab } from '../store.js';
    import { showToast } from '../utils.js';

    let novels = [];
    let syncSources = [];
    let loadingNovels = true;
    let loadingSync = true;

    async function loadData() {
        try {
            // Load Novels
            const novelsRes = await fetch('/api/novels');
            if (novelsRes.ok) {
                const data = await novelsRes.json();
                novels = data.novels || [];
                
                // If there's a selected novel file from store, make sure it is in the list
                // or select the first one by default if none selected.
                if (novels.length > 0) {
                    if (!$selectedNovelFile) {
                        selectedNovelFile.set(novels[0].name);
                    }
                }
            }
        } catch (err) {
            console.error('Failed to load novels:', err);
        } finally {
            loadingNovels = false;
        }

        try {
            // Load Sync Status
            const syncRes = await fetch('/api/sync/status');
            if (syncRes.ok) {
                const syncData = await syncRes.json();
                syncSources = syncData.sources || [];
            }
        } catch (err) {
            console.error('Failed to load sync status:', err);
        } finally {
            loadingSync = false;
        }
    }

    function selectAndEditNovel(novelName) {
        selectedNovelFile.set(novelName);
        activeEditorTab.set('findings'); // Default tab when editing findings
        activeView.set('editor');
        window.location.hash = `#/editor/${encodeURIComponent(novelName)}`;
    }

    function handleCardClick(novelName) {
        selectedNovelFile.set(novelName);
    }

    function navigateToView(viewName, tabName = '') {
        if (tabName) {
            activeEditorTab.set(tabName);
        }
        activeView.set(viewName);
        
        if (viewName === 'editor' && $selectedNovelFile) {
            window.location.hash = `#/editor/${encodeURIComponent($selectedNovelFile)}`;
        } else {
            window.location.hash = `#/${viewName}`;
        }
    }

    onMount(() => {
        loadData();
    });
</script>

<div class="view-content active" id="view-dashboard">
    <div class="scrollable-view">
        <div class="view-title-area">
            <h2>ダッシュボード</h2>
            <p>執筆済みドラフトの管理、新規執筆、校閲ステータスの一覧。</p>
        </div>
        
        <div class="grid-3">
            <div class="card">
                <h3>Google Drive 同期状況</h3>
                <div id="drive-sync-status-area" style="font-size: 0.9rem; color: var(--text-muted); display:flex; flex-direction:column; gap:10px; min-height: 60px;">
                    {#if loadingSync}
                        読み込み中...
                    {:else if syncSources.length === 0}
                        <div>同期された設定資料はありません。</div>
                    {:else}
                        {#each syncSources as s}
                            <div style="display: flex; justify-content: space-between;">
                                <span>{s.name}</span>
                                <span style="font-size:0.8rem; color:var(--text-muted);">{s.last_updated}</span>
                            </div>
                        {/each}
                    {/if}
                </div>
                <button class="btn-secondary btn-sm" on:click={() => navigateToView('sync')}>同期画面へ</button>
            </div>
            
            <div class="card">
                <h3>AI小説執筆</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted);">
                    プロットに沿ったエピソードのドラフトをAIで自動生成します。
                </p>
                <button class="btn-primary btn-sm" on:click={() => navigateToView('editor', 'settings')}>執筆画面へ</button>
            </div>
            
            <div class="card">
                <h3>校閲・レビュー実行</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted);">
                    ドラフトの自動校閲、編集長AIによる指摘反映、校閲エディタでの推敲を行います。
                </p>
                <button class="btn-primary btn-sm" on:click={() => navigateToView('editor', 'settings')}>レビュー画面へ</button>
            </div>
        </div>

        <div class="card" style="margin-top: 24px;">
            <h3 style="margin-bottom: 16px;">📂 小説ドラフト一覧</h3>
            <div class="draft-cards-container" id="review-draft-cards-container">
                {#if loadingNovels}
                    読み込み中...
                {:else if novels.length === 0}
                    <div style="text-align: center; color: var(--text-muted); padding: 20px;">
                        小説が見つかりません。novels/ フォルダを確認してください。
                    </div>
                {:else}
                    {#each novels as n}
                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                        <div class="draft-selection-card {$selectedNovelFile === n.name ? 'active' : ''}" on:click={() => handleCardClick(n.name)}>
                            <div class="draft-card-info">
                                <div class="draft-card-name">{n.name}</div>
                                <div class="draft-card-meta">
                                    <span>{(n.size / 1024).toFixed(1)} KB</span>
                                    <span>•</span>
                                    <span>{n.mtime}</span>
                                </div>
                            </div>
                            <div class="draft-card-status">
                                {#if n.has_findings}
                                    <span class="badge badge-success">指摘あり</span>
                                {:else}
                                    <span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>
                                {/if}
                            </div>
                            {#if n.has_findings}
                                <button class="draft-card-action-btn" on:click|stopPropagation={() => selectAndEditNovel(n.name)}>
                                    📝 校閲する
                                </button>
                            {/if}
                        </div>
                    {/each}
                {/if}
            </div>
        </div>
    </div>
</div>
