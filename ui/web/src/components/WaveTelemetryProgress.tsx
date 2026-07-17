/**
 * Wave Telemetry Progress Tile — shows current wave/phase and top blocker.
 *
 * Displays:
 * - Wave number/name (e.g., "wave-rc.2")
 * - Phase (e.g., "rc-1-published-source-available")
 * - Top blocker from AUDIT-BACKLOG.md
 *
 * Reads from GET /api/wave/telemetry at call time (no caching).
 */

import { useEffect, useState } from 'react';
import { fetchApi } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import './WaveTelemetryProgress.css';

interface WaveTelemetry {
  wave: string;
  phase: string;
  blocker: string;
  tokens_used: number;
  top_model: string;
  ok_rate: number;
}

export function WaveTelemetryProgress() {
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
        setError(err instanceof Error ? err.message : 'Failed to load wave telemetry');
        console.error('[WaveTelemetryProgress] Load failed:', err);
      } finally {
        setLoading(false);
      }
    };

    loadTelemetry();
  }, []);

  if (loading) {
    return (
      <section
        className="wave-telemetry-progress"
        data-testid={TESTIDS.waveTelemetryProgress}
        aria-label="Wave progress"
      >
        <div className="wave-progress-header">
          <h3>Wave Progress</h3>
        </div>
        <div className="wave-progress-content">
          <p>Loading wave telemetry...</p>
        </div>
      </section>
    );
  }

  if (error || !telemetry) {
    return (
      <section
        className="wave-telemetry-progress"
        data-testid={TESTIDS.waveTelemetryProgress}
        aria-label="Wave progress"
      >
        <div className="wave-progress-header">
          <h3>Wave Progress</h3>
        </div>
        <div className="wave-progress-content">
          <p className="wave-progress-error">
            {error ? `Error: ${error}` : 'No wave data available'}
          </p>
        </div>
      </section>
    );
  }

  // Normalize phase for display (e.g., "rc-1-published-source-available" → "Published (rc.1)")
  const phaseDisplay = formatPhaseForDisplay(telemetry.phase);

  return (
    <section
      className="wave-telemetry-progress"
      data-testid={TESTIDS.waveTelemetryProgress}
      aria-label="Wave progress"
    >
      <div className="wave-progress-header">
        <h3>Wave Progress</h3>
        <div className="wave-progress-badge">{telemetry.wave}</div>
      </div>

      <div className="wave-progress-content">
        <div className="wave-progress-phase">
          <div className="phase-label">Phase</div>
          <div className="phase-value">{phaseDisplay}</div>
        </div>

        <div className="wave-progress-blocker">
          <div className="blocker-label">Top Blocker</div>
          <div className="blocker-value">{telemetry.blocker}</div>
        </div>
      </div>
    </section>
  );
}

/**
 * Format phase string for display.
 * Examples:
 * - "rc-1-published-source-available" → "Published (rc.1)"
 * - "wave-rc.2: build" → "Build (wave-rc.2)"
 * - "unknown" → "Unknown"
 */
function formatPhaseForDisplay(phase: string): string {
  if (phase === 'unknown' || !phase) {
    return 'Unknown';
  }

  // Extract wave number if present (e.g., "rc-1", "wave-rc.2")
  const waveMatch = phase.match(/(?:wave-)?(\w+[\w.-]*)/i);
  const waveLabel = waveMatch ? ` (${waveMatch[1]})` : '';

  // Capitalize first word
  const words = phase.split(/[-_]/);
  const mainPhase = words[0].charAt(0).toUpperCase() + words[0].slice(1);

  return mainPhase + waveLabel;
}
