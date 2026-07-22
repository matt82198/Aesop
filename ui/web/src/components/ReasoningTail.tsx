/**
 * ReasoningTail — per-agent live reasoning/transcript activity transparency.
 * Shows latest transcript activity summary per live agent (redacted).
 * Integrated into the Activity view for execution transparency.
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { fetchWaveReasoningTail } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import styles from './ReasoningTail.module.css';
import type { WaveReasoningTailData } from '../lib/types';

interface ReasoningTailProps {
  containerRef?: React.RefObject<HTMLDivElement>;
  fetcher?: () => Promise<WaveReasoningTailData>;
}

const POLL_INTERVAL_MS = 2500; // 2.5 seconds
const VISIBLE_CHECK_INTERVAL_MS = 500;

// Phase to color mapping
const PHASE_COLORS: Record<string, string> = {
  dispatch: '#3b82f6',     // blue
  thinking: '#06b6d4',     // cyan
  'tool-use': '#10b981',   // green
  'tool_use': '#10b981',   // green (underscore variant)
  stall: '#f59e0b',        // amber
  done: '#6b7280',         // gray
};

function getPhaseColor(phase: string): string {
  return PHASE_COLORS[phase.toLowerCase()] || '#9ca3af';
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

export default function ReasoningTail({
  containerRef,
  fetcher = fetchWaveReasoningTail,
}: ReasoningTailProps) {
  const [reasoning, setReasoning] = useState<WaveReasoningTailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(true);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const visibilityCheckTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchReasoning = useCallback(async () => {
    try {
      const data = await fetcher();
      setReasoning(data);
      setError(null);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error('[ReasoningTail] fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  const checkVisibility = useCallback(() => {
    if (!containerRef?.current) {
      setIsVisible(true);
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const visible = rect.bottom > 0 && rect.top < window.innerHeight;
    setIsVisible(visible);
  }, [containerRef]);

  useEffect(() => {
    if (isVisible && !pollTimerRef.current) {
      fetchReasoning();
      pollTimerRef.current = setInterval(fetchReasoning, POLL_INTERVAL_MS);
    } else if (!isVisible && pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [isVisible, fetchReasoning]);

  useEffect(() => {
    checkVisibility();
    visibilityCheckTimerRef.current = setInterval(checkVisibility, VISIBLE_CHECK_INTERVAL_MS);
    return () => {
      if (visibilityCheckTimerRef.current) {
        clearInterval(visibilityCheckTimerRef.current);
        visibilityCheckTimerRef.current = null;
      }
    };
  }, [checkVisibility]);

  if (!reasoning && loading) {
    return (
      <div data-testid={TESTIDS.reasoningTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Reasoning Transparency</h4>
          <div className={styles.status}>Loading...</div>
        </div>
      </div>
    );
  }

  if (error || !reasoning) {
    return (
      <div data-testid={TESTIDS.reasoningTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Reasoning Transparency</h4>
        </div>
        <div className={styles.unavailable}>
          {error || 'No data available'}
        </div>
      </div>
    );
  }

  if (!reasoning.available || reasoning.agents.length === 0) {
    return (
      <div data-testid={TESTIDS.reasoningTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Reasoning Transparency</h4>
        </div>
        <div className={styles.empty}>(no active agents)</div>
      </div>
    );
  }

  return (
    <div data-testid={TESTIDS.reasoningTail} className={styles.container}>
      <div className={styles.header}>
        <h4 className={styles.title}>Reasoning Transparency</h4>
        <div className={styles.timestamp}>
          {new Date(reasoning.at).toLocaleTimeString()}
        </div>
      </div>

      <div className={styles.agentsList}>
        {reasoning.agents.map((agent) => (
          <div
            key={agent.id}
            data-testid={TESTIDS.reasoningTailAgent}
            className={styles.agentCard}
          >
            <div className={styles.agentHeader}>
              <div className={styles.agentId}>{agent.id}</div>
              <div
                className={styles.phaseBadge}
                style={{ backgroundColor: getPhaseColor(agent.phase) }}
              >
                {agent.phase}
              </div>
              <div className={styles.age}>{formatAge(agent.activity_age_sec)}</div>
              <div className={styles.tokens}>{(agent.token_estimate / 1000).toFixed(0)}K</div>
            </div>
            <div className={styles.reasoning}>
              {agent.reasoning}
            </div>
            {agent.warnings && agent.warnings.length > 0 && (
              <div className={styles.warnings}>
                {agent.warnings.map((warn, idx) => (
                  <span key={idx} className={styles.warningBadge}>
                    {warn}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
