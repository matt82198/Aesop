/**
 * AuditTailStream — compact live tail of audit/verification outcomes.
 * Shows newest audit backlog items and ledger verdicts.
 * Integrated into the Activity view for visibility into verification findings.
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { fetchWaveAuditTail } from '../lib/api';
import { TESTIDS } from '../test/fixtures';
import styles from './AuditTailStream.module.css';
import type { WaveAuditTailData, WaveAuditTailEvent } from '../lib/types';

interface AuditTailStreamProps {
  containerRef?: React.RefObject<HTMLDivElement>;
  fetcher?: () => Promise<WaveAuditTailData>;
}

const POLL_INTERVAL_MS = 4000; // 4 seconds
const VISIBLE_CHECK_INTERVAL_MS = 500;

// Status emoji rendering helper
function getStatusIcon(status?: string): string {
  switch (status) {
    case '✅':
      return '✅';
    case '🔵':
      return '🔵';
    case '⬜':
      return '⬜';
    case '⏸':
      return '⏸';
    default:
      return '·';
  }
}

// Verdict rendering helper
function getVerdictIcon(verdict?: string): string {
  switch (verdict) {
    case 'OK':
      return '✓';
    case 'FAILED':
      return '✗';
    case 'EMPTY':
      return '○';
    case 'HUNG':
      return '⟳';
    default:
      return '?';
  }
}

// Verdict color class
function getVerdictClass(verdict?: string): string {
  switch (verdict) {
    case 'OK':
      return 'verdict-ok';
    case 'FAILED':
      return 'verdict-failed';
    case 'EMPTY':
      return 'verdict-empty';
    case 'HUNG':
      return 'verdict-hung';
    default:
      return 'verdict-neutral';
  }
}

// Format timestamp for display
function formatTimestamp(ts?: string): string {
  if (!ts) return '';
  try {
    const date = new Date(ts.replace('Z', '+00:00'));
    const now = new Date();
    const seconds = (now.getTime() - date.getTime()) / 1000;

    if (seconds < 60) return `${Math.floor(seconds)}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return date.toLocaleDateString();
  } catch {
    return '';
  }
}

export default function AuditTailStream({
  containerRef,
  fetcher = fetchWaveAuditTail,
}: AuditTailStreamProps) {
  const [auditTail, setAuditTail] = useState<WaveAuditTailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(true);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const visibilityCheckTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAuditTail = useCallback(async () => {
    try {
      const data = await fetcher();
      setAuditTail(data);
      setError(null);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error('[AuditTailStream] fetch error:', err);
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
      fetchAuditTail();
      pollTimerRef.current = setInterval(fetchAuditTail, POLL_INTERVAL_MS);
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
  }, [isVisible, fetchAuditTail]);

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

  if (!auditTail && loading) {
    return (
      <div data-testid={TESTIDS.auditTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Audit Tail</h4>
          <div className={styles.status}>Loading...</div>
        </div>
      </div>
    );
  }

  if (error || !auditTail) {
    return (
      <div data-testid={TESTIDS.auditTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Audit Tail</h4>
        </div>
        <div className={styles.unavailable}>
          {error || 'No data available'}
        </div>
      </div>
    );
  }

  if (!auditTail.available || auditTail.audit_items.length === 0) {
    return (
      <div data-testid={TESTIDS.auditTail} className={styles.container}>
        <div className={styles.header}>
          <h4 className={styles.title}>Audit Tail</h4>
        </div>
        <div className={styles.empty}>(no recent audits)</div>
      </div>
    );
  }

  return (
    <div data-testid={TESTIDS.auditTail} className={styles.container}>
      <div className={styles.header}>
        <h4 className={styles.title}>Audit Tail</h4>
        <div className={styles.timestamp}>
          {new Date(auditTail.at).toLocaleTimeString()}
        </div>
      </div>

      <div className={styles.tailList}>
        {auditTail.audit_items.map((item, idx) => (
          <div
            key={idx}
            data-testid={TESTIDS.auditTailItem}
            className={styles.item}
          >
            {item.type === 'audit_backlog' ? (
              <div className={styles.auditItem}>
                <div className={styles.statusBadge}>
                  {getStatusIcon(item.status)}
                </div>
                <div className={styles.content}>
                  <div className={styles.meta}>
                    <span className={styles.tier}>{item.tier}</span>
                    <span className={styles.tag}>{item.tag}</span>
                    <span className={styles.timeAgo}>
                      {formatTimestamp(item.timestamp)}
                    </span>
                  </div>
                  <div className={styles.title}>{item.title}</div>
                </div>
              </div>
            ) : (
              <div className={styles.verdictItem}>
                <div className={`${styles.verdictBadge} ${styles[getVerdictClass(item.verdict)]}`}>
                  {getVerdictIcon(item.verdict)}
                </div>
                <div className={styles.content}>
                  <div className={styles.meta}>
                    <span className={styles.agent}>{item.agent}</span>
                    <span className={styles.verdict}>{item.verdict}</span>
                    <span className={styles.timeAgo}>
                      {formatTimestamp(item.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
