/**
 * CostTable component — per-model cost and token summary table.
 * Proper table semantics: caption, thead with scope="col", tbody.
 * Columns: Model | Runs | Tokens In | Tokens Out | Verdicts (OK/FAILED/EMPTY/HUNG) | [Pricing if has_pricing]
 * Dollar columns labeled "estimate" when pricing is available.
 * Uses formatTokens() for readable token display.
 */

import type { CostSummary, CostModelStats } from '../lib/types';
import { formatTokens, formatCurrency } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './CostTable.css';

interface CostTableProps {
  cost: CostSummary;
}

export function CostTable({ cost }: CostTableProps) {
  const { models, has_pricing, estimates_by_model } = cost;
  const modelIds = Object.keys(models).sort();

  return (
    <table className="cost-table" data-testid={TESTIDS.costTable}>
      <caption>Per-model cost and token usage summary</caption>
      <thead>
        <tr>
          <th scope="col">Model</th>
          <th scope="col" className="col-numeric">
            Runs
          </th>
          <th scope="col" className="col-numeric">
            Tokens In
          </th>
          <th scope="col" className="col-numeric">
            Tokens Out
          </th>
          <th scope="col" className="col-numeric">
            OK
          </th>
          <th scope="col" className="col-numeric">
            FAILED
          </th>
          <th scope="col" className="col-numeric">
            EMPTY
          </th>
          <th scope="col" className="col-numeric">
            HUNG
          </th>
          {has_pricing && (
            <>
              <th scope="col" className="col-numeric">
                Input (estimate)
              </th>
              <th scope="col" className="col-numeric">
                Output (estimate)
              </th>
              <th scope="col" className="col-numeric">
                Total (estimate)
              </th>
            </>
          )}
        </tr>
      </thead>
      <tbody>
        {modelIds.map((modelId) => {
          const stats = models[modelId] as CostModelStats;
          const estimate = has_pricing ? estimates_by_model[modelId] : null;

          return (
            <tr key={modelId}>
              <td className="model-name">{modelId}</td>
              <td className="col-numeric">{stats.runs}</td>
              <td className="col-numeric">{formatTokens(stats.tokens_in)}</td>
              <td className="col-numeric">{formatTokens(stats.tokens_out)}</td>
              <td className="col-numeric">{stats.verdicts.OK}</td>
              <td className="col-numeric verdict-failed">{stats.verdicts.FAILED}</td>
              <td className="col-numeric verdict-empty">{stats.verdicts.EMPTY}</td>
              <td className="col-numeric verdict-hung">{stats.verdicts.HUNG}</td>
              {has_pricing && estimate && (
                <>
                  <td className="col-numeric">{formatCurrency(estimate.input_cost)}</td>
                  <td className="col-numeric">{formatCurrency(estimate.output_cost)}</td>
                  <td className="col-numeric col-total">
                    {formatCurrency(estimate.total_cost)}
                  </td>
                </>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
