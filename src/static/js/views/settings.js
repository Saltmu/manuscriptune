import { showToast } from '../utils.js';

export async function loadSettingsData() {
    const overlay = document.getElementById('settings-loading-overlay');
    if (overlay) {
        overlay.classList.add('active');
    }
    try {
        // Load sync status for policies and characters
        const response = await fetch('/api/sync/status');
        const data = await response.json();

        const policySelects = [
            'settings-policy-global',
            'settings-policy-chapter',
            'settings-character'
        ];

        policySelects.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;

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
        const modelSelect = document.getElementById('settings-model');
        if (modelSelect && modelData.models) {
            modelSelect.innerHTML = '';
            modelData.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m.includes('High') || m.includes('Flash (High)')) {
                    opt.selected = true;
                }
                modelSelect.appendChild(opt);
            });
        }

        // Restore values from localStorage
        const fields = [
            'settings-title',
            'settings-model',
            'settings-policy-global',
            'settings-policy-chapter',
            'settings-character'
        ];

        fields.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            const savedVal = localStorage.getItem(id);
            if (savedVal !== null) {
                el.value = savedVal;
            }
        });

    } catch (err) {
        console.error('Failed to load settings data:', err);
    } finally {
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
}

export function saveSettings() {
    const fields = [
        'settings-title',
        'settings-model',
        'settings-policy-global',
        'settings-policy-chapter',
        'settings-character'
    ];

    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            localStorage.setItem(id, el.value);
        }
    });

    showToast('設定を保存しました');
}

export function getCommonSettings() {
    return {
        novelTitle: localStorage.getItem('settings-title') || '重天の調律師',
        model: localStorage.getItem('settings-model') || 'Gemini 3.5 Flash (High)',
        policyGlobal: localStorage.getItem('settings-policy-global') || '',
        policyChapter: localStorage.getItem('settings-policy-chapter') || '',
        character: localStorage.getItem('settings-character') || ''
    };
}
