/**
 * QualityScorecards component — per-agent-specialty quality metrics.
 * Shows success rates and retry/repair frequencies in a clear, info-dense table.
 * Displays top rankings by success rate and retry frequency.
 */

import type { QualityScorecardData } from '../lib/types';
import { formatPercent } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './QualityScorecards.css';

interface QualityScorecardsProps {
  quality: QualityScorecardData | null;
}

export function QualityScorecards({ quality }: QualityScorecardsProps) {
  if (!quality) {
    return (
      <div className="quality-scorecards quality-scorecards--loading">
        <p>Loading quality metrics...</p>
      </div>
    );
  }

  const { specialties, top_by_success, top_by_retry, skipped_lines } = quality;

  // If no data, show empty state
  if (!specialties || Object.keys(specialties).length === 0) {
    return (
      <div className="quality-scorecards quality-scorecards--empty">
        <p>No quality data available yet. Ledger data will appear as agents run.</p>
      </div>
    );
  }

  // Determine severity based on success rate
  const getSeverity = (successRate: number): 'ok' | 'warn' | 'error' => {
    if (successRate >= 0.95) return 'ok';
    if (successRate >= 0.80) return 'warn';
    return 'error';
  };

  return (
    <section
      className="quality-scorecards"
      data-testid={TESTIDS.qualityScorecards}
      aria-label="Per-specialty quality metrics"
    >
      <div className="quality-section">
        <h4>By Agent Specialty</h4>
        <table className="quality-table" role="table">
          <thead>
            <tr>
              <th>Specialty</th>
              <th>Runs</th>
              <th>Success Rate</th>
              <th>Repairs</th>
              <th>Retry Freq</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(specialties).map(([agentType, stats]) => (
              <tr key={agentType} className={`quality-row quality-row--${getSeverity(stats.success_rate)}`}>
                <td className="cell-specialty">{agentType}</td>
                <td className="cell-numeric">{stats.total_runs}</td>
                <td className="cell-metric">
                  <span className={`metric metric--${getSeverity(stats.success_rate)}`}>
                    {formatPercent(stats.success_rate)}
                  </span>
                  <span className="metric-detail">({stats.success_count})</span>
                </td>
                <td className="cell-numeric">{stats.repair_count}</td>
                <td className="cell-metric">
                  <span className="metric">{formatPercent(stats.retry_frequency)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {top_by_success && top_by_success.length > 0 && (
        <div className="quality-section">
          <h4>Top by Success Rate</h4>
          <ol className="quality-ranking">
            {top_by_success.slice(0, 5).map((item, idx) => (
              <li key={item.agent_type} className="ranking-item">
                <span className="ranking-place">#{idx + 1}</span>
                <span className="ranking-specialty">{item.agent_type}</span>
                <span className="ranking-metric">
                  {formatPercent(item.success_rate ?? 0)} ({item.total_runs} runs)
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {top_by_retry && top_by_retry.length > 0 && (
        <div className="quality-section">
          <h4>Highest Retry Frequency</h4>
          <ol className="quality-ranking">
            {top_by_retry.slice(0, 5).map((item, idx) => (
              <li key={item.agent_type} className="ranking-item">
                <span className="ranking-place">#{idx + 1}</span>
                <span className="ranking-specialty">{item.agent_type}</span>
                <span className="ranking-metric">
                  {formatPercent(item.retry_frequency ?? 0)} ({item.total_runs} runs)
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {skipped_lines > 0 && (
        <footer className="quality-footer">
          <small>Data quality note: {skipped_lines} line(s) could not be parsed from the ledger.</small>
        </footer>
      )}
    </section>
  );
}
