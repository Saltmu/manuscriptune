<script>
    import { createEventDispatcher } from 'svelte';
    import { selectedNovelFile, findings } from '../store.js';
    import { showToast } from '../utils.js';

    export let finding;
    export let novelName = "";

    const dispatch = createEventDispatcher();
    let messageInput = "";
    let isSending = false;
    let chatContainer;

    // Auto-scroll to bottom of chat
    $: if (finding && finding.discussion && chatContainer) {
        setTimeout(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }, 50);
    }

    async function handleSendMessage() {
        if (!messageInput.trim() || isSending) return;

        const currentMsg = messageInput;
        messageInput = "";
        isSending = true;

        // Optimistically add user message to local UI
        const tempMsg = { role: "user", content: currentMsg };
        if (!finding.discussion) {
            finding.discussion = [];
        }
        finding.discussion = [...finding.discussion, tempMsg];

        try {
            const res = await fetch("/api/findings/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    novel_name: novelName || $selectedNovelFile,
                    finding_id: finding.id,
                    message: currentMsg
                })
            });

            if (!res.ok) {
                throw new Error("サーバーとの通信に失敗しました。");
            }

            const data = await res.json();
            if (data.status === "success") {
                // Update finding locally
                finding.discussion = [
                    ...finding.discussion.slice(0, -1), // Remove temporary message
                    { role: "user", content: currentMsg },
                    { role: "assistant", content: data.reply }
                ];
                
                if (data.source_suggestion) {
                    finding.source_suggestion = data.source_suggestion;
                } else {
                    delete finding.source_suggestion;
                }

                // Update the findings store to trigger reactivity in parent
                findings.update(items => {
                    return items.map(item => {
                        if (item.id === finding.id) {
                            return { ...finding };
                        }
                        return item;
                    });
                });
                dispatch('update', finding);
            } else {
                throw new Error(data.message || "チャットに失敗しました。");
            }
        } catch (error) {
            showToast(error.message);
            // Revert optimistic update
            finding.discussion = finding.discussion.slice(0, -1);
        } finally {
            isSending = false;
        }
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text);
        showToast("コピーしました！");
    }
</script>

<div class="chat-container">
    <div class="chat-header">
        <span class="badge">指摘 ID: {finding.id}</span>
        <h4>AI 編集者と対話</h4>
    </div>

    <!-- Chat Message List -->
    <div class="chat-messages" bind:this={chatContainer}>
        <div class="message system">
            <p><strong>指摘の原文:</strong> {finding.original}</p>
            <p><strong>分析:</strong> {finding.analysis}</p>
            <p><strong>当初の提案:</strong> {finding.suggestion}</p>
        </div>

        {#if finding.discussion && finding.discussion.length > 0}
            {#each finding.discussion as msg}
                <div class="message {msg.role}">
                    <div class="sender-label">
                        {msg.role === 'user' ? 'あなた' : 'AI'}
                    </div>
                    <div class="message-content">
                        {msg.content}
                    </div>
                </div>
            {/each}
        {/if}

        {#if isSending}
            <div class="message assistant loading">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
            </div>
        {/if}
    </div>

    <!-- Source Suggestion Card -->
    {#if finding.source_suggestion}
        <div class="source-suggestion-card">
            <h5>💡 設定資料（Google Drive）の修正提案</h5>
            <div class="suggestion-detail">
                <div class="item">
                    <span class="label">対象ファイル:</span>
                    <span class="value">{finding.source_suggestion.file}</span>
                </div>
                <div class="item">
                    <span class="label">修正前記述:</span>
                    <code class="value">{finding.source_suggestion.original}</code>
                    <button class="btn-copy" on:click={() => copyToClipboard(finding.source_suggestion.original)}>コピー</button>
                </div>
                <div class="item">
                    <span class="label">修正後記述:</span>
                    <code class="value">{finding.source_suggestion.replacement}</code>
                    <button class="btn-copy" on:click={() => copyToClipboard(finding.source_suggestion.replacement)}>コピー</button>
                </div>
                <div class="item">
                    <span class="label">変更理由:</span>
                    <span class="value">{finding.source_suggestion.reason}</span>
                </div>
            </div>
            <p class="warning-text">※上記の内容をGoogle Drive側のマスター設定ファイルに反映し、同期を実行してください。</p>
        </div>
    {/if}

    <!-- Chat Input Form -->
    <form class="chat-input-form" on:submit|preventDefault={handleSendMessage}>
        <input 
            type="text" 
            placeholder="修正の要望や相談を入力..." 
            bind:value={messageInput} 
            disabled={isSending}
        />
        <button type="submit" disabled={isSending || !messageInput.trim()}>
            {isSending ? '送信中...' : '送信'}
        </button>
    </form>
</div>

<style>
    .chat-container {
        display: flex;
        flex-direction: column;
        height: 100%;
        max-height: 550px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        overflow: hidden;
        margin-top: 15px;
        font-size: 0.9rem;
    }

    .chat-header {
        padding: 10px 15px;
        background: rgba(255, 255, 255, 0.05);
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .chat-header h4 {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 600;
        color: #e2e8f0;
    }

    .badge {
        background: #4f46e5;
        color: #fff;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: bold;
    }

    .chat-messages {
        flex: 1;
        padding: 15px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-height: 350px;
        min-height: 200px;
    }

    .message {
        max-width: 85%;
        padding: 10px 12px;
        border-radius: 8px;
        line-height: 1.4;
    }

    .message.system {
        align-self: center;
        background: rgba(255, 255, 255, 0.02);
        border: 1px dashed rgba(255, 255, 255, 0.15);
        color: #a0aec0;
        font-size: 0.85rem;
        max-width: 95%;
        width: 100%;
    }

    .message.system p {
        margin: 4px 0;
    }

    .message.user {
        align-self: flex-end;
        background: #3182ce;
        color: #fff;
        border-bottom-right-radius: 2px;
    }

    .message.assistant {
        align-self: flex-start;
        background: rgba(255, 255, 255, 0.08);
        color: #e2e8f0;
        border-bottom-left-radius: 2px;
    }

    .sender-label {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.5);
        margin-bottom: 4px;
        font-weight: 500;
    }

    .message.user .sender-label {
        color: rgba(255, 255, 255, 0.8);
        text-align: right;
    }

    .message-content {
        white-space: pre-wrap;
    }

    /* Loading dots animation */
    .message.loading {
        display: flex;
        gap: 4px;
        padding: 12px 16px;
    }

    .dot {
        width: 6px;
        height: 6px;
        background: #a0aec0;
        border-radius: 50%;
        animation: wave 1.3s infinite ease-in-out;
    }

    .dot:nth-child(2) { animation-delay: -1.1s; }
    .dot:nth-child(3) { animation-delay: -0.9s; }

    @keyframes wave {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-4px); }
    }

    /* Source Suggestion Card */
    .source-suggestion-card {
        margin: 10px 15px;
        padding: 12px;
        background: rgba(245, 158, 11, 0.08);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 6px;
    }

    .source-suggestion-card h5 {
        margin: 0 0 8px 0;
        color: #fbbf24;
        font-size: 0.85rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .suggestion-detail {
        display: flex;
        flex-direction: column;
        gap: 6px;
        font-size: 0.8rem;
    }

    .suggestion-detail .item {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .suggestion-detail .label {
        color: #a0aec0;
        min-width: 80px;
        font-weight: bold;
    }

    .suggestion-detail .value {
        color: #e2e8f0;
        flex: 1;
    }

    .suggestion-detail code.value {
        background: rgba(0, 0, 0, 0.2);
        padding: 2px 6px;
        border-radius: 4px;
        font-family: monospace;
        word-break: break-all;
    }

    .btn-copy {
        background: rgba(255, 255, 255, 0.1);
        border: none;
        color: #a0aec0;
        padding: 2px 6px;
        border-radius: 3px;
        cursor: pointer;
        font-size: 0.7rem;
        transition: background 0.2s;
    }

    .btn-copy:hover {
        background: rgba(255, 255, 255, 0.2);
        color: #fff;
    }

    .warning-text {
        margin: 8px 0 0 0;
        font-size: 0.75rem;
        color: #f87171;
    }

    /* Input Form */
    .chat-input-form {
        display: flex;
        padding: 10px 15px;
        background: rgba(255, 255, 255, 0.02);
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        gap: 10px;
    }

    .chat-input-form input {
        flex: 1;
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.15);
        color: #fff;
        padding: 8px 12px;
        border-radius: 6px;
        outline: none;
        font-size: 0.85rem;
    }

    .chat-input-form input:focus {
        border-color: #3182ce;
    }

    .chat-input-form button {
        background: #3182ce;
        color: #fff;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 600;
        transition: background 0.2s;
        font-size: 0.85rem;
    }

    .chat-input-form button:hover:not(:disabled) {
        background: #2b6cb0;
    }

    .chat-input-form button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
</style>
