/**
 * AlertsPanel — Security alerts with severity styling.
 */

import type { Alert } from '../lib/types';
import { TESTIDS } from '../test/fixtures';
import './AlertsPanel.css';

interface AlertsPanelProps {
  alerts: Alert | null;
}

/**
 * Determine severity level from alert line.
 */
function getSeverity(line: string): 'error' | 'warn' | 'info' {
  if (line.includes('HIGH') || line.includes('SUSPICIOUS')) return 'error';
  if (line.includes('MED') || line.includes('DRIFT')) return 'warn';
  return 'info';
}

/**
 * Get color for severity level.
 */
function getSeverityColor(severity: 'error' | 'warn' | 'info'): string {
  if (severity === 'error') return 'var(--color-status-error)';
  if (severity === 'warn') return 'var(--color-status-warn)';
  return 'var(--color-status-info)';
}

export function AlertsPanel({ alerts }: AlertsPanelProps) {
  const hasAlerts = alerts && alerts.lines.length > 0;

  return (
    <section className="alerts-panel" data-testid={TESTIDS.alertsPanel}>
      <h2>Security Alerts</h2>
      {!hasAlerts ? (
        <p className="empty-state">No alerts.</p>
      ) : (
        <ul className="alerts-panel__list">
          {alerts.lines.map((line, idx) => {
            const severity = getSeverity(line);
            return (
              <li
                key={idx}
                className="alerts-panel__item"
                data-testid={TESTIDS.alertLine}
                data-severity={severity}
                style={{
                  borderLeftColor: getSeverityColor(severity),
                }}
              >
                <span
                  className="alerts-panel__severity"
                  style={{ color: getSeverityColor(severity) }}
                >
                  {severity.toUpperCase()}
                </span>
                <span className="alerts-panel__text">{line}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
