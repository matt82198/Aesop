/**
 * CostChart component — pure SVG bar chart showing per-day token usage.
 * No external chart libraries; uses SVG primitives (<rect>, <text>, <title>).
 * Responsive via viewBox; theme colors via CSS variables.
 * Handles empty data, single day, and many days gracefully.
 */

import type { CostSummary } from '../lib/types';
import { TESTIDS } from '../test/fixtures';
import './CostChart.css';

interface CostChartProps {
  cost: CostSummary;
}

export function CostChart({ cost }: CostChartProps) {
  const { daily_totals } = cost;
  const days = Object.keys(daily_totals).sort();

  if (days.length === 0) {
    return (
      <div className="chart-empty" data-testid={TESTIDS.costChart}>
        <svg viewBox="0 0 400 200" className="cost-chart-svg">
          <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
            No data
          </text>
        </svg>
      </div>
    );
  }

  // Calculate max for scaling
  const allTokens = days.flatMap((day) => [
    daily_totals[day].tokens_in,
    daily_totals[day].tokens_out,
  ]);
  const maxTokens = Math.max(...allTokens, 1);

  // SVG layout
  const SVG_WIDTH = 600;
  const SVG_HEIGHT = 250;
  const CHART_MARGIN = 40;
  const CHART_AREA_WIDTH = SVG_WIDTH - CHART_MARGIN * 2;
  const CHART_AREA_HEIGHT = SVG_HEIGHT - CHART_MARGIN * 2;
  const BAR_WIDTH = CHART_AREA_WIDTH / (days.length * 2.5);
  const BAR_GROUP_SPACING = BAR_WIDTH * 1.5;

  return (
    <svg
      viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
      className="cost-chart-svg"
      data-testid={TESTIDS.costChart}
      role="img"
      aria-label="Daily token usage by model"
    >
      {/* Axes */}
      <line
        x1={CHART_MARGIN}
        y1={SVG_HEIGHT - CHART_MARGIN}
        x2={SVG_WIDTH - CHART_MARGIN}
        y2={SVG_HEIGHT - CHART_MARGIN}
        className="chart-axis"
      />
      <line
        x1={CHART_MARGIN}
        y1={CHART_MARGIN}
        x2={CHART_MARGIN}
        y2={SVG_HEIGHT - CHART_MARGIN}
        className="chart-axis"
      />

      {/* Y-axis label */}
      <text x={15} y={CHART_MARGIN} className="chart-label-y">
        Tokens
      </text>

      {/* Bars and labels */}
      {days.map((day, i) => {
        const totals = daily_totals[day];
        const totalTokens = totals.tokens_in + totals.tokens_out;
        const barHeight = (totalTokens / maxTokens) * CHART_AREA_HEIGHT;
        const xPos = CHART_MARGIN + i * BAR_GROUP_SPACING;

        return (
          <g key={day} className="bar-group">
            {/* Stacked bar */}
            <g>
              {/* Input tokens (bottom) */}
              <rect
                x={xPos}
                y={SVG_HEIGHT - CHART_MARGIN - (totals.tokens_in / maxTokens) * CHART_AREA_HEIGHT}
                width={BAR_WIDTH * 0.35}
                height={(totals.tokens_in / maxTokens) * CHART_AREA_HEIGHT}
                className="bar-segment bar-input"
                data-day={day}
              >
                <title>
                  {day}: {totals.tokens_in.toLocaleString()} tokens in
                </title>
              </rect>

              {/* Output tokens (top) */}
              <rect
                x={xPos + BAR_WIDTH * 0.4}
                y={SVG_HEIGHT - CHART_MARGIN - barHeight}
                width={BAR_WIDTH * 0.35}
                height={(totals.tokens_out / maxTokens) * CHART_AREA_HEIGHT}
                className="bar-segment bar-output"
                data-day={day}
              >
                <title>
                  {day}: {totals.tokens_out.toLocaleString()} tokens out
                </title>
              </rect>
            </g>

            {/* Date label */}
            <text
              x={xPos + BAR_WIDTH * 0.35}
              y={SVG_HEIGHT - CHART_MARGIN + 20}
              className="chart-label-x"
              textAnchor="middle"
            >
              {day.split('-')[2]}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      <g className="chart-legend">
        <rect x={SVG_WIDTH - 150} y={15} width={12} height={12} className="bar-input" />
        <text x={SVG_WIDTH - 135} y={25} className="legend-text">
          In
        </text>

        <rect x={SVG_WIDTH - 150} y={35} width={12} height={12} className="bar-output" />
        <text x={SVG_WIDTH - 135} y={45} className="legend-text">
          Out
        </text>
      </g>
    </svg>
  );
}
