import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import Editor from './Editor.svelte';
import { selectedNovelFile, findings, activeEditorTab } from '../store.js';

function jsonResponse(body, ok = true) {
    return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) });
}

function stubFetch(findingsData) {
    vi.stubGlobal('fetch', vi.fn((url) => {
        const u = String(url);
        if (u === '/api/auth/token') return jsonResponse({ token: 'test-token' });
        if (u.startsWith('/api/plots')) return jsonResponse({ plots: [] });
        if (u.startsWith('/api/plot/episodes_status')) return jsonResponse({}, false);
        if (u.startsWith('/api/data')) {
            return jsonResponse({ novel_lines: [], findings: findingsData, metadata: {}, novel_filename: 'test.txt' });
        }
        if (u.startsWith('/api/history')) return jsonResponse({ history: [] });
        if (u.startsWith('/api/save')) return jsonResponse({ status: 'success' });
        return jsonResponse({}, false);
    }));
}

function makeFinding(overrides = {}) {
    return {
        id: 'F1',
        category: '文芸表現',
        severity: 'medium',
        location: 'L1',
        analysis: '分析',
        original: '原文',
        suggestion: '提案',
        accepted: null,
        ...overrides,
    };
}

describe('Editor decision workflow', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
        vi.restoreAllMocks();
        selectedNovelFile.set('');
        findings.set([]);
        activeEditorTab.set('findings');
    });

    afterEach(() => {
        cleanup();
    });

    it('accepts a finding, updates header counts, and toggles back to undecided on a second click', async () => {
        stubFetch([makeFinding()]);
        selectedNovelFile.set('test.txt');

        render(Editor);

        await screen.findByText('採用する');
        expect(screen.getByText('未判断 1')).toBeInTheDocument();

        await fireEvent.click(screen.getByText('採用する'));
        await waitFor(() => expect(screen.getByText('✓ 採用中')).toBeInTheDocument());
        expect(screen.getByText('採用 1')).toBeInTheDocument();
        expect(screen.getByText('未判断 0')).toBeInTheDocument();

        await fireEvent.click(screen.getByText('✓ 採用中'));
        await waitFor(() => expect(screen.getByText('採用する')).toBeInTheDocument());
        expect(screen.getByText('未判断 1')).toBeInTheDocument();
    });

    it('disables the apply button with no accepted findings and shows the count once accepted', async () => {
        stubFetch([makeFinding()]);
        selectedNovelFile.set('test.txt');

        render(Editor);

        const applyBtn = await screen.findByText('小説へ反映');
        expect(applyBtn).toBeDisabled();

        await fireEvent.click(await screen.findByText('採用する'));

        await waitFor(() => expect(screen.getByText('小説へ反映 (1件)')).toBeInTheDocument());
        expect(screen.getByText('小説へ反映 (1件)')).not.toBeDisabled();
    });

    it('auto-saves via /api/save when a decision is made', async () => {
        stubFetch([makeFinding()]);
        selectedNovelFile.set('test.txt');

        render(Editor);

        await fireEvent.click(await screen.findByText('採用する'));

        await waitFor(() => {
            expect(fetch).toHaveBeenCalledWith(
                '/api/save',
                expect.objectContaining({ method: 'POST' })
            );
        });
    });
});
