/**
 * Wave PR Board — the current wave's open PRs and PR-less feat/* branches at a
 * glance: PR number + title, branch, CI status, mergeable state, age, and the
 * top blocker. Solves the daily context-switch to GitHub to check PR/CI status.
 *
 * Data: polls GET /api/wave/prs (own endpoint — `gh pr list` is too slow to run
 * on every SSE tick, and the backend caches a few seconds). Auto-refreshes on a
 * 15s interval plus a manual Refresh button.
 *
 * A11y: status rides on icon + text, never color alone (WCAG 1.4.1). Real
 * <table> semantics with scope="col" headers; PR titles are keyboard-navigable
 * links whose hrefs pass through sanitizeUrl (hostile schemes render inert).
 * Loading / empty / error / gh-unavailable states are all first-class.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { WavePR, WavePRBoardData } from '../lib/types';
import { fetchWavePRs } from '../lib/api';
import { formatTimestamp } from '../lib/format';
import { sanitizeUrl } from '../lib/sanitizeUrl';
import { TESTIDS } from '../test/fixtures';
import { FailureDrilldown } from '../components/FailureDrilldown';
import './WavePRBoard.css';

const POLL_INTERVAL_MS = 15000;

type LoadState = 'loading' | 'ready' | 'error';

interface WavePRBoardProps {
  /** Injectable for tests; defaults to the real GET /api/wave/prs fetch. */
  fetcher?: () => Promise<WavePRBoardData>;
}

/** CI rollup → { icon, label, className }. Icon + text, never color alone. */
const CI_DISPLAY: Record<WavePR['ci'], { icon: string; label: string; cls: string }> = {
  passing: { icon: '✔', label: 'Passing', cls: 'text-status-ok' }, // ✔
  failing: { icon: '✖', label: 'Failing', cls: 'text-status-error' }, // ✖
  pending: { icon: '●', label: 'Pending', cls: 'text-status-warn' }, // ●
  none: { icon: '–', label: 'No checks', cls: 'text-status-neutral' }, // –
};

function mergeableDisplay(mergeable: string): { label: string; cls: string } {
  const m = (mergeable || '').toUpperCase();
  if (m === 'MERGEABLE') return { label: 'Mergeable', cls: 'text-status-ok' };
  if (m === 'CONFLICTING') return { label: 'Conflicting', cls: 'text-status-error' };
  return { label: 'Unknown', cls: 'text-status-neutral' };
}

function PRRow({ pr }: { pr: WavePR }) {
  const ci = CI_DISPLAY[pr.ci] ?? CI_DISPLAY.none;
  const merge = mergeableDisplay(pr.mergeable);
  const href = pr.has_pr ? sanitizeUrl(pr.url) : null;
  const age = pr.created_at ? formatTimestamp(pr.created_at) : '—';
  // Failing PRs get an expandable drill-down (PR → CI jobs → failed step → log excerpt).
  const [expanded, setExpanded] = useState(false);
  const canDrill = pr.ci === 'failing' && pr.has_pr && pr.number != null;

  return (
    <>
    <tr data-testid={TESTIDS.prBoardRow}>
      <td className="prboard-num">
        {pr.number != null ? `#${pr.number}` : <span className="prboard-branch-tag">branch</span>}
      </td>
      <td className="prboard-title">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {pr.title}
          </a>
        ) : (
          <span>{pr.title}</span>
        )}
        {pr.is_draft && <span className="prboard-draft-badge"> (draft)</span>}
      </td>
      <td className="prboard-branchcol">
        <code>{pr.branch}</code>
      </td>
      <td className="prboard-cicol">
        <span className={`prboard-status ${ci.cls}`} data-testid={TESTIDS.prBoardCi}>
          <span aria-hidden="true" className="prboard-status-icon">
            {ci.icon}
          </span>
          <span>{ci.label}</span>
        </span>
        {canDrill && (
          <button
            type="button"
            className="prboard-refresh"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? 'Hide details' : 'Details'}
          </button>
        )}
      </td>
      <td className="prboard-mergecol">
        <span className={merge.cls}>{merge.label}</span>
      </td>
      <td className="prboard-agecol">{age}</td>
      <td className="prboard-blockercol">
        {pr.blocker ? (
          <span className="prboard-blocker">{pr.blocker}</span>
        ) : (
          <span className="text-status-ok">Ready</span>
        )}
      </td>
    </tr>
    {canDrill && expanded && (
      <tr>
        <td colSpan={7}>
          <FailureDrilldown prNumber={pr.number as number} />
        </td>
      </tr>
    )}
    </>
  );
}

export function WavePRBoard({ fetcher = fetchWavePRs }: WavePRBoardProps) {
  const [data, setData] = useState<WavePRBoardData | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Keep the latest fetcher without re-subscribing the poll interval on each render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  // Track if component is mounted to prevent setState on unmounted component
  const isMountedRef = useRef(true);

  const load = useCallback(async () => {
    // Create an AbortController for this fetch to allow cancellation on unmount
    const abortController = new AbortController();

    try {
      const result = await fetcherRef.current();
      // Check if still mounted before updating state
      if (!isMountedRef.current) {
        abortController.abort();
        return;
      }
      setData(result);
      setErrorMsg(null);
      setState('ready');
    } catch (err) {
      // If the component was unmounted or fetch was aborted, don't setState
      if (!isMountedRef.current) {
        abortController.abort();
        return;
      }
      // Ignore abort errors (component was unmounted)
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load PR board');
      // Preserve any previously loaded data; only flip to the error screen
      // when we have nothing to show.
      setState((prev) => (prev === 'ready' ? 'ready' : 'error'));
    }
  }, []);

  useEffect(() => {
    // Mark as mounted when effect runs
    isMountedRef.current = true;

    load();
    const id = setInterval(load, POLL_INTERVAL_MS);

    return () => {
      // Mark as unmounted when component unmounts
      isMountedRef.current = false;
      // Clear the interval timer
      clearInterval(id);
    };
  }, [load]);

  const prs = data?.prs ?? [];

  return (
    <section className="view-prboard" data-testid={TESTIDS.viewPRBoard} aria-label="Wave PR board">
      <div className="prboard-head">
        <h2>Wave PR Board</h2>
        <button
          type="button"
          className="prboard-refresh"
          data-testid={TESTIDS.prBoardRefresh}
          onClick={load}
        >
          Refresh
        </button>
      </div>

      {errorMsg && state === 'ready' && (
        <div className="prboard-callout prboard-callout--warn" role="status">
          <span aria-hidden="true">{'⚠'} </span>
          Refresh failed ({errorMsg}); showing the last successful snapshot.
        </div>
      )}

      {state === 'loading' && (
        <div className="prboard-callout" role="status" data-testid={TESTIDS.prBoardLoading}>
          Loading pull requests{'…'}
        </div>
      )}

      {state === 'error' && (
        <div
          className="prboard-callout prboard-callout--error"
          role="alert"
          data-testid={TESTIDS.prBoardError}
        >
          <h3>Could not load PR board</h3>
          <p>{errorMsg ?? 'Unknown error'}</p>
          <button type="button" className="prboard-refresh" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {state === 'ready' && data && !data.available && (
        <div
          className="prboard-callout prboard-callout--info"
          role="status"
          data-testid={TESTIDS.prBoardEmpty}
        >
          <h3>GitHub CLI unavailable</h3>
          <p>{data.error ?? 'The GitHub CLI (gh) is not available.'}</p>
          <p>
            Install and authenticate the GitHub CLI (<code>gh auth login</code>) to see live PR and
            CI status here.
          </p>
        </div>
      )}

      {state === 'ready' && data && data.available && prs.length === 0 && (
        <div
          className="prboard-callout prboard-callout--info"
          role="status"
          data-testid={TESTIDS.prBoardEmpty}
        >
          <h3>No open PRs or feature branches</h3>
          <p>
            Nothing is in flight for the current wave. Open a PR or push a <code>feat/*</code> branch
            and it will appear here.
          </p>
        </div>
      )}

      {state === 'ready' && data && data.available && prs.length > 0 && (
        <div className="prboard-table-wrapper">
          <table className="prboard-table" data-testid={TESTIDS.prBoardTable}>
            <caption>
              Open pull requests and feature branches for the current wave
              {data.generated_at ? ` (as of ${formatTimestamp(data.generated_at)})` : ''}
            </caption>
            <thead>
              <tr>
                <th scope="col">PR</th>
                <th scope="col">Title</th>
                <th scope="col">Branch</th>
                <th scope="col">CI</th>
                <th scope="col">Mergeable</th>
                <th scope="col">Age</th>
                <th scope="col">Top blocker</th>
              </tr>
            </thead>
            <tbody>
              {prs.map((pr) => (
                <PRRow key={pr.number != null ? `pr-${pr.number}` : `branch-${pr.branch}`} pr={pr} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default WavePRBoard;
