/**
 * HealthHeader — Sticky status header (always visible, D4).
 *
 * Displays: watchdog ALIVE/STALE+age · monitor status · orchestrator
 * activity/phase · running-agents count · unreviewed-alerts count
 * (severity-colored) · SSE connection state · theme toggle · manual refresh.
 *
 * Every cell is a clickable element jumping to its corresponding view (#/overview, #/activity, etc).
 * Props driven by App.tsx; no local state beyond focus/hover.
 */

import { useCallback } from 'react';
import type { HeartbeatStatus, Agent, OrchestratorStatus, Alert, SSEConnectionStatus } from '../lib/types';
import { TESTIDS } from '../test/fixtures';
import './HealthHeader.css';

interface HealthHeaderProps {
  watchdog: HeartbeatStatus | null;
  monitor: HeartbeatStatus | null;
  orchestrator: OrchestratorStatus | null;
  agents: Agent[] | null;
  alerts: Alert | null;
  connectionStatus: SSEConnectionStatus;
  onThemeToggle: () => void;
  onRefresh: () => void;
}

/**
 * Format age in seconds as a readable duration.
 */
function formatAge(ageSeconds: number): string {
  if (ageSeconds < 0) return 'unknown';
  if (ageSeconds < 60) return `${ageSeconds}s`;
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(ageSeconds / 3600);
  return `${hours}h`;
}

/**
 * Determine status color based on alert severity or status.
 */
function getStatusColor(status: string): string {
  if (status === 'HIGH' || status === 'SUSPICIOUS') return 'var(--color-status-error)';
  if (status === 'MED' || status === 'DRIFT') return 'var(--color-status-warn)';
  if (status === 'ALIVE' || status === 'running' || status === 'OK') return 'var(--color-status-ok)';
  if (status === 'STALE') return 'var(--color-status-error)';
  if (status === 'idle') return 'var(--color-status-info)';
  return 'var(--color-status-neutral)';
}

export function HealthHeader({
  watchdog,
  monitor,
  orchestrator,
  agents,
  alerts,
  connectionStatus,
  onThemeToggle,
  onRefresh,
}: HealthHeaderProps) {
  const handleWatchdogClick = useCallback(() => {
    window.location.hash = '#/activity';
  }, []);

  const handleMonitorClick = useCallback(() => {
    window.location.hash = '#/activity';
  }, []);

  const handleOrchestratorClick = useCallback(() => {
    window.location.hash = '#/activity';
  }, []);

  const handleAlertsClick = useCallback(() => {
    window.location.hash = '#/';
  }, []);

  // Determine audit phase badge — the status file signals via phase/activity, not role
  const isAuditPhase =
    orchestrator?.orchestrators.some(
      (o) => o.phase?.toLowerCase().includes('audit') || o.activity?.toLowerCase().includes('audit'),
    ) ?? false;
  const orchestratorActivity =
    orchestrator?.orchestrators.map((o) => o.activity || o.phase).filter(Boolean)[0] ?? 'no active session';

  const agentsCount = agents?.length ?? 0;
  const alertsCount = alerts?.count ?? 0;

  // Determine max severity for alerts color
  let maxAlertSeverity = 'neutral';
  if (alertsCount > 0 && alerts?.lines.length) {
    const firstLine = alerts.lines[0] || '';
    if (firstLine.includes('HIGH') || firstLine.includes('SUSPICIOUS')) {
      maxAlertSeverity = 'error';
    } else if (firstLine.includes('MED') || firstLine.includes('DRIFT')) {
      maxAlertSeverity = 'warn';
    }
  }

  return (
    <header className="health-header" data-testid={TESTIDS.healthHeader} role="banner">
      <div className="health-header__cells">
        {/* Watchdog cell */}
        <button
          type="button"
          className="health-header__cell health-header__cell--watchdog"
          data-testid={TESTIDS.healthWatchdog}
          onClick={handleWatchdogClick}
          aria-label={`Watchdog: ${watchdog?.alive ?? 'unknown'} (age: ${formatAge(watchdog?.age ?? -1)})`}
        >
          <span className="health-header__label">Watchdog</span>
          <span
            className="health-header__status"
            style={{
              color: getStatusColor(watchdog?.alive ?? 'unknown'),
            }}
          >
            {watchdog?.alive ?? 'unknown'}
            {watchdog && watchdog.age >= 0 && ` +${formatAge(watchdog.age)}`}
          </span>
        </button>

        {/* Monitor cell */}
        <button
          type="button"
          className="health-header__cell health-header__cell--monitor"
          data-testid={TESTIDS.healthMonitor}
          onClick={handleMonitorClick}
          aria-label={`Monitor: ${monitor?.alive ?? 'unknown'}`}
        >
          <span className="health-header__label">Monitor</span>
          <span
            className="health-header__status"
            style={{
              color: getStatusColor(monitor?.alive ?? 'unknown'),
            }}
          >
            {monitor?.alive ?? 'unknown'}
          </span>
        </button>

        {/* Orchestrator cell */}
        <button
          type="button"
          className="health-header__cell health-header__cell--orchestrator"
          data-testid={TESTIDS.healthOrchestrator}
          onClick={handleOrchestratorClick}
          aria-label="Orchestrator status"
        >
          <span className="health-header__label">Orchestrator</span>
          {isAuditPhase && (
            <span className="health-header__badge" role="status">
              Audit
            </span>
          )}
          <span className="health-header__status">{orchestratorActivity}</span>
        </button>

        {/* Agents count */}
        <button
          type="button"
          className="health-header__cell health-header__cell--agents"
          data-testid={TESTIDS.healthAgentsCount}
          onClick={handleAlertsClick}
          aria-label={`${agentsCount} agents running`}
        >
          <span className="health-header__label">Agents</span>
          <span className="health-header__count">{agentsCount}</span>
        </button>

        {/* Alerts count */}
        <button
          type="button"
          className="health-header__cell health-header__cell--alerts"
          data-testid={TESTIDS.healthAlertsCount}
          onClick={handleAlertsClick}
          style={{
            color: maxAlertSeverity === 'error' ? 'var(--color-status-error)' : maxAlertSeverity === 'warn' ? 'var(--color-status-warn)' : undefined,
          }}
          aria-label={`${alertsCount} alerts`}
        >
          <span className="health-header__label">Alerts</span>
          <span className="health-header__count">{alertsCount}</span>
        </button>

        {/* SSE status */}
        <span
          className="health-header__cell health-header__cell--sse"
          data-testid={TESTIDS.sseStatus}
          data-status={connectionStatus.status}
          role="status"
          aria-live="polite"
          aria-label={`Connection: ${connectionStatus.status}`}
        >
          <span className="health-header__label">SSE</span>
          <span
            className="health-header__status"
            style={{
              color:
                connectionStatus.status === 'live'
                  ? 'var(--color-status-ok)'
                  : connectionStatus.status === 'reconnecting'
                    ? 'var(--color-status-warn)'
                    : 'var(--color-status-error)',
            }}
          >
            {connectionStatus.status === 'live'
              ? 'Live'
              : connectionStatus.status === 'reconnecting'
                ? 'Reconnecting'
                : 'Error'}
          </span>
        </span>

        {/* Theme toggle */}
        <button
          type="button"
          className="health-header__cell health-header__cell--theme"
          data-testid={TESTIDS.themeToggle}
          onClick={onThemeToggle}
          aria-label="Toggle color theme"
        >
          <span className="health-header__label">Theme</span>
          <span className="health-header__icon">◐</span>
        </button>

        {/* Refresh button */}
        <button
          type="button"
          className="health-header__cell health-header__cell--refresh"
          data-testid={TESTIDS.refreshButton}
          onClick={onRefresh}
          aria-label="Refresh data"
        >
          <span className="health-header__label">Refresh</span>
          <span className="health-header__icon">↻</span>
        </button>
      </div>
    </header>
  );
}
