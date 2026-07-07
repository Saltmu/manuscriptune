<script>
    import { onMount } from 'svelte';
    import { activeView, selectedNovelFile, isRunningProcess } from './store.js';
    import { showToast } from './utils.js';
    import { apiFetch, ensureApiKey } from './lib/apiClient.js';
    
    // Import views
    import Dashboard from './views/Dashboard.svelte';
    import Sync from './views/Sync.svelte';
    import PlotReview from './views/PlotReview.svelte';
    import Editor from './views/Editor.svelte';
    import Settings from './views/Settings.svelte';
    import ReviewHistory from './views/ReviewHistory.svelte';

    let novelTitle = '重天の調律師';
    let showShutdownModal = false;

    // Handle hash change routing
    function parseHash() {
        const hash = window.location.hash || '#/dashboard';
        const cleanHash = hash.startsWith('#/') ? hash.substring(2) : (hash.startsWith('#') ? hash.substring(1) : hash);
        const parts = cleanHash.split('/');
        const view = parts[0] || 'dashboard';
        const file = parts[1] ? decodeURIComponent(parts[1]) : null;
        return { view, file };
    }

    async function handleRouting() {
        if ($isRunningProcess) {
            showToast('プロセス実行中は画面を切り替えられません。');
            return;
        }

        const { view, file } = parseHash();
        const validViews = ['dashboard', 'sync', 'editor', 'plot_review', 'review_history', 'settings'];
        if (!validViews.includes(view)) {
            window.location.hash = '#/dashboard';
            return;
        }

        activeView.set(view);
        if (file) {
            selectedNovelFile.set(file);
        }
    }

    function switchView(viewName) {
        if ($isRunningProcess) {
            showToast('プロセス実行中は画面を切り替えられません。');
            return;
        }
        activeView.set(viewName);
        if (viewName === 'editor' && $selectedNovelFile) {
            window.location.hash = `#/editor/${encodeURIComponent($selectedNovelFile)}`;
        } else {
            window.location.hash = `#/${viewName}`;
        }
    }

    async function loadProjectConfig() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const data = await response.json();
                if (data.novel_title) {
                    novelTitle = data.novel_title;
                }
                if (data.initial_novel && !$selectedNovelFile) {
                    selectedNovelFile.set(data.initial_novel);
                }
            }
        } catch (err) {
            console.error('Failed to load project config:', err);
        }
    }

    async function executeGlobalShutdown() {
        showShutdownModal = false;
        try {
            await apiFetch('/api/shutdown', { method: 'POST' });
            window.close();
            document.body.innerHTML = `<div style="display:flex; justify-content:center; align-items:center; height:100vh; font-size:1.2rem; color:var(--text-muted)">サーバーを停止しました。ブラウザタブを閉じてください。</div>`;
        } catch (err) {
            console.error(err);
            window.close();
        }
    }

    onMount(() => {
        // 起動時にAPIトークンが未キャッシュなら自己発行しておく(非同期・非ブロッキング)
        ensureApiKey().catch(err => console.error('Failed to self-issue API token:', err));

        window.addEventListener('hashchange', handleRouting);
        loadProjectConfig();
        
        // Initial route handling
        const { file } = parseHash();
        if (file) {
            selectedNovelFile.set(file);
        }
        handleRouting();

        // Load settings title from localStorage on start
        const savedTitle = localStorage.getItem('settings-title');
        if (savedTitle) {
            novelTitle = savedTitle;
        }

        return () => {
            window.removeEventListener('hashchange', handleRouting);
        };
    });
</script>

<!-- Top Navigation Header -->
<header>
    <div class="brand">
        <h1 id="novel-title-display">{novelTitle}</h1>
        <p>AI Writing & Review Platform</p>
    </div>
    <ul class="nav-links">
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'dashboard' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('dashboard')}>
                📊 ダッシュボード
            </a>
        </li>
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'sync' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('sync')}>
                🔄 設定資料同期
            </a>
        </li>
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'plot_review' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('plot_review')}>
                🗺️ プロットレビュー
            </a>
        </li>
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'editor' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('editor')}>
                📝 執筆・校閲エディタ
            </a>
        </li>
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'review_history' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('review_history')}>
                📜 レビュー履歴
            </a>
        </li>
        <!-- svelte-ignore a11y-invalid-attribute -->
        <li>
            <a class="nav-item {$activeView === 'settings' ? 'active' : ''}" href="javascript:void(0)" on:click={() => switchView('settings')}>
                ⚙️ 設定
            </a>
        </li>
    </ul>
    <div class="sidebar-footer">
        <span style="margin-right: 12px;">v1.1 (Svelte)</span>
        <button class="btn-secondary btn-sm" on:click={() => showShutdownModal = true}>終了</button>
    </div>
</header>

<!-- Main content area switching based on activeView store -->
<main>
    {#if $activeView === 'dashboard'}
        <Dashboard />
    {:else if $activeView === 'sync'}
        <Sync />
    {:else if $activeView === 'plot_review'}
        <PlotReview />
    {:else if $activeView === 'editor'}
        <Editor />
    {:else if $activeView === 'review_history'}
        <ReviewHistory />
    {:else if $activeView === 'settings'}
        <Settings />
    {/if}
</main>

<!-- Common Global Modals -->

<!-- Confirm Global Shutdown Modal -->
{#if showShutdownModal}
    <div class="modal-overlay active">
        <div class="modal">
            <h3>Manuscriptune を終了しますか？</h3>
            <p>サーバーをシャットダウンし、ブラウザセッションを終了します。保存された採用マーク情報はYAMLファイルに残ります。</p>
            <div class="modal-buttons">
                <button class="btn-secondary" on:click={() => showShutdownModal = false}>キャンセル</button>
                <button class="btn-primary" style="background-color: var(--severity-high);" on:click={executeGlobalShutdown}>
                    終了する
                </button>
            </div>
        </div>
    </div>
{/if}

<!-- Toast Element -->
<div class="toast" id="toast">保存しました</div>

<style>
    /* Use app.css global styles */
</style>
