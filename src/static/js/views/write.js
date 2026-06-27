import { state } from '../state.js';
import { startEventStream, showToast } from '../utils.js';
import { loadDashboardData } from './dashboard.js';

export async function loadSourcesForWrite() {
    const overlay = document.getElementById('write-loading-overlay');
    if (overlay) {
        overlay.classList.add('active');
    }
    try {
        // Load sources
        const response = await fetch('/api/sync/status');
        const data = await response.json();
        
        const selects = [
            'write-plot',
            'write-policy-global',
            'write-policy-chapter',
            'write-character'
        ];
        
        selects.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            
            // Keep the first default option
            el.innerHTML = '<option value="">(デフォルト/自動解決)</option>';
            
            data.sources.forEach(src => {
                const opt = document.createElement('option');
                opt.value = src.name;
                opt.textContent = src.name;
                el.appendChild(opt);
            });
        });

        // Load models
        const modelRes = await fetch('/api/models');
        const modelData = await modelRes.json();
        const modelSelects = [
            document.getElementById('write-model'),
            document.getElementById('review-model')
        ];
        modelSelects.forEach(modelSelect => {
            if (modelSelect && modelData.models) {
                modelSelect.innerHTML = '';
                modelData.models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    // Select Flash High as default
                    if (m.includes('High') || m.includes('Flash (High)')) {
                        opt.selected = true;
                    }
                    modelSelect.appendChild(opt);
                });
            }
        });

        // Restore values from localStorage and attach event listeners to save changes
        const fields = [
            'write-episode',
            'write-title',
            'write-model',
            'write-plot',
            'write-policy-global',
            'write-policy-chapter',
            'write-character',
            'review-model'
        ];

        fields.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;

            // Restore from localStorage
            const savedVal = localStorage.getItem(id);
            if (savedVal !== null) {
                el.value = savedVal;
            }

            // Bind change listener for saving
            if (!el.dataset.listenerRegistered) {
                el.dataset.listenerRegistered = 'true';
                const saveHandler = () => {
                    localStorage.setItem(id, el.value);
                };
                el.addEventListener('change', saveHandler);
                if (el.tagName === 'INPUT') {
                    el.addEventListener('input', saveHandler);
                }
            }
        });

    } catch (err) {
        console.error('Failed to load sources for write:', err);
    } finally {
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
}

export function runAiWriting() {
    const epInput = document.getElementById('write-episode').value.trim();
    if (!epInput) {
        alert('執筆する話を入力してください (例: 第1話)');
        return;
    }

    const titleVal = document.getElementById('write-title').value.trim();
    const modelVal = document.getElementById('write-model').value;
    const plotVal = document.getElementById('write-plot').value;
    const policyGlobalVal = document.getElementById('write-policy-global').value;
    const policyChapterVal = document.getElementById('write-policy-chapter').value;
    const characterVal = document.getElementById('write-character').value;
    const stepByStepVal = document.getElementById('write-step-by-step').checked;
    const selfCheckVal = document.getElementById('write-self-check').checked;

    const btn = document.getElementById('btn-run-write');
    if (btn) btn.disabled = true;

    let url = `/api/stream/write?episode=${encodeURIComponent(epInput)}`;
    if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
    if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
    if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
    if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
    if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
    if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;
    if (stepByStepVal) url += `&step_by_step=true`;
    if (selfCheckVal) url += `&self_check=true`;

    startEventStream(url, 'write-console-log', 'write-console-status', (success) => {
        if (btn) btn.disabled = false;
        if (success) {
            showToast('AI執筆が完了しました');
            loadDashboardData();
        } else {
            showToast('執筆中にエラーが発生しました');
        }
    });
}

export async function copyWritingPrompt() {
    const epInput = document.getElementById('write-episode').value.trim();
    if (!epInput) {
        alert('執筆する話を入力してください (例: 第1話)');
        return;
    }

    const titleVal = document.getElementById('write-title').value.trim();
    const modelVal = document.getElementById('write-model').value;
    const plotVal = document.getElementById('write-plot').value;
    const policyGlobalVal = document.getElementById('write-policy-global').value;
    const policyChapterVal = document.getElementById('write-policy-chapter').value;
    const characterVal = document.getElementById('write-character').value;

    const btn = document.getElementById('btn-copy-prompt');
    const writeBtn = document.getElementById('btn-run-write');
    if (btn) btn.disabled = true;
    if (writeBtn) writeBtn.disabled = true;

    // Show loading overlay
    const overlay = document.getElementById('write-loading-overlay');
    const loadingText = overlay ? overlay.querySelector('.view-loading-text') : null;
    const originalText = loadingText ? loadingText.textContent : '';
    if (loadingText) loadingText.textContent = 'プロンプト生成中...';
    if (overlay) overlay.classList.add('active');

    try {
        let url = `/api/write/prompt?episode=${encodeURIComponent(epInput)}`;
        if (modelVal) url += `&model=${encodeURIComponent(modelVal)}`;
        if (titleVal) url += `&novel_title=${encodeURIComponent(titleVal)}`;
        if (plotVal) url += `&plot=${encodeURIComponent(plotVal)}`;
        if (policyGlobalVal) url += `&policy_global=${encodeURIComponent(policyGlobalVal)}`;
        if (policyChapterVal) url += `&policy_chapter=${encodeURIComponent(policyChapterVal)}`;
        if (characterVal) url += `&character=${encodeURIComponent(characterVal)}`;

        const response = await fetch(url);
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'プロンプト生成に失敗しました');
        }

        const data = await response.json();
        await navigator.clipboard.writeText(data.prompt);
        showToast('プロンプトをクリップボードにコピーしました');
    } catch (err) {
        console.error('Failed to copy prompt:', err);
        showToast(`エラー: ${err.message}`);
    } finally {
        if (btn) btn.disabled = false;
        if (writeBtn) writeBtn.disabled = false;
        if (loadingText) loadingText.textContent = originalText;
        if (overlay) overlay.classList.remove('active');
    }
}
