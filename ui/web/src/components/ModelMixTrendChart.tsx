/**
 * ModelMixTrendChart component — per-day model usage distribution visualization.
 * Shows the percentage breakdown of model usage over time using stacked bars.
 * Pure SVG implementation with no external chart libraries.
 */

import type { CostSummary } from '../lib/types';
import { TESTIDS } from '../test/fixtures';
import './ModelMixTrendChart.css';

interface ModelMixTrendChartProps {
  cost: CostSummary;
}

// Define a set of distinct colors for different models
const MODEL_COLORS: Record<string, string> = {
  'claude-haiku-4-5-20251001': '#60a5fa',
  'claude-sonnet-4-20250514': '#fbbf24',
  'claude-opus-4-1': '#34d399',
  'claude-opus-4': '#34d399',
};

function getModelColor(modelId: string): string {
  if (MODEL_COLORS[modelId]) {
    return MODEL_COLORS[modelId];
  }

  // Generate a consistent color for unknown models based on hash
  let hash = 0;
  for (let i = 0; i < modelId.length; i++) {
    hash = (hash << 5) - hash + modelId.charCodeAt(i);
    hash = hash & hash; // Convert to 32bit integer
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 50%)`;
}

export function ModelMixTrendChart({ cost }: ModelMixTrendChartProps) {
  const { model_mix_trend, overall_scorecard } = cost;
  const days = Object.keys(model_mix_trend || {}).sort();

  if (days.length === 0 || overall_scorecard.total_runs === 0) {
    return (
      <div className="model-mix-empty" data-testid={TESTIDS.modelMixChart}>
        <p className="chart-empty-message">No model mix data yet</p>
      </div>
    );
  }

  // Collect all unique models
  const allModels = new Set<string>();
  days.forEach((day) => {
    const dayDist = model_mix_trend[day];
    Object.keys(dayDist).forEach((model) => allModels.add(model));
  });
  const modelList = Array.from(allModels).sort();

  // SVG dimensions
  const SVG_WIDTH = 600;
  const SVG_HEIGHT = 250;
  const CHART_MARGIN = 40;
  const CHART_AREA_WIDTH = SVG_WIDTH - CHART_MARGIN * 2;
  const CHART_AREA_HEIGHT = SVG_HEIGHT - CHART_MARGIN * 2;
  const BAR_WIDTH = Math.max(10, CHART_AREA_WIDTH / (days.length * 1.5));
  const BAR_GROUP_SPACING = BAR_WIDTH * 1.5;

  return (
    <div className="model-mix-wrapper" data-testid={TESTIDS.modelMixChart}>
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="model-mix-chart-svg"
        role="img"
        aria-label="Daily model usage distribution"
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
          %
        </text>

        {/* Stacked bars for each day */}
        {days.map((day, i) => {
          const dayDist = model_mix_trend[day];
          const xPos = CHART_MARGIN + i * BAR_GROUP_SPACING;
          const barX = xPos + BAR_WIDTH * 0.15;

          let yOffset = SVG_HEIGHT - CHART_MARGIN; // Start from bottom

          return (
            <g key={day} className="bar-group">
              {/* Stacked segments for each model */}
              {modelList.map((model) => {
                const percentage = dayDist[model] || 0;
                const segmentHeight = (percentage / 100) * CHART_AREA_HEIGHT;

                // Calculate segment position
                const segmentY = yOffset - segmentHeight;
                yOffset = segmentY;

                return (
                  <rect
                    key={`${day}-${model}`}
                    x={barX}
                    y={segmentY}
                    width={BAR_WIDTH * 0.7}
                    height={segmentHeight}
                    className="bar-segment"
                    style={{ fill: getModelColor(model) }}
                    data-day={day}
                    data-model={model}
                  >
                    <title>
                      {day}: {model} {percentage.toFixed(1)}%
                    </title>
                  </rect>
                );
              })}

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
          {modelList.slice(0, 4).map((model, idx) => {
            const x = SVG_WIDTH - 250;
            const y = 15 + idx * 20;

            // Extract short model name
            const shortName = model
              .replace('claude-', '')
              .replace(/-\d{10}$/, '')
              .split('-')[0]
              .substring(0, 8);

            return (
              <g key={model}>
                <rect
                  x={x}
                  y={y}
                  width={12}
                  height={12}
                  style={{ fill: getModelColor(model) }}
                />
                <text x={x + 18} y={y + 10} className="legend-text">
                  {shortName}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="model-mix-note">
        <p>Daily model distribution showing percentage breakdown by model type</p>
      </div>
    </div>
  );
}
