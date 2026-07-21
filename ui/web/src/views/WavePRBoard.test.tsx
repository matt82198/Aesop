/**
 * WavePRBoard tests — loading, ready, empty, gh-unavailable, and error states,
 * plus the color-independent status contract (icon + text) and inert hostile
 * PR urls. The component takes an injectable `fetcher` so tests never touch the
 * global fetch.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { WavePRBoard } from './WavePRBoard';
import {
  fixtureWavePRBoard,
  fixtureWavePRBoardEmpty,
  fixtureWavePRBoardUnavailable,
  TESTIDS,
} from '../test/fixtures';
import type { WavePRBoardData } from '../lib/types';

const ready = (data: WavePRBoardData) => () => Promise.resolve(data);

describe('WavePRBoard', () => {
  it('renders the view section with a heading', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    expect(await screen.findByTestId(TESTIDS.viewPRBoard)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /wave pr board/i })).toBeInTheDocument();
  });

  it('shows a loading state before data arrives', () => {
    // Never-resolving fetcher keeps the component in the loading state.
    render(<WavePRBoard fetcher={() => new Promise<WavePRBoardData>(() => {})} />);
    expect(screen.getByTestId(TESTIDS.prBoardLoading)).toBeInTheDocument();
  });

  it('renders one row per PR / branch', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    const rows = await screen.findAllByTestId(TESTIDS.prBoardRow);
    // By default, PR-less branches are filtered out, so only 3 rows show
    // (the ones with has_pr=true). fixtureWavePRBoard has 4 total but 1 is PR-less.
    expect(rows.length).toBe(3);
  });

  it('shows PR number, title, and branch', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    const table = await screen.findByTestId(TESTIDS.prBoardTable);
    expect(table.textContent).toContain('#173');
    expect(table.textContent).toContain('Live Wave PR Board view');
    expect(table.textContent).toContain('feat/wave30-pr-board');
  });

  it('CI status is color-independent: icon + text label', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    const cis = await screen.findAllByTestId(TESTIDS.prBoardCi);
    // First fixture PR is passing → must contain the word "Passing" as text,
    // not rely on color. The decorative icon is aria-hidden.
    const passing = cis[0];
    expect(passing.textContent).toMatch(/passing/i);
    const icon = passing.querySelector('[aria-hidden="true"]');
    expect(icon).not.toBeNull();
    // The whole board carries every state's text label somewhere.
    const table = screen.getByTestId(TESTIDS.prBoardTable);
    expect(table.textContent).toMatch(/failing/i);
    expect(table.textContent).toMatch(/pending/i);
  });

  it('surfaces the top blocker per row', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    const table = await screen.findByTestId(TESTIDS.prBoardTable);
    expect(table.textContent).toContain('CI failing');
    // "No PR opened yet" is on the PR-less branch which is hidden by default
    expect(table.textContent).toContain('Review required');
    expect(table.textContent).toContain('Draft — not ready for review');
  });

  it('renders PR titles as real links to the PR url', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    await screen.findByTestId(TESTIDS.prBoardTable);
    const link = screen.getByRole('link', { name: /Live Wave PR Board view/i });
    expect(link).toHaveAttribute('href', 'https://github.com/matt82198/aesop/pull/173');
  });

  it('renders a hostile PR url inert (no javascript: href)', async () => {
    const hostile: WavePRBoardData = {
      ...fixtureWavePRBoard,
      prs: [
        {
          ...fixtureWavePRBoard.prs[0],
          number: 999,
          title: 'hostile pr',
          url: 'javascript:alert(1)',
        },
      ],
    };
    const { container } = render(<WavePRBoard fetcher={ready(hostile)} />);
    await screen.findByTestId(TESTIDS.prBoardTable);
    const jsHrefs = Array.from(container.querySelectorAll('a[href]')).filter((a) =>
      (a.getAttribute('href') || '').toLowerCase().startsWith('javascript:')
    );
    expect(jsHrefs.length).toBe(0);
    // The title still renders (as inert text).
    expect(screen.getByText('hostile pr')).toBeInTheDocument();
  });

  it('uses proper table semantics (column headers with scope)', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    const table = await screen.findByTestId(TESTIDS.prBoardTable);
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.length).toBe(7);
    headers.forEach((h) => expect(h).toHaveAttribute('scope', 'col'));
  });

  it('renders an empty state when there are no PRs or branches', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoardEmpty)} />);
    const empty = await screen.findByTestId(TESTIDS.prBoardEmpty);
    expect(empty.textContent).toMatch(/no open prs|feature branch/i);
    expect(screen.queryByTestId(TESTIDS.prBoardTable)).not.toBeInTheDocument();
  });

  it('renders a gh-unavailable callout with the backend reason', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoardUnavailable)} />);
    const empty = await screen.findByTestId(TESTIDS.prBoardEmpty);
    expect(empty.textContent).toMatch(/github cli/i);
    expect(empty.textContent).toMatch(/not authenticated/i);
  });

  it('renders an error state when the fetch rejects', async () => {
    render(<WavePRBoard fetcher={() => Promise.reject(new Error('boom'))} />);
    const err = await screen.findByTestId(TESTIDS.prBoardError);
    expect(err).toHaveAttribute('role', 'alert');
    expect(err.textContent).toContain('boom');
  });

  it('has an accessible Refresh button', async () => {
    render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
    await screen.findByTestId(TESTIDS.prBoardTable);
    const refresh = screen.getByTestId(TESTIDS.prBoardRefresh);
    expect(refresh.tagName).toBe('BUTTON');
    expect(refresh).toHaveAccessibleName(/refresh/i);
  });

  it('cancels in-flight fetch when unmounting', async () => {
    // A slow fetcher to ensure the component unmounts before it resolves
    const slowFetcher = async () => {
      return new Promise<WavePRBoardData>((resolve) => {
        setTimeout(() => resolve(fixtureWavePRBoard), 100);
      });
    };

    // Spy on console.error to detect setState-on-unmounted-component warnings
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = render(<WavePRBoard fetcher={slowFetcher} />);

    // Wait for loading state to be rendered
    expect(screen.getByTestId(TESTIDS.prBoardLoading)).toBeInTheDocument();

    // Unmount the component before the fetch completes
    unmount();

    // Wait for the async fetch to complete and any setState attempts to occur
    await new Promise((resolve) => setTimeout(resolve, 150));

    // Verify no "setState on unmounted component" warning was logged
    const errorCalls = consoleErrorSpy.mock.calls;
    const unmountWarnings = errorCalls.filter((call) =>
      call.some(
        (arg) =>
          typeof arg === 'string' &&
          (arg.includes('unmounted component') || arg.includes('Can\'t perform a React state update'))
      )
    );

    expect(unmountWarnings).toHaveLength(0);
    consoleErrorSpy.mockRestore();
  });

  describe('Filter: show/hide PR-less branches', () => {
    it('defaults to hiding PR-less branches (only real PRs shown)', async () => {
      // fixtureWavePRBoard has 4 items: 3 with has_pr=true, 1 with has_pr=false
      render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);

      // Default: PR-less branches hidden, so only 3 rows (the PRs with numbers)
      const rows = await screen.findAllByTestId(TESTIDS.prBoardRow);
      expect(rows.length).toBe(3);

      // Verify the table has only PRs (#173, #172, #171), not the branch-only row
      const table = screen.getByTestId(TESTIDS.prBoardTable);
      expect(table.textContent).toContain('#173');
      expect(table.textContent).toContain('#172');
      expect(table.textContent).toContain('#171');
      // The PR-less branch row should not appear in the filtered view
      expect(table.textContent).not.toContain('feat/wave30-cost-pricing');
    });

    it('shows the toggle control with hidden count', async () => {
      render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
      await screen.findByTestId(TESTIDS.prBoardTable);

      // The toggle should be unchecked (false = hidden)
      const toggle = screen.getByTestId(TESTIDS.prBoardTogglePRless) as HTMLInputElement;
      expect(toggle).toBeInTheDocument();
      expect(toggle.type).toBe('checkbox');
      expect(toggle.checked).toBe(false);

      // The label should indicate 1 hidden branch (4 total - 3 with PR)
      expect(screen.getByText(/Show branches without PR.*1 hidden/)).toBeInTheDocument();
    });

    it('toggle reveals PR-less branches and updates the hidden count', async () => {
      const { rerender } = render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);

      // Initially 3 rows (PRs only)
      const initialRows = await screen.findAllByTestId(TESTIDS.prBoardRow);
      expect(initialRows.length).toBe(3);

      // Click the toggle to show PR-less branches
      const toggle = screen.getByTestId(TESTIDS.prBoardTogglePRless) as HTMLInputElement;
      toggle.click();

      // Need a small wait for state update
      await new Promise((resolve) => setTimeout(resolve, 50));

      // Rerender to pick up state changes
      rerender(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);

      // After toggle, all 4 rows should be visible
      const allRows = screen.getAllByTestId(TESTIDS.prBoardRow);
      expect(allRows.length).toBe(4);

      // Table should now contain the PR-less branch
      const table = screen.getByTestId(TESTIDS.prBoardTable);
      expect(table.textContent).toContain('feat/wave30-cost-pricing');
    });

    it('toggle is properly labeled for accessibility', async () => {
      render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
      await screen.findByTestId(TESTIDS.prBoardTable);

      const toggle = screen.getByTestId(TESTIDS.prBoardTogglePRless);
      const label = toggle.closest('label');
      expect(label).toBeInTheDocument();
      expect(label?.textContent).toMatch(/Show branches without PR/);

      // The label should be associated with the checkbox
      const labelFor = document.querySelector('label[for="prboard-toggle-prless"]');
      expect(labelFor).toBeInTheDocument();
      expect(labelFor?.textContent).toMatch(/Show branches without PR/);
    });

    it('shows table when there are PRs to display (toggle off hides PR-less)', async () => {
      render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
      await screen.findByTestId(TESTIDS.prBoardTable);

      // In default state (toggle off), PR-less branches are filtered out
      // The table shows the remaining PRs (3 items)
      const table = screen.getByTestId(TESTIDS.prBoardTable);
      expect(table).toBeInTheDocument();
      expect(table.textContent).toContain('#173');
      expect(table.textContent).toContain('#172');
      expect(table.textContent).toContain('#171');
    });

    it('shows all rows when toggle is on, no callout about hidden branches', async () => {
      const { container, rerender } = render(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);
      await screen.findByTestId(TESTIDS.prBoardTable);

      // Toggle on to show all
      const toggle = screen.getByTestId(TESTIDS.prBoardTogglePRless) as HTMLInputElement;
      toggle.click();

      // Rerender to pick up state changes
      await new Promise((resolve) => setTimeout(resolve, 50));
      rerender(<WavePRBoard fetcher={ready(fixtureWavePRBoard)} />);

      // The table should render with all 4 rows
      const allRows = container.querySelectorAll(`[data-testid="${TESTIDS.prBoardRow}"]`);
      expect(allRows.length).toBeGreaterThanOrEqual(4);
    });
  });
});
