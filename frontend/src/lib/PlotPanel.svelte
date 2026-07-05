<script>
    import { onMount, createEventDispatcher } from 'svelte';
    import { 
        selectedPlot, 
        selectedNovelFile, 
        isRunningProcess 
    } from '../store.js';
    import { showToast } from '../utils.js';

    const dispatch = createEventDispatcher();

    let plots = [];
    let chapters = [];
    let loadingPlots = true;
    let loadingEpisodes = false;

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

    onMount(() => {
        loadPlots();
    });

    // Public method to reload episode cards from parent
    export async function refreshEpisodes() {
        if ($selectedPlot) {
            await loadEpisodeCards($selectedPlot);
        }
    }
</script>

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
        <select 
            bind:value={$selectedPlot} 
            on:change={(e) => loadEpisodeCards(e.target.value)} 
            style="width: 100%; padding: 8px 12px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.85rem;"
        >
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
                    <div 
                        class="draft-selection-card {isActive ? 'active' : ''}" 
                        on:click={() => ep.novel_file ? dispatch('select-novel-file', ep.novel_file) : showToast('このエピソードはまだ執筆されていません。執筆ボタンを押してください。')}
                    >
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
                                <button class="draft-card-action-btn" on:click|stopPropagation={() => dispatch('run-write', ep.title)}>
                                    ✍️ 執筆する
                                </button>
                            {:else}
                                <button 
                                    class="draft-card-action-btn" 
                                    style="background-color: rgba(255,255,255,0.05); color: var(--text-main); border: 1px solid var(--border-color); flex: 1;" 
                                    on:click|stopPropagation={() => dispatch('open-rewrite', ep)}
                                >
                                    🔄 再執筆
                                </button>
                                <button 
                                    class="draft-card-action-btn" 
                                    style="flex: 1;" 
                                    on:click|stopPropagation={() => dispatch('run-review', ep.novel_file)}
                                >
                                    🔍 レビュー
                                </button>
                            {/if}
                        </div>
                        {#if ep.status === 'reviewed' && ep.findings_count > 0}
                            <button 
                                class="draft-card-action-btn" 
                                style="background-color: var(--logic-color); width: 100%;" 
                                on:click|stopPropagation={() => dispatch('show-findings', ep.novel_file)}
                            >
                                📋 指摘確認
                            </button>
                        {/if}
                    </div>
                {/each}
            {/each}
        {/if}
    </div>
</div>
