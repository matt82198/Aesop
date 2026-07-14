/**
 * BacklogPanel — Audit backlog with tier progress bars.
 * Shows done/in-flight/todo counts and a list of items per tier.
 * Handles overflow with fade-out effect, empty state.
 */

import { TESTIDS } from '../test/fixtures';
import type { AuditBacklog } from '../lib/types';

interface BacklogPanelProps {
  backlog: AuditBacklog | null;
}

function statusEmoji(status: string): string {
  switch (status) {
    case '✅':
      return '✅';
    case '🔵':
      return '🔵';
    case '⬜':
      return '⬜';
    case '⏸':
      return '⏸';
    default:
      return '❓';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case '✅':
      return 'Done';
    case '🔵':
      return 'In progress';
    case '⬜':
      return 'To do';
    case '⏸':
      return 'Blocked';
    default:
      return 'Unknown';
  }
}

export function BacklogPanel({ backlog }: BacklogPanelProps) {
  if (!backlog || backlog.tiers.length === 0) {
    return (
      <div className="backlog-panel" data-testid={TESTIDS.backlogPanel}>
        <h3>Audit Backlog</h3>
        <p className="empty-state">No backlog items</p>
      </div>
    );
  }

  return (
    <div className="backlog-panel" data-testid={TESTIDS.backlogPanel}>
      <h3>Audit Backlog</h3>

      {backlog.tiers.map((tier) => {
        const total = tier.total;
        if (total === 0) return null;

        const donePercent = total > 0 ? (tier.done / total) * 100 : 0;
        const inflightPercent = total > 0 ? (tier.inflight / total) * 100 : 0;
        const todoPercent = total > 0 ? (tier.todo / total) * 100 : 0;

        return (
          <div key={tier.tier} className="backlog-tier">
            <div className="tier-header">
              <h4>{tier.tier}</h4>
              <span className="tier-counts">
                {tier.done} done, {tier.inflight} inflight, {tier.todo} todo
              </span>
            </div>

            <div className="tier-progress-bar">
              {tier.done > 0 && (
                <div
                  className="progress-segment done"
                  style={{ width: `${donePercent}%` }}
                  title={`Done: ${tier.done}`}
                  aria-label={`${tier.done} items done`}
                />
              )}
              {tier.inflight > 0 && (
                <div
                  className="progress-segment inflight"
                  style={{ width: `${inflightPercent}%` }}
                  title={`In flight: ${tier.inflight}`}
                  aria-label={`${tier.inflight} items in flight`}
                />
              )}
              {tier.todo > 0 && (
                <div
                  className="progress-segment todo"
                  style={{ width: `${todoPercent}%` }}
                  title={`To do: ${tier.todo}`}
                  aria-label={`${tier.todo} items to do`}
                />
              )}
            </div>

            <div className="tier-items-list">
              {tier.items.map((item, idx) => (
                <div key={idx} className="backlog-item">
                  <span
                    className="item-status"
                    title={statusLabel(item.status)}
                    aria-label={statusLabel(item.status)}
                  >
                    {statusEmoji(item.status)}
                  </span>
                  <span className="item-tag">{item.tag}</span>
                  <span className="item-title">{item.title}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
