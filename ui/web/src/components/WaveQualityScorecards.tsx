/**
 * Wave Quality Scorecards — polls /api/wave/quality-scorecards for per-specialty metrics.
 * Shows success rates and retry/repair frequencies for agents.
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { fetchApi as defaultFetcher } from '../lib/api';
import { QualityScorecards } from './QualityScorecards';
import type { QualityScorecardData } from '../lib/types';

const POLL_INTERVAL_MS = 10000; // 10 seconds

interface WaveQualityScorecardsProps {
  fetcher?: (path: string) => Promise<QualityScorecardData>;
}

export function WaveQualityScorecards({ fetcher = defaultFetcher }: WaveQualityScorecardsProps) {
  const [quality, setQuality] = useState<QualityScorecardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadQuality = useCallback(async () => {
    try {
      setError(null);
      const data = await fetcher('/api/wave/quality-scorecards');
      setQuality(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load quality metrics');
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    // Initial load
    loadQuality();

    // Poll for updates
    pollTimerRef.current = setInterval(() => {
      loadQuality();
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [loadQuality]);

  if (loading && !quality) {
    return <QualityScorecards quality={null} />;
  }

  if (error) {
    return (
      <div className="quality-scorecards quality-scorecards--error">
        <p>Error loading quality metrics: {error}</p>
      </div>
    );
  }

  return <QualityScorecards quality={quality} />;
}
