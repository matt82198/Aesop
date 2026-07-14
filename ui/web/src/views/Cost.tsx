/**
 * Cost view — composition of cost table, chart, and scorecard.
 * Shows per-model breakdowns, per-day trends, and verdict quality metrics.
 * When has_pricing=false, shows a "configure pricing" empty-state callout.
 * When has_pricing=true, displays dollar estimates alongside tokens.
 */

import type { CostSummary } from '../lib/types';
import { CostTable } from '../components/CostTable';
import { CostChart } from '../components/CostChart';
import { Scorecard } from '../components/Scorecard';
import { TESTIDS } from '../test/fixtures';
import './Cost.css';

interface CostProps {
  cost: CostSummary;
}

export function Cost({ cost }: CostProps) {
  return (
    <section className="view-cost" data-testid={TESTIDS.viewCost} aria-label="Cost analytics">
      <h2>Cost Analytics</h2>

      {!cost.has_pricing && (
        <div className="cost-callout cost-callout--info" role="status">
          <h3>Configure Pricing</h3>
          <p>
            To see cost estimates, add a <code>pricing</code> map to your{' '}
            <code>aesop.config.json</code> with per-model input and output rates (e.g.{' '}
            <code>{'{input: 0.003, output: 0.015}'}</code>). Without pricing, token counts are
            shown; no estimates are computed.
          </p>
        </div>
      )}

      <div className="cost-layout">
        <div className="cost-section">
          <h3>By Model</h3>
          <CostTable cost={cost} />
        </div>

        <div className="cost-section">
          <h3>Daily Trend</h3>
          <CostChart cost={cost} />
        </div>

        <div className="cost-section">
          <h3>Quality Scorecard</h3>
          <Scorecard cost={cost} />
        </div>
      </div>
    </section>
  );
}
