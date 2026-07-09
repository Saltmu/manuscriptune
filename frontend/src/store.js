import { writable } from 'svelte/store';

// Core Application States
export const activeView = writable('dashboard');

export const isRunningProcess = writable(false);
export const novelLines = writable([]);
export const findings = writable([]);
export const activeCategoryFilter = writable('all');
export const activeSeverityFilter = writable('all');
export const activeHighlightLine = writable(null);

const initialSelectedNovelFile = localStorage.getItem('selectedNovelFile') || "";
export const selectedNovelFile = writable(initialSelectedNovelFile);

selectedNovelFile.subscribe(value => {
    localStorage.setItem('selectedNovelFile', value);
});

// Editor Specific States
export const selectedPlot = writable(localStorage.getItem('editor-selected-plot') || "");
selectedPlot.subscribe(value => {
    localStorage.setItem('editor-selected-plot', value);
});

export const activeEditorTab = writable('preview'); // 'preview', 'findings', 'console'
export const novelMetadata = writable({});
export const novelFilename = writable('');

// Review History Specific States
export const selectedReviewHistoryVersion = writable(null);

// Console log states (for streaming output)
export const consoleLogMap = writable({
    sync: '--- プロセスを開始します ---\n',
    plot_review: '--- プロセスを開始します ---\n',
    plot_create: '--- プロセスを開始します ---\n',
    editor: '--- プロセスを開始します ---\n'
});

export const consoleStatusMap = writable({
    sync: 'IDLE',
    plot_review: 'IDLE',
    plot_create: 'IDLE',
    editor: 'IDLE'
});
