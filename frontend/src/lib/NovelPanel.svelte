<script>
    import { createEventDispatcher } from 'svelte';
    import { 
        selectedNovelFile, 
        novelLines, 
        activeHighlightLine,
        novelFilename 
    } from '../store.js';

    const dispatch = createEventDispatcher();

    export let editMode = false;
    export let editedText = '';
    export let findingsByLine = {};

    function isLogicCategory(category) {
        const cat = String(category).toLowerCase();
        return cat.includes('ロジック') || cat.includes('設定') || cat.includes('矛盾') || cat.includes('伏線') || cat.includes('整合性') || cat.includes('logic');
    }

    function handleLineClick(lineNo, lineFindings) {
        const firstFindingId = (lineFindings && lineFindings.length > 0) ? lineFindings[0].id : null;
        dispatch('line-click', { lineNo, firstFindingId });
    }
</script>

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
                <button class="btn-secondary btn-sm" on:click={() => dispatch('toggle-edit')} style="padding: 4px 8px; font-size: 0.75rem;">
                    {editMode ? '❌ キャンセル' : '📝 直接編集'}
                </button>
                {#if editMode}
                    <button class="btn-primary btn-sm" on:click={() => dispatch('save-novel')} style="padding: 4px 8px; font-size: 0.75rem;">
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
                            on:click={() => hasFindings && handleLineClick(lineNo, lineFindings)}
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
