import { state, setSelectedNovelFile } from './state.js';
import { showToast, initPanelResizer, shutdownServerGlobal, toggleConsole, closeModal, executeGlobalShutdown } from './utils.js';
import { loadDashboardData, selectDraftCard, loadPreview, selectAndEditNovel, selectAndReviewNovel } from './views/dashboard.js';
import { runDriveSync } from './views/sync.js';
import { loadSourcesForWrite, runAiWriting, copyWritingPrompt } from './views/write.js';
import { runReviewPipeline } from './views/review.js';
import {
    loadEditorData,
    filterCategory,
    filterSeverity,
    toggleAccept,
    confirmApply,
    executeApply,
    closeApplyProgressModal,
    toggleEditMode,
    saveNovel,
    confirmRollback,
    executeRollback
} from './views/editor.js';

// Parse URL hash to view and file resources
function parseHash() {
    const hash = window.location.hash || '#/dashboard';
    const cleanHash = hash.startsWith('#/') ? hash.substring(2) : (hash.startsWith('#') ? hash.substring(1) : hash);
    const parts = cleanHash.split('/');
    const view = parts[0] || 'dashboard';
    const file = parts[1] ? decodeURIComponent(parts[1]) : null;
    return { view, file };
}

let lastHash = window.location.hash || '#/dashboard';

// Handle routing based on hash
async function handleRouting() {
    if (state.isRunningProcess) {
        showToast('プロセス実行中は画面を切り替えられません。');
        // Prevent hash change by rolling back to lastHash
        window.removeEventListener('hashchange', handleRouting);
        window.location.hash = lastHash;
        setTimeout(() => {
            window.addEventListener('hashchange', handleRouting);
        }, 0);
        return;
    }

    const { view, file } = parseHash();
    lastHash = window.location.hash || '#/dashboard';

    const validViews = ['dashboard', 'sync', 'write', 'review', 'editor'];
    if (!validViews.includes(view)) {
        window.location.hash = '#/dashboard';
        return;
    }

    // Toggle view visibility
    document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
    const targetViewEl = document.getElementById(`view-${view}`);
    if (targetViewEl) {
        targetViewEl.classList.add('active');
    }

    // Toggle navigation item active states
    document.querySelectorAll('.nav-item').forEach(i => {
        i.classList.remove('active');
        const href = i.getAttribute('href');
        const onclick = i.getAttribute('onclick');
        if ((href && href.includes(`#/${view}`)) || (onclick && onclick.includes(`'${view}'`))) {
            i.classList.add('active');
        }
    });

    // View-specific data loading
    if (view === 'dashboard') {
        loadDashboardData();
    } else if (view === 'editor') {
        if (file) {
            setSelectedNovelFile(file);
        }
        if (state.selectedNovelFile) {
            // Sync URL with state if the file parameter is missing in URL
            if (!file) {
                window.location.hash = `#/editor/${encodeURIComponent(state.selectedNovelFile)}`;
                return;
            }
            await loadEditorData();
        } else {
            const container = document.getElementById('novel-content');
            if (container) {
                container.innerHTML = `
                    <div style="text-align: center; color: var(--text-muted); padding-top: 60px;">
                        ダッシュボードで小説を選択し、「校閲」を押してください。
                    </div>
                `;
            }
            const filenameDisplay = document.getElementById('filename-display');
            if (filenameDisplay) filenameDisplay.textContent = '-';
            const rollbackBtn = document.getElementById('btn-rollback');
            if (rollbackBtn) rollbackBtn.style.display = 'none';
        }
    } else if (view === 'review') {
        if (file) {
            setSelectedNovelFile(file);
        }
        if (state.selectedNovelFile && !file) {
            window.location.hash = `#/review/${encodeURIComponent(state.selectedNovelFile)}`;
            return;
        }
        await loadDashboardData();
    }
}

// Switch Tabs/Views
function switchView(viewId) {
    if (state.isRunningProcess) {
        showToast('プロセス実行中は画面を切り替えられません。');
        return;
    }
    if (viewId === 'editor' && state.selectedNovelFile) {
        window.location.hash = `#/editor/${encodeURIComponent(state.selectedNovelFile)}`;
    } else if (viewId === 'review' && state.selectedNovelFile) {
        window.location.hash = `#/review/${encodeURIComponent(state.selectedNovelFile)}`;
    } else {
        window.location.hash = `#/${viewId}`;
    }
}

async function loadProjectConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (data.novel_title) {
            const titleEl = document.getElementById('novel-title-display');
            if (titleEl) titleEl.textContent = data.novel_title;
        }
        if (data.initial_novel && !state.selectedNovelFile) {
            setSelectedNovelFile(data.initial_novel);
            
            // Sync URL with initial novel if currently on editor/review view without a specified file
            const { view, file } = parseHash();
            if ((view === 'editor' || view === 'review') && !file) {
                window.location.hash = `#/${view}/${encodeURIComponent(state.selectedNovelFile)}`;
            }
        }
    } catch (err) {
        console.error('Failed to load project config:', err);
    }
}

// Init Load
window.addEventListener('DOMContentLoaded', () => {
    // Listen for hash changes
    window.addEventListener('hashchange', handleRouting);

    // Initial parsing of URL to determine selectedNovelFile early
    const { file } = parseHash();
    if (file) {
        setSelectedNovelFile(file);
    }

    loadProjectConfig();
    loadSourcesForWrite();
    
    // Execute routing for initial page load
    handleRouting();
    
    // Initialize resizers
    initPanelResizer('write-resizer', 'write-right-panel');
    initPanelResizer('review-resizer', 'review-right-panel');
    initPanelResizer('sync-resizer', 'sync-right-panel');
});

// HTML のインラインイベントハンドラからアクセスできるように global 公開する
window.switchView = switchView;
window.runDriveSync = runDriveSync;
window.runAiWriting = runAiWriting;
window.copyWritingPrompt = copyWritingPrompt;
window.runReviewPipeline = runReviewPipeline;
window.selectAndEditNovel = selectAndEditNovel;
window.selectAndReviewNovel = selectAndReviewNovel;
window.filterCategory = filterCategory;
window.filterSeverity = filterSeverity;
window.toggleAccept = toggleAccept;
window.confirmApply = confirmApply;
window.executeApply = executeApply;
window.closeApplyProgressModal = closeApplyProgressModal;
window.toggleEditMode = toggleEditMode;
window.saveNovel = saveNovel;
window.confirmRollback = confirmRollback;
window.executeRollback = executeRollback;
window.shutdownServerGlobal = shutdownServerGlobal;
window.toggleConsole = toggleConsole;
window.closeModal = closeModal;
window.executeGlobalShutdown = executeGlobalShutdown;
