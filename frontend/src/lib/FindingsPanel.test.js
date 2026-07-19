import '@testing-library/jest-dom';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import FindingsPanel from './FindingsPanel.svelte';
import {
    findings,
    activeEditorTab,
    activeCategoryFilter,
    activeSeverityFilter,
    activeDecisionFilter,
} from '../store.js';

function makeFinding(overrides = {}) {
    return {
        id: 'F1',
        category: '文芸表現',
        severity: 'medium',
        location: 'L10',
        analysis: '分析',
        original: '原文',
        suggestion: '提案',
        accepted: null,
        ...overrides,
    };
}

describe('FindingsPanel decision UI', () => {
    beforeEach(() => {
        activeEditorTab.set('findings');
        activeCategoryFilter.set('all');
        activeSeverityFilter.set('all');
        activeDecisionFilter.set('all');
        findings.set([]);
    });

    afterEach(() => {
        cleanup();
    });

    it('shows the undecided state chip and decision buttons for a finding with no accepted value', () => {
        findings.set([makeFinding({ id: 'F1', accepted: null })]);
        render(FindingsPanel);

        expect(screen.getByText('⚠ 要判断')).toBeInTheDocument();
        expect(screen.getByText('採用する')).toBeInTheDocument();
        expect(screen.getByText('見送る')).toBeInTheDocument();
    });

    it('shows the accepted state chip and active accept button when accepted === "y"', () => {
        findings.set([makeFinding({ id: 'F1', accepted: 'y' })]);
        const { container } = render(FindingsPanel);

        expect(container.querySelector('.state-chip.accepted').textContent).toContain('✓ 採用');
        expect(screen.getByText('✓ 採用中')).toBeInTheDocument();
    });

    it('shows the dismissed state chip and active dismiss button when accepted === "n"', () => {
        findings.set([makeFinding({ id: 'F1', accepted: 'n' })]);
        const { container } = render(FindingsPanel);

        expect(container.querySelector('.state-chip.dismissed').textContent).toContain('見送り');
        expect(screen.getByText('見送り中')).toBeInTheDocument();
    });

    it('filters findings by decision when a decision filter chip is clicked', async () => {
        findings.set([
            makeFinding({ id: 'F1', accepted: 'y' }),
            makeFinding({ id: 'F2', accepted: 'n' }),
            makeFinding({ id: 'F3', accepted: null }),
        ]);
        const { container } = render(FindingsPanel);

        await fireEvent.click(container.querySelector('.filter-btn.df-accepted'));

        expect(screen.getByText('F1')).toBeInTheDocument();
        expect(screen.queryByText('F2')).not.toBeInTheDocument();
        expect(screen.queryByText('F3')).not.toBeInTheDocument();
    });

    it('sorts undecided findings to the top of the list', () => {
        findings.set([
            makeFinding({ id: 'F1', accepted: 'y' }),
            makeFinding({ id: 'F2', accepted: null }),
        ]);
        const { container } = render(FindingsPanel);
        const cards = container.querySelectorAll('.finding-card');

        expect(cards[0].id).toBe('finding-card-F2');
        expect(cards[1].id).toBe('finding-card-F1');
    });

    it('dispatches toggle-decision with val "y" when clicking 採用する', async () => {
        findings.set([makeFinding({ id: 'F1', accepted: null })]);
        const onToggleDecision = vi.fn();
        render(FindingsPanel, { events: { 'toggle-decision': onToggleDecision } });

        await fireEvent.click(screen.getByText('採用する'));

        expect(onToggleDecision).toHaveBeenCalledTimes(1);
        expect(onToggleDecision.mock.calls[0][0].detail).toEqual({ findingId: 'F1', val: 'y' });
    });

    it('dispatches toggle-decision with val "n" when clicking 見送る', async () => {
        findings.set([makeFinding({ id: 'F1', accepted: null })]);
        const onToggleDecision = vi.fn();
        render(FindingsPanel, { events: { 'toggle-decision': onToggleDecision } });

        await fireEvent.click(screen.getByText('見送る'));

        expect(onToggleDecision).toHaveBeenCalledTimes(1);
        expect(onToggleDecision.mock.calls[0][0].detail).toEqual({ findingId: 'F1', val: 'n' });
    });
});
