import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PlotCreate from './PlotCreate.svelte';

function jsonResponse(body, ok = true) {
    return Promise.resolve({
        ok,
        json: () => Promise.resolve(body),
    });
}

describe('PlotCreate view', () => {
    beforeEach(() => {
        localStorage.clear();
        vi.restoreAllMocks();
    });

    it('loads plot list and defaults to expand mode with revise disabled when no findings', async () => {
        vi.stubGlobal('fetch', vi.fn((url) => {
            if (url === '/api/plots') {
                return jsonResponse({
                    plots: [{ name: 'plot.txt', size: 100, mtime: '2026-07-01', has_findings: false }],
                });
            }
            if (url.startsWith('/api/plot?')) {
                return jsonResponse({ plot_name: 'plot.txt', content: '本文', findings: [] });
            }
            if (url.startsWith('/api/plot/draft')) {
                return jsonResponse({}, false);
            }
            return jsonResponse({}, false);
        }));

        render(PlotCreate);

        await waitFor(() => {
            expect(screen.getByText('plot.txt')).toBeInTheDocument();
        });

        const expandBtn = screen.getByText('🪄 肉付けする');
        const reviseBtn = screen.getByText('🔧 指摘を反映して改稿する');
        expect(expandBtn.className).toContain('active');
        expect(reviseBtn).toBeDisabled();
    });

    it('enables revise mode when the selected plot has integrated findings', async () => {
        vi.stubGlobal('fetch', vi.fn((url) => {
            if (url === '/api/plots') {
                return jsonResponse({
                    plots: [{ name: 'plot.txt', size: 100, mtime: '2026-07-01', has_findings: true }],
                });
            }
            if (url.startsWith('/api/plot?')) {
                return jsonResponse({
                    plot_name: 'plot.txt',
                    content: '本文',
                    findings: [{ id: 'F1', category: '対立', severity: 'high' }],
                });
            }
            if (url.startsWith('/api/plot/draft')) {
                return jsonResponse({}, false);
            }
            return jsonResponse({}, false);
        }));

        render(PlotCreate);

        const reviseBtn = await screen.findByText('🔧 指摘を反映して改稿する');
        await waitFor(() => expect(reviseBtn).not.toBeDisabled());

        await fireEvent.click(reviseBtn);
        expect(reviseBtn.className).toContain('active');
    });

    it('shows the data/sources protection banner', async () => {
        vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ plots: [] })));

        const { container } = render(PlotCreate);

        const banner = container.querySelector('#plot-create-source-warning');
        expect(banner).not.toBeNull();
        expect(banner.textContent).toContain('へは自動反映されません');
    });
});
