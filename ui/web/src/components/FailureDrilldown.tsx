/**
 * Failure Drill-down Component — expands CI job logs for a failing PR.
 *
 * Mounted from a red PR row in WavePRBoard. Clicking the expand button fetches
 * CI job details (GET /api/wave/failure?pr=N), shows the latest run's jobs,
 * and displays tail excerpts of failing job logs.
 *
 * Polling (NOT SSE): fetcher is called on expand, then on manual refresh.
 * Degrades gracefully when gh is unavailable (same as WavePRBoard).
 *
 * Shape (WaveFailureData):
 *   {
 *     "available": bool,
 *     "error": str | null,
 *     "pr_number": int,
 *     "branch": str,
 *     "latest_run": {id, name, status, conclusion, url} | null,
 *     "jobs": [{id, name, status, conclusion, url, log_excerpt}, ...]
 *   }
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { WaveFailureData, WaveFailureJob, WaveFailureRun } from '../lib/types';
import { fetchWaveFailure } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import './FailureDrilldown.css';

type LoadState = 'collapsed' | 'loading' | 'ready' | 'error';

interface FailureDrilldownProps {
  /** PR number to fetch failure details for. */
  prNumber: number;

  /** Injectable for tests; defaults to the real GET /api/wave/failure fetch. */
  fetcher?: (prNumber: number) => Promise<WaveFailureData>;
}

function RunSummary({ run, branch }: { run: WaveFailureRun | null; branch: string }) {
  if (!run) {
    return <div className="failure-run-empty">No workflow runs found for this branch.</div>;
  }

  const conclusionIcon = {
    success: '✔',
    failure: '✖',
    cancelled: '⊘',
    timed_out: '⏱',
  }[run.conclusion as string] || '?';

  const conclusionLabel = (
    {
      success: 'Success',
      failure: 'Failed',
      cancelled: 'Cancelled',
      timed_out: 'Timed out',
    } as Record<string, string>
  )[run.conclusion as string] || 'Unknown';

  return (
    <div className="failure-run" data-testid={TESTIDS.failureDrilldownRun}>
      <div className="failure-run-header">
        <span className="failure-run-conclusion">
          <span aria-hidden="true" className="failure-run-icon">
            {conclusionIcon}
          </span>
          <span>{conclusionLabel}</span>
        </span>
        <span className="failure-run-name">{run.name}</span>
        {run.url && (
          <a href={run.url} target="_blank" rel="noopener noreferrer" className="failure-run-link">
            View on GitHub
          </a>
        )}
      </div>
      <div className="failure-run-meta">
        Branch: <code>{branch}</code> | Run ID: <code>{run.id}</code>
      </div>
    </div>
  );
}

function JobRow({ job }: { job: WaveFailureJob }) {
  const [expanded, setExpanded] = useState(false);

  const isFailing = job.conclusion === 'failure';
  const hasLog = job.log_excerpt != null;

  const conclusionIcon = {
    success: '✔',
    failure: '✖',
    cancelled: '⊘',
    timed_out: '⏱',
  }[job.conclusion as string] || '?';

  const conclusionLabel = (
    {
      success: 'Success',
      failure: 'Failed',
      cancelled: 'Cancelled',
      timed_out: 'Timed out',
    } as Record<string, string>
  )[job.conclusion as string] || 'Unknown';

  return (
    <div className="failure-job" data-testid={TESTIDS.failureDrilldownJob}>
      <button
        className={`failure-job-summary ${isFailing ? 'failure-job-failing' : ''} ${expanded ? 'failure-job-expanded' : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        <span aria-hidden="true" className="failure-job-icon">
          {expanded ? '▼' : '▶'}
        </span>
        <span className="failure-job-status">
          <span aria-hidden="true" className="failure-job-conclusion-icon">
            {conclusionIcon}
          </span>
          <span>{conclusionLabel}</span>
        </span>
        <span className="failure-job-name">{job.name}</span>
        {job.url && !expanded && (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="failure-job-link"
            onClick={(e) => e.stopPropagation()}
          >
            View on GitHub
          </a>
        )}
      </button>

      {expanded && (
        <div className="failure-job-details">
          <div className="failure-job-meta">
            ID: <code>{job.id}</code> | Status: <code>{job.status}</code>
            {job.url && (
              <>
                {' '}
                |{' '}
                <a href={job.url} target="_blank" rel="noopener noreferrer">
                  View on GitHub
                </a>
              </>
            )}
          </div>

          {hasLog ? (
            <pre className="failure-job-log" data-testid={TESTIDS.failureDrilldownLogExcerpt}>
              {job.log_excerpt}
            </pre>
          ) : isFailing ? (
            <div className="failure-job-log-unavailable">Could not fetch job log.</div>
          ) : null}
        </div>
      )}
    </div>
  );
}

export function FailureDrilldown({
  prNumber,
  fetcher = fetchWaveFailure,
}: FailureDrilldownProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [data, setData] = useState<WaveFailureData | null>(null);
  const [state, setState] = useState<LoadState>('collapsed');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Keep the latest fetcher without re-subscribing on each render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  // Track if component is mounted
  const isMountedRef = useRef(true);

  const load = useCallback(async () => {
    if (!isExpanded) return;

    try {
      const result = await fetcherRef.current(prNumber);
      if (!isMountedRef.current) return;
      setData(result);
      setErrorMsg(null);
      setState('ready');
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load failure details');
      setState((prev) => (prev === 'ready' ? 'ready' : 'error'));
    }
  }, [prNumber, isExpanded]);

  const toggleExpanded = useCallback(() => {
    if (!isExpanded) {
      setIsExpanded(true);
      setState('loading');
      load();
    } else {
      setIsExpanded(false);
      setState('collapsed');
    }
  }, [isExpanded, load]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (isExpanded) {
      load();
    }
  }, [isExpanded, load]);

  const jobs = data?.jobs ?? [];
  const failingJobs = jobs.filter((j) => j.conclusion === 'failure');

  return (
    <div className="failure-drilldown" data-testid={TESTIDS.failureDrilldown}>
      <button
        className="failure-drilldown-toggle"
        data-testid={TESTIDS.failureDrilldownToggle}
        onClick={toggleExpanded}
        aria-expanded={isExpanded}
        aria-label={isExpanded ? 'Hide failure details' : 'Show failure details'}
      >
        <span aria-hidden="true">{isExpanded ? '▼' : '▶'}</span>
        {' '}
        <span>Drill down</span>
      </button>

      {isExpanded && (
        <div className="failure-drilldown-content" data-testid={TESTIDS.failureDrilldownContent}>
          {state === 'loading' && (
            <div className="failure-drilldown-loading" data-testid={TESTIDS.failureDrilldownLoading}>
              Loading CI details{'…'}
            </div>
          )}

          {state === 'error' && (
            <div
              className="failure-drilldown-error"
              data-testid={TESTIDS.failureDrilldownError}
              role="alert"
            >
              <strong>Error:</strong> {errorMsg ?? 'Unknown error'}
              <button type="button" onClick={() => load()}>
                Retry
              </button>
            </div>
          )}

          {state === 'ready' && data && !data.available && (
            <div
              className="failure-drilldown-unavailable"
              data-testid={TESTIDS.failureDrilldownUnavailable}
            >
              <strong>GitHub CLI unavailable</strong>
              <p>{data.error ?? 'The GitHub CLI (gh) is not available.'}</p>
            </div>
          )}

          {state === 'ready' && data && data.available && !data.latest_run && (
            <div
              className="failure-drilldown-empty"
              data-testid={TESTIDS.failureDrilldownEmpty}
            >
              No workflow runs found for this branch yet.
            </div>
          )}

          {state === 'ready' && data && data.available && data.latest_run && (
            <div>
              <RunSummary run={data.latest_run} branch={data.branch} />

              <div className="failure-jobs">
                {jobs.length === 0 ? (
                  <div className="failure-jobs-empty">No jobs found in this run.</div>
                ) : (
                  <>
                    <div className="failure-jobs-summary">
                      {failingJobs.length > 0 ? (
                        <div className="failure-jobs-failing">
                          <strong>{failingJobs.length}</strong> job
                          {failingJobs.length !== 1 ? 's' : ''} failed
                        </div>
                      ) : (
                        <div className="failure-jobs-all-passing">All jobs passed</div>
                      )}
                    </div>
                    <div className="failure-jobs-list">
                      {jobs.map((job) => (
                        <JobRow key={job.id} job={job} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FailureDrilldown;
