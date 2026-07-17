/**
 * Wave Telemetry Cost Scorecard — shows tokens spent, top model, and OK rate for the wave.
 *
 * Displays:
 * - Tokens spent this wave
 * - Top model by token usage
 * - OK-rate (verdict success rate)
 *
 * Reads from GET /api/wave/telemetry at call time (no caching).
 */

import { useEffect, useState } from 'react';
import { fetchApi } from '../lib/api';
import { formatPercent } from '../lib/format';
import { TESTIDS } from '../test/fixtures';
import './WaveTelemetryCost.css';

interface WaveTelemetry {
  wave: string;
  phase: string;
  blocker: string;
  tokens_used: number;
  top_model: string;
  ok_rate: number;
}

export function WaveTelemetryCost() {
  const [telemetry, setTelemetry] = useState<WaveTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadTelemetry = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchApi<WaveTelemetry>('/api/wave/telemetry');
        setTelemetry(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load wave cost');
        console.error('[WaveTelemetryCost] Load failed:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTelemetry();
  }, []);

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
      className="wave-telemetry-cost"
      data-testid={TESTIDS.waveTelemetryCost}
      aria-label="Wave cost scorecard"
    >
      <div className="cost-header">
        <h3>Wave Cost</h3>
      </div>

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
