import { startEventStream, showToast } from '../utils.js';

let plotFindings = [];
let currentPlotFile = "";

export async function loadPlotsData() {
    try {
        const response = await fetch('/api/plots');
        const data = await response.json();

        const container = document.getElementById('plot-cards-container');
        if (!container) return;
        container.innerHTML = '';

        const hiddenInput = document.getElementById('plot-file-select');
        const savedPlot = localStorage.getItem('selectedPlotFile') || (hiddenInput ? hiddenInput.value : "");
        let selectedFound = false;

        if (data.plots.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">プロットファイルが見つかりません。data/sources/ フォルダを確認してください。</div>`;
            return;
        }

        data.plots.forEach(p => {
            const card = document.createElement('div');
            card.className = 'draft-selection-card';
            card.dataset.filename = p.name;
            card.dataset.hasfindings = p.has_findings ? "true" : "false";

            const badgeHtml = p.has_findings
                ? `<span class="badge badge-success">指摘あり</span>`
                : `<span class="badge badge-warning" style="background-color:rgba(255,255,255,0.03); color:var(--text-muted)">未校閲</span>`;

            card.innerHTML = `
                <div class="draft-card-info">
                    <div class="draft-card-name">${p.name}</div>
                    <div class="draft-card-meta">
                        <span>${(p.size / 1024).toFixed(1)} KB</span>
                        <span>•</span>
                        <span>${p.mtime}</span>
                    </div>
                </div>
                <div class="draft-card-status">
                    ${badgeHtml}
                </div>
            `;

            card.addEventListener('click', () => {
                selectPlotCard(p.name, p.has_findings);
            });

            container.appendChild(card);

            if (savedPlot === p.name) {
                card.classList.add('active');
                selectedFound = true;
            }
        });

        if (container.children.length > 0) {
            if (!selectedFound) {
                const firstCard = container.children[0];
                selectPlotCard(firstCard.dataset.filename, firstCard.dataset.hasfindings === "true");
            } else {
                loadPlotPreview(savedPlot);
            }
        }
    } catch (err) {
        console.error('Failed to load plots list:', err);
        showToast('プロット一覧の取得に失敗しました。');
    }
}

function selectPlotCard(filename, hasFindings) {
    currentPlotFile = filename;
    localStorage.setItem('selectedPlotFile', filename);

    const hiddenInput = document.getElementById('plot-file-select');
    if (hiddenInput) hiddenInput.value = filename;

    document.querySelectorAll('#plot-cards-container .draft-selection-card').forEach(c => {
        if (c.dataset.filename === filename) {
            c.classList.add('active');
        } else {
            c.classList.remove('active');
        }
    });

    loadPlotPreview(filename);
}

async function loadPlotPreview(filename) {
    try {
        const response = await fetch(`/api/plot?file=${encodeURIComponent(filename)}`);
        if (!response.ok) throw new Error('Failed to fetch plot details');

        const data = await response.json();

        // プレビュー表示
        const previewFilename = document.getElementById('plot-preview-filename');
        if (previewFilename) previewFilename.textContent = data.plot_name;

        const previewBody = document.getElementById('plot-preview-body');
        if (previewBody) {
            previewBody.textContent = data.content || "内容が空です。";
        }

        // 指摘事項表示
        plotFindings = data.findings || [];
        renderPlotFindings();
    } catch (err) {
        console.error('Failed to load plot details:', err);
        showToast('プロット詳細の取得に失敗しました。');
    }
}

function renderPlotFindings() {
    const cardEl = document.getElementById('plot-findings-card');
    const listEl = document.getElementById('plot-findings-list');
    const countEl = document.getElementById('plot-findings-count');
    const sevFilter = document.getElementById('plot-filter-severity');
    const catFilter = document.getElementById('plot-filter-category');

    if (!listEl) return;
    listEl.innerHTML = '';

    if (plotFindings.length === 0) {
        if (cardEl) cardEl.style.display = 'none';
        return;
    }

    if (cardEl) cardEl.style.display = 'block';
    if (countEl) countEl.textContent = plotFindings.length;

    // カテゴリフィルタの選択肢を動的に構築（初回のみ、または描画時）
    const selectedCategory = catFilter ? catFilter.value : "all";
    if (catFilter) {
        const categories = new Set();
        plotFindings.forEach(f => {
            if (f.category) categories.add(f.category);
        });

        catFilter.innerHTML = '<option value="all">すべて表示</option>';
        categories.forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            if (cat === selectedCategory) opt.selected = true;
            catFilter.appendChild(opt);
        });
    }

    // フィルタリング
    const filtered = plotFindings.filter(f => {
        const activeSev = sevFilter ? sevFilter.value : "all";
        const activeCat = catFilter ? catFilter.value : "all";

        if (activeSev !== "all" && String(f.severity).toLowerCase() !== activeSev) return false;
        if (activeCat !== "all" && f.category !== activeCat) return false;
        return true;
    });

    if (filtered.length === 0) {
        listEl.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 0.9rem;">該当する指摘事項はありません</div>`;
        return;
    }

    filtered.forEach(f => {
        const card = document.createElement('div');
        const isConflict = String(f.category).includes('対立') || String(f.category).includes('葛藤') || String(f.category).includes('GMCO');
        card.className = `finding-card ${isConflict ? 'logic' : 'style'}`;
        card.id = `plot-finding-card-${f.id}`;

        card.innerHTML = `
            <div class="card-header" style="border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px; margin-bottom: 8px;">
                <div class="card-meta">
                    <span class="badge badge-id">${f.id}</span>
                    <span class="badge badge-category ${isConflict ? 'logic' : 'style'}">${f.category}</span>
                    <span class="badge badge-severity ${String(f.severity).toLowerCase()}">${f.severity}</span>
                </div>
            </div>
            <div class="card-location" style="margin-bottom: 8px; font-size: 0.85rem; color: var(--text-accent);">場所: ${f.location}</div>
            <div class="card-field" style="margin-bottom: 8px;">
                <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">対象プロット記述</div>
                <div class="field-value original-text" style="font-family: monospace; background: rgba(0,0,0,0.2); padding: 6px; border-radius: 4px; font-size: 0.85rem;">${f.original}</div>
            </div>
            <div class="card-field" style="margin-bottom: 8px;">
                <div class="field-label" style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">分析</div>
                <div class="field-value analysis-text" style="font-size: 0.9rem; line-height: 1.5; color: #cbd5e1;">${f.analysis}</div>
            </div>
            <div class="card-field">
                <div class="field-label" style="font-size: 0.75rem; color: var(--text-success); text-transform: uppercase;">構成改善案</div>
                <div class="field-value suggestion-text" style="font-size: 0.9rem; line-height: 1.5; color: var(--text-success); font-weight: 500;">${f.suggestion}</div>
            </div>
        `;

        listEl.appendChild(card);
    });
}

export function filterPlotFindings() {
    renderPlotFindings();
}

export function runPlotReviewPipeline() {
    const selectEl = document.getElementById('plot-file-select');
    if (!selectEl) return;
    const fileName = selectEl.value;
    if (!fileName) {
        alert('プロットファイルを選択してください');
        return;
    }

    // 表示をコンソールログ表示モードに切り替える
    const header = document.getElementById('plot_review-preview-header');
    const consoleHeader = document.getElementById('plot_review-console-header');
    const previewBody = document.getElementById('plot-preview-body');
    const consoleLog = document.getElementById('plot_review-console-log');

    if (header) header.style.display = 'none';
    if (consoleHeader) consoleHeader.style.display = 'flex';
    if (previewBody) previewBody.style.display = 'none';
    if (consoleLog) consoleLog.style.display = 'block';

    const btn = document.getElementById('btn-run-plot-review');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '🔍 レビュー実行中...';
    }

    // ナビゲーションブロックを設定
    window.state = window.state || {};
    window.state.isRunningProcess = true;

    const modelVal = document.getElementById('plot-review-model').value;
    let url = `/api/stream/plot_review?file=${encodeURIComponent(fileName)}`;
    if (modelVal) {
        url += `&model=${encodeURIComponent(modelVal)}`;
    }

    startEventStream(url, 'plot_review-console-log', 'plot-console-status', (success) => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '🔍 プロットレビューを実行';
        }

        window.state.isRunningProcess = false;

        if (success) {
            showToast('プロットレビューパイプラインが正常に完了しました');
            // コンソールログから元のプレビュー画面に戻す
            if (header) header.style.display = 'flex';
            if (consoleHeader) consoleHeader.style.display = 'none';
            if (previewBody) previewBody.style.display = 'block';
            if (consoleLog) consoleLog.style.display = 'none';

            // 指摘情報を再ロード
            loadPlotsData();
        } else {
            showToast('プロットレビュー中にエラーが発生しました。コンソールログを確認してください。');
        }
    });
}
