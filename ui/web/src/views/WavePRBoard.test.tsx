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
    expect(rows.length).toBe(fixtureWavePRBoard.prs.length);
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
    expect(table.textContent).toContain('No PR opened yet');
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
});
