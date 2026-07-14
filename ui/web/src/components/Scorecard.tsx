/**
 * Scorecard component — accessible stat tiles for run verdicts.
 * Displays OK/FAILED/EMPTY/HUNG rates as percentages and counts.
 * Severity coloring uses theme color tokens.
 * Includes skipped_lines footnote when > 0.
 */

import type { CostSummary } from '../lib/types';
import { formatPercent } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './Scorecard.css';

interface ScorecardProps {
  cost: CostSummary;
}

interface StatTile {
  label: string;
  count: number;
  rate: number;
  severity: 'ok' | 'error' | 'warn' | 'neutral';
}

export function Scorecard({ cost }: ScorecardProps) {
  const { overall_scorecard: sc, skipped_lines } = cost;

  const stats: StatTile[] = [
    {
      label: 'OK',
      count: sc.ok_count,
      rate: sc.ok_rate,
      severity: 'ok',
    },
    {
      label: 'FAILED',
      count: sc.failed_count,
      rate: sc.failed_rate,
      severity: 'error',
    },
    {
      label: 'EMPTY',
      count: sc.empty_count,
      rate: sc.empty_rate,
      severity: 'warn',
    },
    {
      label: 'HUNG',
      count: sc.hung_count,
      rate: sc.hung_rate,
      severity: 'error',
    },
  ];

  return (
    <section
      className="scorecard"
      data-testid={TESTIDS.scorecard}
      aria-label="Fleet quality scorecard"
    >
      <header className="scorecard-header">
        <h3>Run Verdict Rates</h3>
        <div className="scorecard-total">Total runs: {sc.total_runs}</div>
      </header>
      <div className="scorecard-tiles">
        {stats.map((stat) => (
          <article
            key={stat.label}
            className={`scorecard-tile scorecard-tile--${stat.severity}`}
          >
            <div className="tile-label">{stat.label}</div>
            <div className="tile-percent">{formatPercent(stat.rate)}</div>
            <div className="tile-count">{stat.count} runs</div>
          </article>
        ))}
      </div>
      {skipped_lines > 0 && (
        <footer className="scorecard-footer">
          <small>
            Data quality note: {skipped_lines} line(s) in the ledger could not be parsed.
          </small>
        </footer>
      )}
    </section>
  );
}
