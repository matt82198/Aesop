/**
 * Timeline — Horizontal per-agent bars from startedAt/lastActivity/runtimeSeconds.
 * Bars are status-colored via theme tokens. Includes sensible clamping for edge cases.
 */

import { formatAge } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import type { Agent } from '../lib/types';
import styles from './Timeline.module.css';

interface Props {
  agents: Agent[];
}

// Status to CSS class mapping
function getStatusClass(status: string): string {
  if (status === 'running') return 'status-ok';
  if (status === 'idle') return 'status-info';
  if (status === 'SUSPICIOUS' || status === 'HIGH') return 'status-error';
  if (status === 'DRIFT' || status === 'MED') return 'status-warn';
  return 'status-neutral';
}

// Compute bar width percentage based on time span
function computeBarWidth(startedAt: string | null, lastActivity: string | null, runtimeSeconds: number): number {
  // If we have both timestamps, use them to compute the span
  if (startedAt && lastActivity) {
    try {
      const start = new Date(startedAt).getTime();
      const end = new Date(lastActivity).getTime();
      const span = (end - start) / 1000; // convert to seconds

      if (span > 0) {
        // Progress from start to end relative to runtime
        const progress = Math.min(span / Math.max(runtimeSeconds, 1), 1);
        return Math.max(5, Math.min(100, progress * 100)); // Clamp between 5% and 100%
      }
    } catch (err) {
      // Fall through to runtime-based calculation
    }
  }

  // Fallback: use runtimeSeconds to estimate visibility
  if (runtimeSeconds > 0) {
    // Clamp very large values
    const clamped = Math.min(runtimeSeconds, 86400); // Max 1 day
    return Math.max(5, Math.min(100, (clamped / 3600) * 10)); // Normalize to 5-100%
  }

  return 10; // Default minimum width
}

export default function Timeline({ agents }: Props) {
  if (agents.length === 0) {
    return (
      <div data-testid={TESTIDS.timeline} className={styles.container}>
        <h3 className={styles.title}>Agent Timeline</h3>
        <div className={styles.emptyState}>(no agents)</div>
      </div>
    );
  }

  return (
    <div data-testid={TESTIDS.timeline} className={styles.container}>
      <h3 className={styles.title}>Agent Timeline</h3>
      <div className={styles.timelineContent}>
        {agents.map((agent) => {
          const barWidth = computeBarWidth(agent.startedAt, agent.lastActivity, agent.runtimeSeconds);
          const statusClass = getStatusClass(agent.status);
          const duration = formatAge(agent.runtimeSeconds);

          return (
            <div key={agent.id} className={styles.row}>
              <div className={styles.rowLabel}>
                <span className={styles.agentId}>{agent.id}</span>
                <span className={styles.agentStatus}>{agent.status}</span>
              </div>
              <div className={styles.barContainer}>
                <div
                  data-testid={TESTIDS.timelineBar}
                  className={`${styles.bar} ${styles[statusClass]}`}
                  style={{ width: `${barWidth}%` }}
                  aria-label={`Agent ${agent.id} (${agent.status}, ${duration})`}
                  role="presentation"
                />
              </div>
              <div className={styles.rowDuration}>{duration}</div>
            </div>
          );
        })}
      </div>
      <div className={styles.footer}>
        <span className={styles.legend}>
          Green = running · Blue = idle · Orange = warn/drift · Red = error/suspicious
        </span>
      </div>
    </div>
  );
}
