<script>
    import { onMount } from 'svelte';
    import { showToast } from '../utils.js';

    let loading = true;
    let sources = [];
    let models = [];

    // Local state bound to inputs
    let settingsTitle = '重天の調律師';
    let settingsModel = 'Gemini 3.5 Flash (High)';
    let settingsPolicyGlobal = '';
    let settingsPolicyChapter = '';
    let settingsCharacter = '';

    onMount(async () => {
        try {
            // Load sync status for policies and characters
            const response = await fetch('/api/sync/status');
            const data = await response.json();
            sources = data.sources || [];

            // Load models
            const modelRes = await fetch('/api/models');
            const modelData = await modelRes.json();
            models = modelData.models || [];
            
            // Set default selected model if not saved
            if (!localStorage.getItem('settings-model') && models.length > 0) {
                const defaultModel = models.find(m => m.includes('High') || m.includes('Flash (High)'));
                if (defaultModel) {
                    settingsModel = defaultModel;
                }
            }

            // Restore from localStorage
            settingsTitle = localStorage.getItem('settings-title') || '重天の調律師';
            settingsModel = localStorage.getItem('settings-model') || settingsModel;
            settingsPolicyGlobal = localStorage.getItem('settings-policy-global') || '';
            settingsPolicyChapter = localStorage.getItem('settings-policy-chapter') || '';
            settingsCharacter = localStorage.getItem('settings-character') || '';

        } catch (err) {
            console.error('Failed to load settings data:', err);
        } finally {
            loading = false;
        }
    });

    function handleSave() {
        localStorage.setItem('settings-title', settingsTitle);
        localStorage.setItem('settings-model', settingsModel);
        localStorage.setItem('settings-policy-global', settingsPolicyGlobal);
        localStorage.setItem('settings-policy-chapter', settingsPolicyChapter);
        localStorage.setItem('settings-character', settingsCharacter);

        // Update header novel title if element exists
        const titleEl = document.getElementById('novel-title-display');
        if (titleEl) titleEl.textContent = settingsTitle;

        showToast('設定を保存しました');
    }
</script>

<div class="view-content active" id="view-settings">
    {#if loading}
        <div class="view-loading-overlay active" id="settings-loading-overlay">
            <div class="spinner"></div>
            <div class="view-loading-text">設定読み込み中...</div>
        </div>
    {/if}
    
    <div class="scrollable-view">
        <div class="view-title-area">
            <h2>プロジェクト設定</h2>
            <p>小説執筆および校閲時に使用するAIモデルや参照するポリシーのデフォルト設定。</p>
        </div>

        <div class="card" style="max-width: 600px; padding: 24px; margin-top: 20px;">
            <div style="display: flex; flex-direction: column; gap: 20px;">
                <div class="form-group" style="display: flex; flex-direction: column; gap: 8px;">
                    <label for="settings-title" style="font-weight: 600; font-size: 0.9rem;">小説タイトル</label>
                    <input type="text" id="settings-title" bind:value={settingsTitle} placeholder="重天の調律師" style="padding: 10px 14px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.9rem;">
                </div>

                <div class="form-group" style="display: flex; flex-direction: column; gap: 8px;">
                    <label for="settings-model" style="font-weight: 600; font-size: 0.9rem;">使用するAIモデル</label>
                    <select id="settings-model" bind:value={settingsModel} style="padding: 10px 14px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.9rem;">
                        {#each models as m}
                            <option value={m}>{m}</option>
                        {/each}
                    </select>
                </div>

                <div class="form-group" style="display: flex; flex-direction: column; gap: 8px;">
                    <label for="settings-policy-global" style="font-weight: 600; font-size: 0.9rem;">全体執筆ポリシー</label>
                    <select id="settings-policy-global" bind:value={settingsPolicyGlobal} style="padding: 10px 14px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.9rem;">
                        <option value="">(デフォルト/自動解決)</option>
                        {#each sources as src}
                            <option value={src.name}>{src.name}</option>
                        {/each}
                    </select>
                </div>

                <div class="form-group" style="display: flex; flex-direction: column; gap: 8px;">
                    <label for="settings-policy-chapter" style="font-weight: 600; font-size: 0.9rem;">章執筆ポリシー</label>
                    <select id="settings-policy-chapter" bind:value={settingsPolicyChapter} style="padding: 10px 14px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.9rem;">
                        <option value="">(デフォルト/自動解決)</option>
                        {#each sources as src}
                            <option value={src.name}>{src.name}</option>
                        {/each}
                    </select>
                </div>

                <div class="form-group" style="display: flex; flex-direction: column; gap: 8px;">
                    <label for="settings-character" style="font-weight: 600; font-size: 0.9rem;">キャラクター概要</label>
                    <select id="settings-character" bind:value={settingsCharacter} style="padding: 10px 14px; background-color: #0b0f19; border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-main); font-size: 0.9rem;">
                        <option value="">(デフォルト/自動解決)</option>
                        {#each sources as src}
                            <option value={src.name}>{src.name}</option>
                        {/each}
                    </select>
                </div>

                <div style="margin-top: 10px;">
                    <button class="btn-primary" on:click={handleSave} style="padding: 10px 20px; font-size: 0.9rem; font-weight: 600;">設定を保存</button>
                </div>
            </div>
        </div>
    </div>
</div>
