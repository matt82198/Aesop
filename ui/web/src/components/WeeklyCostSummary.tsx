/**
 * WeeklyCostSummary component — per-week cost rollup display.
 * Shows token usage and estimated costs aggregated by ISO week.
 * Uses proper table semantics with sortable column headers.
 */

import type { CostSummary } from '../lib/types';
import { formatTokens, formatCurrency } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './WeeklyCostSummary.css';

interface WeeklyCostSummaryProps {
  cost: CostSummary;
}

export function WeeklyCostSummary({ cost }: WeeklyCostSummaryProps) {
  const { per_week_costs, has_pricing } = cost;
  const weeks = Object.keys(per_week_costs || {}).sort().reverse();

  if (weeks.length === 0) {
    return (
      <div className="weekly-cost-empty" data-testid={TESTIDS.weeklyCostSummary}>
        <p className="empty-message">No weekly data available yet</p>
      </div>
    );
  }

  return (
    <div className="weekly-cost-wrapper" data-testid={TESTIDS.weeklyCostSummary}>
      <table className="weekly-cost-table">
        <caption>Per-week cost and token usage summary</caption>
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col" className="col-numeric">
              Tokens In
            </th>
            <th scope="col" className="col-numeric">
              Tokens Out
            </th>
            <th scope="col" className="col-numeric">
              Total Tokens
            </th>
            {has_pricing && (
              <th scope="col" className="col-numeric">
                Cost (estimate)
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => {
            const data = per_week_costs[week];
            const totalTokens = data.tokens_in + data.tokens_out;

            return (
              <tr key={week}>
                <td className="week-label">{week}</td>
                <td className="col-numeric">{formatTokens(data.tokens_in)}</td>
                <td className="col-numeric">{formatTokens(data.tokens_out)}</td>
                <td className="col-numeric">{formatTokens(totalTokens)}</td>
                {has_pricing && <td className="col-numeric">{formatCurrency(data.cost)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
