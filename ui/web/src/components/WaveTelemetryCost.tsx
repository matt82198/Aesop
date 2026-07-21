/**
 * Wave Telemetry Cost Scorecard — shows tokens spent, top model, OK rate, and live burn rate.
 *
 * Displays:
 * - Tokens spent this wave
 * - Top model by token usage
 * - OK-rate (verdict success rate)
 * - Tokens burned per minute (NEW)
 * - Projected total at current rate (NEW)
 * - Visual alert when over cost_ceiling (NEW)
 *
 * Polls GET /api/wave/telemetry every ~5s to show live burn rate during a wave.
 * Accepts optional fetcher prop for dependency injection in tests.
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { fetchApi as defaultFetcher } from '../lib/api';
import { formatPercent } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './WaveTelemetryCost.css';

const POLL_INTERVAL_MS = 5000; // 5 seconds

interface WaveTelemetry {
  wave: string;
  phase: string;
  blocker: string;
  tokens_used: number;
  top_model: string;
  ok_rate: number;
  tokens_burned_per_min?: number;
  projected_total_tokens?: number;
  cost_ceiling_exceeded?: boolean;
}

interface WaveTelemetryCostProps {
  fetcher?: (path: string) => Promise<WaveTelemetry>;
}

export function WaveTelemetryCost({ fetcher = defaultFetcher }: WaveTelemetryCostProps) {
  const [telemetry, setTelemetry] = useState<WaveTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTelemetry = useCallback(async () => {
    try {
      setError(null);
      const data = await fetcher('/api/wave/telemetry');
      setTelemetry(data);
      if (loading) {
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load wave cost');
      console.error('[WaveTelemetryCost] Load failed:', err);
      if (loading) {
        setLoading(false);
      }
    }
  }, [fetcher, loading]);

  useEffect(() => {
    // Fetch immediately on mount
    loadTelemetry();
    // Set up polling interval
    pollTimerRef.current = setInterval(loadTelemetry, POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [loadTelemetry]);

  if (loading) {
    return (
      <section
        className="wave-telemetry-cost"
        data-testid={TESTIDS.waveTelemetryCost}
        aria-label="Wave cost scorecard"
      >
        <div className="cost-header">
          <h3>Wave Cost</h3>
        </div>
        <div className="cost-content">
          <p>Loading wave cost...</p>
        </div>
      </section>
    );
  }

  if (error || !telemetry) {
    return (
      <section
        className="wave-telemetry-cost"
        data-testid={TESTIDS.waveTelemetryCost}
        aria-label="Wave cost scorecard"
      >
        <div className="cost-header">
          <h3>Wave Cost</h3>
        </div>
        <div className="cost-content">
          <p className="cost-error">
            {error ? `Error: ${error}` : 'No cost data available'}
          </p>
        </div>
      </section>
    );
  }

  // Format model name for display (e.g., "20251001" → "Haiku")
  const modelDisplay = formatModelName(telemetry.top_model);

  return (
    <section
      className={`wave-telemetry-cost ${
        telemetry.cost_ceiling_exceeded ? 'wave-telemetry-cost--alert' : ''
      }`}
      data-testid={TESTIDS.waveTelemetryCost}
      aria-label="Wave cost scorecard"
    >
      <div className="cost-header">
        <h3>Wave Cost</h3>
        {telemetry.cost_ceiling_exceeded && (
          <div
            className="cost-alert-badge"
            title="Over cost ceiling"
            aria-label="Cost ceiling exceeded alert"
          >
            ! Alert
          </div>
        )}
      </div>

      {telemetry.cost_ceiling_exceeded && (
        <div className="cost-ceiling-warning">
          Cost ceiling exceeded - wave may need review
        </div>
      )}

      <div className="cost-grid">
        <article className="cost-tile cost-tile--tokens">
          <div className="tile-label">Tokens Used</div>
          <div className="tile-value">{formatTokens(telemetry.tokens_used)}</div>
          <div className="tile-unit">this wave</div>
        </article>

        <article className="cost-tile cost-tile--model">
          <div className="tile-label">Top Model</div>
          <div className="tile-value">{modelDisplay}</div>
          <div className="tile-unit">by usage</div>
        </article>

        <article className="cost-tile cost-tile--okrate">
          <div className="tile-label">OK Rate</div>
          <div className="tile-value">{formatPercent(telemetry.ok_rate)}</div>
          <div className="tile-unit">verdicts</div>
        </article>

        {telemetry.tokens_burned_per_min !== undefined && (
          <article className="cost-tile cost-tile--burnrate">
            <div className="tile-label">Burn Rate</div>
            <div className="tile-value">{formatBurnRate(telemetry.tokens_burned_per_min)}</div>
            <div className="tile-unit">tokens/min</div>
          </article>
        )}

        {telemetry.projected_total_tokens !== undefined && (
          <article className="cost-tile cost-tile--projection">
            <div className="tile-label">Projected Total</div>
            <div className="tile-value">{formatTokens(telemetry.projected_total_tokens)}</div>
            <div className="tile-unit">at current rate</div>
          </article>
        )}
      </div>
    </section>
  );
}

/**
 * Format token count for display (e.g., 1000000 → "1.0M").
 */
function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return (tokens / 1_000_000).toFixed(1) + 'M';
  }
  if (tokens >= 1_000) {
    return (tokens / 1_000).toFixed(1) + 'K';
  }
  return tokens.toString();
}

/**
 * Format burn rate for display (e.g., 12345.6 → "12.3K").
 */
function formatBurnRate(rate: number): string {
  if (rate >= 1_000_000) {
    return (rate / 1_000_000).toFixed(1) + 'M';
  }
  if (rate >= 1_000) {
    return (rate / 1_000).toFixed(1) + 'K';
  }
  // For values less than 1000, return with one decimal place
  return rate.toFixed(1);
}

/**
 * Format model name for display.
 * Examples:
 * - "20251001" → "Haiku"
 * - "claude-sonnet-4-5" → "Sonnet"
 * - "unknown" → "Unknown"
 */
function formatModelName(model: string): string {
  if (!model || model === 'unknown') {
    return 'Unknown';
  }

  // If it's a date-like string (20251001), assume it's from Haiku
  if (/^\d{8}$/.test(model)) {
    return 'Haiku';
  }

  // Extract model name from full id (e.g., "sonnet" from "claude-sonnet-4-5")
  const match = model.match(/(haiku|sonnet|opus)/i);
  if (match) {
    return match[1].charAt(0).toUpperCase() + match[1].slice(1);
  }

  // Capitalize first letter
  return model.charAt(0).toUpperCase() + model.slice(1);
}
