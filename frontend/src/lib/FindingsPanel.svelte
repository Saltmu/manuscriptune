<script>
    import { createEventDispatcher } from 'svelte';
    import {
        activeEditorTab,
        activeCategoryFilter,
        activeSeverityFilter,
        activeDecisionFilter,
        findings,
        consoleLogMap,
        consoleStatusMap,
        activeHighlightLine
    } from '../store.js';
    import FindingChat from './FindingChat.svelte';

    const dispatch = createEventDispatcher();

    let activeChatFindingId = null;

    function toggleChat(findingId) {
        if (activeChatFindingId === findingId) {
            activeChatFindingId = null;
        } else {
            activeChatFindingId = findingId;
        }
    }

    function parseLineNumber(locationStr) {
        if (!locationStr) return null;
        const match = String(locationStr).match(/(\d+)/);
        return match ? parseInt(match[0], 10) : null;
    }

    function isLogicCategory(category) {
        const cat = String(category).toLowerCase();
        return cat.includes('ロジック') || cat.includes('設定') || cat.includes('矛盾') || cat.includes('伏線') || cat.includes('整合性') || cat.includes('logic');
    }

    function decisionOf(f) {
        if (f.accepted === 'y') return 'accepted';
        if (f.accepted === 'n') return 'dismissed';
        return 'undecided';
    }

    $: filteredFindings = $findings
        .filter(f => {
            const isLogic = isLogicCategory(f.category);
            if ($activeCategoryFilter === 'logic' && !isLogic) return false;
            if ($activeCategoryFilter === 'style' && isLogic) return false;
            if ($activeSeverityFilter !== 'all' && String(f.severity).toLowerCase() !== $activeSeverityFilter) return false;
            if ($activeDecisionFilter !== 'all' && decisionOf(f) !== $activeDecisionFilter) return false;
            return true;
        })
        .slice() // 元配列を破壊しないためコピーしてから sort
        .sort((a, b) => {
            const rank = { undecided: 0, accepted: 1, dismissed: 2 };
            return rank[decisionOf(a)] - rank[decisionOf(b)];
        });

    function handleCardClick(f) {
        const lineNo = parseLineNumber(f.location);
        dispatch('finding-card-click', { lineNo, findingId: f.id });
    }
</script>

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
                <button class="filter-btn {$activeDecisionFilter === 'all' ? 'active' : ''}" on:click={() => activeDecisionFilter.set('all')}>すべて</button>
                <button class="filter-btn df-undecided {$activeDecisionFilter === 'undecided' ? 'active' : ''}" on:click={() => activeDecisionFilter.set('undecided')}>未判断</button>
                <button class="filter-btn df-accepted {$activeDecisionFilter === 'accepted' ? 'active' : ''}" on:click={() => activeDecisionFilter.set('accepted')}>採用</button>
                <button class="filter-btn df-dismissed {$activeDecisionFilter === 'dismissed' ? 'active' : ''}" on:click={() => activeDecisionFilter.set('dismissed')}>見送り</button>
                <div style="width: 1px; height: 16px; background-color: var(--border-color); align-self: center; margin: 0 4px;"></div>
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
                        {@const decision = decisionOf(f)}

                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                        <div
                            class="finding-card {isLogic ? 'logic' : 'style'} {decision} {isCardHighlight ? 'active' : ''}"
                            id="finding-card-{f.id}"
                            on:click={() => handleCardClick(f)}
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
                                <span class="state-chip {decision}">
                                    {decision === 'accepted' ? '✓ 採用' : decision === 'dismissed' ? '見送り' : '⚠ 要判断'}
                                </span>
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
                                <button class="decision-btn accept {decision === 'accepted' ? 'active' : ''}"
                                    on:click={() => dispatch('toggle-decision', { findingId: f.id, val: 'y' })}>
                                    {decision === 'accepted' ? '✓ 採用中' : '採用する'}
                                </button>
                                <button class="decision-btn dismiss {decision === 'dismissed' ? 'active' : ''}"
                                    on:click={() => dispatch('toggle-decision', { findingId: f.id, val: 'n' })}>
                                    {decision === 'dismissed' ? '見送り中' : '見送る'}
                                </button>

                                <button class="filter-btn {activeChatFindingId === f.id ? 'active' : ''}" style="padding: 4px 8px; font-size: 0.75rem; margin-left: auto;" on:click={() => toggleChat(f.id)}>
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
