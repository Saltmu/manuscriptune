<script>
    import { createEventDispatcher } from 'svelte';

    const dispatch = createEventDispatcher();

    export let showApplyModal = false;
    export let showApplyProgressModal = false;
    export let showRewriteConfirmModal = false;
    export let pendingRewriteEpisode = null;
    export let applyConsoleStatus = 'READY';
    export let applyConsoleLog = '--- 待機中 ---';
</script>

<!-- Confirm Apply Modal -->
{#if showApplyModal}
    <div class="modal-overlay active">
        <div class="modal">
            <h3>変更を小説に反映しますか？</h3>
            <p>採用マークした指摘事項を小説テキストに適用します。適用前にバックアップファイルが自動的に作成されます。</p>
            <div class="modal-buttons">
                <button class="btn-secondary" on:click={() => dispatch('close-apply-modal')}>キャンセル</button>
                <button class="btn-primary" on:click={() => dispatch('execute-apply')}>反映を実行</button>
            </div>
        </div>
    </div>
{/if}

<!-- Confirm Rewrite Modal -->
{#if showRewriteConfirmModal}
    <div class="modal-overlay active">
        <div class="modal">
            <h3>「{pendingRewriteEpisode?.title}」を再執筆しますか？</h3>
            <p>AIによって本文が新しく生成し直され、現在の本文はレビュー結果ごと履歴（history）に自動退避されたうえで置き換えられます。処理には時間がかかる場合があります。</p>
            <div class="modal-buttons">
                <button class="btn-secondary" on:click={() => dispatch('close-rewrite-modal')}>キャンセル</button>
                <button class="btn-primary" on:click={() => dispatch('confirm-rewrite')}>再執筆を実行</button>
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
                <button class="btn-primary" on:click={() => dispatch('close-apply-progress')} disabled={applyConsoleStatus === 'RUNNING'}>
                    完了してエディタに戻る
                </button>
            </div>
        </div>
    </div>
{/if}
