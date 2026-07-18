/**
 * VerdictCostMetrics component — cost-per-outcome metrics display.
 * Shows cost per successful outcome vs. other verdict types.
 * Uses a compact card layout with metric tiles.
 */

import type { CostSummary } from '../lib/types';
import { formatCurrency } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './VerdictCostMetrics.css';

interface VerdictCostMetricsProps {
  cost: CostSummary;
}

export function VerdictCostMetrics({ cost }: VerdictCostMetricsProps) {
  const { verdict_weighted_cost, has_pricing, overall_scorecard } = cost;

  // If no verdicts recorded, show empty state
  if (overall_scorecard.total_runs === 0) {
    return (
      <div className="verdict-cost-empty" data-testid={TESTIDS.verdictCostMetrics}>
        <p className="empty-message">No verdict data available yet</p>
      </div>
    );
  }

  const metrics = [
    {
      label: 'Cost per OK',
      value: verdict_weighted_cost.cost_per_ok,
      count: overall_scorecard.ok_count,
      verdictType: 'ok',
      enabled: overall_scorecard.ok_count > 0,
    },
    {
      label: 'Cost per Failed',
      value: verdict_weighted_cost.cost_per_failed,
      count: overall_scorecard.failed_count,
      verdictType: 'failed',
      enabled: overall_scorecard.failed_count > 0,
    },
    {
      label: 'Cost per Empty',
      value: verdict_weighted_cost.cost_per_empty,
      count: overall_scorecard.empty_count,
      verdictType: 'empty',
      enabled: overall_scorecard.empty_count > 0,
    },
    {
      label: 'Cost per Hung',
      value: verdict_weighted_cost.cost_per_hung,
      count: overall_scorecard.hung_count,
      verdictType: 'hung',
      enabled: overall_scorecard.hung_count > 0,
    },
  ];

  return (
    <div className="verdict-cost-wrapper" data-testid={TESTIDS.verdictCostMetrics}>
      <div className="verdict-cost-grid">
        {metrics.map((metric) => (
          <div
            key={metric.verdictType}
            className={`verdict-cost-tile verdict-tile--${metric.verdictType}${
              !metric.enabled ? ' verdict-tile--disabled' : ''
            }`}
          >
            <div className="tile-label">{metric.label}</div>
            <div className="tile-value">
              {metric.enabled ? (
                <>
                  {has_pricing ? formatCurrency(metric.value) : Math.round(metric.value)}
                  <span className="tile-unit">{has_pricing ? 'USD' : 'tokens'}</span>
                </>
              ) : (
                <span className="tile-disabled">—</span>
              )}
            </div>
            {metric.enabled && (
              <div className="tile-meta">
                {metric.count} outcome{metric.count !== 1 ? 's' : ''}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="verdict-cost-note">
        <p>
          Cost per outcome metric:
          {has_pricing
            ? ' total estimated cost divided by outcome count'
            : ' total token count divided by outcome count (proxy)'}
        </p>
      </div>
    </div>
  );
}
