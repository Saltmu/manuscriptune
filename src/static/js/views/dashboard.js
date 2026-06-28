import { state, setSelectedNovelFile } from '../state.js';
import { showToast } from '../utils.js';

export async function loadDashboardData() {
    try {
        // Load novels
        const response = await fetch('/api/novels');
        const data = await response.json();
        
        const reviewCardsContainer = document.getElementById('review-draft-cards-container');
        if (reviewCardsContainer) {
            reviewCardsContainer.innerHTML = '';
        }
        
        const hiddenInput = document.getElementById('review-file-select');
        const currentSelected = state.selectedNovelFile || (hiddenInput ? hiddenInput.value : "");
        let selectedFound = false;

        if (data.novels.length === 0) {
            if (reviewCardsContainer) {
                reviewCardsContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">小説が見つかりません。novels/ フォルダを確認してください。</div>`;
            }
        } else {
            data.novels.forEach(n => {
                if (reviewCardsContainer) {
                    const card = document.createElement('div');
                    card.className = 'draft-selection-card';
                    card.dataset.filename = n.name;
                    card.dataset.hasfindings = n.has_findings ? "true" : "false";
                    
                    const badgeHtml = n.has_findings 
                        ? `<span class="badge badge-success">指摘あり</span>` 
                        : `<span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>`;

                    let actionBtnHtml = '';
                    if (n.has_findings) {
                        actionBtnHtml = `<button class="draft-card-action-btn" onclick="event.stopPropagation(); selectAndEditNovel('${n.name}');">📝 校閲する</button>`;
                    }

                    card.innerHTML = `
                        <div class="draft-card-info">
                            <div class="draft-card-name">${n.name}</div>
                            <div class="draft-card-meta">
                                <span>${(n.size / 1024).toFixed(1)} KB</span>
                                <span>•</span>
                                <span>${n.mtime}</span>
                            </div>
                        </div>
                        <div class="draft-card-status">
                            ${badgeHtml}
                        </div>
                        ${actionBtnHtml}
                    `;

                    card.addEventListener('click', () => {
                        selectDraftCard(n.name, n.has_findings);
                    });

                    reviewCardsContainer.appendChild(card);

                    if (currentSelected === n.name) {
                        card.classList.add('active');
                        selectedFound = true;
                    }
                }
            });

            // 以前の選択肢がリスト内で見つからない、あるいは未選択の場合は最初の要素を選択状態にする
            if (reviewCardsContainer && reviewCardsContainer.children.length > 0) {
                if (!selectedFound) {
                    const firstCard = reviewCardsContainer.children[0];
                    selectDraftCard(firstCard.dataset.filename, firstCard.dataset.hasfindings === "true");
                } else {
                    // すでに選択されている場合もプレビューをロード
                    const activeCard = Array.from(reviewCardsContainer.children).find(c => c.dataset.filename === currentSelected);
                    if (activeCard) {
                        loadPreview(currentSelected);
                    }
                }
            }
        }

        // Load Sync Status
        const syncResponse = await fetch('/api/sync/status');
        const syncData = await syncResponse.json();
        const statusArea = document.getElementById('drive-sync-status-area');
        if (statusArea) {
            statusArea.innerHTML = '';

            if (syncData.sources.length === 0) {
                statusArea.innerHTML = '<li>同期された設定資料はありません。</li>';
            } else {
                syncData.sources.forEach(s => {
                    const li = document.createElement('div');
                    li.style.display = 'flex';
                    li.style.justifyContent = 'space-between';
                    li.innerHTML = `
                        <span>${s.name}</span>
                        <span style="font-size:0.8rem; color:var(--text-muted);">${s.last_updated}</span>
                    `;
                    statusArea.appendChild(li);
                });
            }
        }

    } catch (err) {
        console.error(err);
    }
}

export function selectDraftCard(novelName, hasFindings) {
    const container = document.getElementById('review-draft-cards-container');
    if (!container) return;

    Array.from(container.children).forEach(card => {
        if (card.dataset.filename === novelName) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });

    const hiddenInput = document.getElementById('review-file-select');
    if (hiddenInput) {
        hiddenInput.value = novelName;
    }

    setSelectedNovelFile(novelName);

    // Sync URL hash with selection
    const hash = window.location.hash || '#/dashboard';
    const cleanHash = hash.startsWith('#/') ? hash.substring(2) : (hash.startsWith('#') ? hash.substring(1) : hash);
    const parts = cleanHash.split('/');
    const view = parts[0] || 'dashboard';
    const file = parts[1] ? decodeURIComponent(parts[1]) : null;

    if (view === 'review' && file !== novelName) {
        if (!state.isRunningProcess) {
            window.location.hash = `#/review/${encodeURIComponent(novelName)}`;
        }
    }

    loadPreview(novelName);
}

export async function loadPreview(novelName) {
    const header = document.getElementById('review-preview-header');
    const consoleHeader = document.getElementById('review-console-header');
    const previewBody = document.getElementById('review-preview-body');
    const consoleLog = document.getElementById('review-console-log');
    const filenameDisplay = document.getElementById('preview-filename-display');
    
    if (!previewBody) return;
    
    // 表示モードの切り替え
    if (header) header.style.display = 'flex';
    if (consoleHeader) consoleHeader.style.display = 'none';
    previewBody.style.display = 'block';
    if (consoleLog) consoleLog.style.display = 'none';
    
    if (filenameDisplay) filenameDisplay.textContent = novelName;
    previewBody.textContent = 'プレビューを読み込み中...';
    
    // スライドイン表示
    const rightPanel = document.getElementById('review-right-panel');
    if (rightPanel && !rightPanel.classList.contains('show')) {
        rightPanel.classList.add('show');
        // updateToggleButtonText
        const toggleBtn = document.getElementById('review-console-toggle');
        if (toggleBtn) {
            toggleBtn.textContent = '🖥️ コンソール非表示';
        }
    }
    
    try {
        const res = await fetch(`/api/preview?file=${encodeURIComponent(novelName)}`);
        if (res.ok) {
            const data = await res.json();
            previewBody.textContent = data.content;
            previewBody.scrollTop = 0; // スクロールを一番上に
        } else {
            previewBody.textContent = 'プレビューの読み込みに失敗しました。';
        }
    } catch (err) {
        console.error(err);
        previewBody.textContent = 'プレビューのロード中にエラーが発生しました。';
    }
}

export async function selectAndEditNovel(novelName) {
    if (state.isRunningProcess) {
        showToast('プロセス実行中は画面を切り替えられません。');
        return;
    }
    setSelectedNovelFile(novelName);
    window.location.hash = `#/editor/${encodeURIComponent(novelName)}`;
}

export function selectAndReviewNovel(novelName) {
    if (state.isRunningProcess) {
        showToast('プロセス実行中は画面を切り替えられません。');
        return;
    }
    setSelectedNovelFile(novelName);
    window.location.hash = `#/review/${encodeURIComponent(novelName)}`;
}
