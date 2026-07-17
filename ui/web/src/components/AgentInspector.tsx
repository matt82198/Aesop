/**
 * AgentInspector — read-only side drawer with one agent's detail.
 *
 * Opened by clicking (or keyboard-activating) an agent in the Agents panel.
 * Shows status, runtime, tokens, task label, dispatch prompt, and the
 * TRANSCRIPT TAIL (last ~40 lines of the agent's *.jsonl, fetched from
 * GET /api/agent?id=). This dashboard is READ-ONLY: there are no Stop/Retry
 * or any other mutating actions here.
 *
 * A11y (WCAG): role="dialog" + aria-modal, labelled by its heading; Escape and
 * a real close <button> both dismiss it; focus is trapped while open and
 * restored to the trigger on close. Status rides on icon + TEXT, never color
 * alone (1.4.1). Transcript text is rendered as escaped text (the backend
 * hands back plain strings only) — no raw-HTML injection is possible.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Agent, AgentInspectorDetail } from '../lib/types';
import { fetchAgentInspector } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import './AgentInspector.css';

interface AgentInspectorProps {
  agent: Agent;
  onClose: () => void;
  /** Injectable for tests; defaults to the real GET /api/agent?id= fetch. */
  fetcher?: (id: string) => Promise<AgentInspectorDetail>;
}

type LoadState = 'loading' | 'ready' | 'error';

/** Status → decorative icon. Text label always accompanies it (never color-only). */
function statusIcon(status: string): string {
  if (status === 'running') return '▶';
  if (status === 'idle') return '⏸';
  if (status === 'SUSPICIOUS' || status === 'HIGH') return '✖';
  if (status === 'MED' || status === 'DRIFT') return '⚠';
  return '●';
}

function statusClass(status: string): string {
  if (status === 'running') return 'text-status-info';
  if (status === 'SUSPICIOUS' || status === 'HIGH') return 'text-status-error';
  if (status === 'MED' || status === 'DRIFT') return 'text-status-warn';
  return 'text-status-neutral';
}

function formatRuntime(seconds: number | undefined): string {
  if (typeof seconds !== 'number' || seconds < 0) return 'unknown';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

export function AgentInspector({ agent, onClose, fetcher = fetchAgentInspector }: AgentInspectorProps) {
  const [detail, setDetail] = useState<AgentInspectorDetail | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  // The element focused before the drawer opened, so focus can return to it.
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Fetch detail whenever the inspected agent changes.
  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setErrorMsg(null);
    setDetail(null);
    fetcher(agent.id)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setState('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMsg(err instanceof Error ? err.message : 'Failed to load agent detail');
        setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [agent.id, fetcher]);

  // Capture the trigger, move focus into the dialog, restore on unmount.
  useEffect(() => {
    previouslyFocused.current = (document.activeElement as HTMLElement) ?? null;
    // Focus the close button so keyboard users land inside the dialog.
    closeButtonRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  // Escape to close + focus trap (Tab / Shift+Tab cycle within the dialog).
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusables = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );
      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !dialog.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose]
  );

  const titleId = `agent-inspector-title-${agent.id}`;

  return (
    <div className="agent-inspector-backdrop" onMouseDown={onClose} data-testid="agent-inspector-backdrop">
      <div
        className="agent-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid={TESTIDS.agentInspector}
        ref={dialogRef}
        onKeyDown={onKeyDown}
        // Clicks inside the drawer must not bubble to the backdrop's close.
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="agent-inspector__head">
          <h2 id={titleId} className="agent-inspector__title">
            Agent Inspector
          </h2>
          <button
            type="button"
            ref={closeButtonRef}
            className="agent-inspector__close"
            data-testid={TESTIDS.agentInspectorClose}
            onClick={onClose}
            aria-label="Close agent inspector"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>

        <dl className="agent-inspector__meta">
          <div className="agent-inspector__meta-row">
            <dt>Agent</dt>
            <dd className="agent-inspector__mono">{agent.id}</dd>
          </div>
          <div className="agent-inspector__meta-row">
            <dt>Status</dt>
            <dd>
              <span
                className={`agent-inspector__status ${statusClass(agent.status)}`}
                data-testid={TESTIDS.agentInspectorStatus}
              >
                <span aria-hidden="true" className="agent-inspector__status-icon">
                  {statusIcon(agent.status)}
                </span>
                <span>{agent.status}</span>
              </span>
            </dd>
          </div>
          <div className="agent-inspector__meta-row">
            <dt>Project</dt>
            <dd>{agent.project}</dd>
          </div>
          <div className="agent-inspector__meta-row">
            <dt>Runtime</dt>
            <dd>{formatRuntime(agent.runtimeSeconds)}</dd>
          </div>
          <div className="agent-inspector__meta-row">
            <dt>Tokens used</dt>
            <dd>
              {typeof agent.tokensUsed === 'number' ? agent.tokensUsed.toLocaleString() : 'unknown'}
            </dd>
          </div>
          <div className="agent-inspector__meta-row">
            <dt>Task</dt>
            <dd>{agent.taskLabel}</dd>
          </div>
          {state === 'ready' && detail && (
            <>
              <div className="agent-inspector__meta-row">
                <dt>Model</dt>
                <dd className="agent-inspector__mono">{detail.model}</dd>
              </div>
              <div className="agent-inspector__meta-row">
                <dt>Dispatcher</dt>
                <dd>{detail.dispatcher}</dd>
              </div>
              <div className="agent-inspector__meta-row">
                <dt>Messages</dt>
                <dd>{detail.message_count.toLocaleString()}</dd>
              </div>
            </>
          )}
        </dl>

        {state === 'ready' && detail && detail.dispatch_prompt && (
          <section className="agent-inspector__section" aria-label="Dispatch prompt">
            <h3>Dispatch prompt</h3>
            <pre className="agent-inspector__prompt">{detail.dispatch_prompt}</pre>
          </section>
        )}

        <section className="agent-inspector__section" aria-label="Transcript tail">
          <h3>
            Transcript tail
            {state === 'ready' && detail?.tail_truncated ? (
              <span className="agent-inspector__truncated"> (last {detail.transcript_tail.length} lines)</span>
            ) : null}
          </h3>

          {state === 'loading' && (
            <div className="agent-inspector__callout" role="status" data-testid={TESTIDS.agentInspectorLoading}>
              Loading transcript{'…'}
            </div>
          )}

          {state === 'error' && (
            <div className="agent-inspector__callout agent-inspector__callout--error" role="alert" data-testid={TESTIDS.agentInspectorError}>
              Could not load agent detail: {errorMsg ?? 'Unknown error'}
            </div>
          )}

          {state === 'ready' && detail && detail.transcript_tail.length === 0 && (
            <div className="agent-inspector__callout" role="status" data-testid={TESTIDS.agentInspectorEmpty}>
              No transcript lines to show.
            </div>
          )}

          {state === 'ready' && detail && detail.transcript_tail.length > 0 && (
            <ol className="agent-inspector__transcript" data-testid={TESTIDS.agentInspectorTranscript}>
              {detail.transcript_tail.map((entry, i) => (
                <li key={i} className="agent-inspector__tail-entry" data-testid={TESTIDS.agentInspectorTail}>
                  <span className={`agent-inspector__tail-type agent-inspector__tail-type--${entry.type}`}>
                    {entry.type}
                  </span>
                  <pre className="agent-inspector__tail-text">{entry.text}</pre>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}

export default AgentInspector;
