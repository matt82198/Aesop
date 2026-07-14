/**
 * Formatting utilities for display values.
 */

/**
 * Format age in seconds as human-readable string.
 * Examples: "2s", "1m 30s", "2h", "1d 3h"
 */
export function formatAge(ageSeconds: number): string {
  if (ageSeconds < 0) return 'unknown';
  if (ageSeconds < 60) return `${ageSeconds}s`;
  if (ageSeconds < 3600) {
    const minutes = Math.floor(ageSeconds / 60);
    const seconds = ageSeconds % 60;
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  if (ageSeconds < 86400) {
    const hours = Math.floor(ageSeconds / 3600);
    const minutes = Math.floor((ageSeconds % 3600) / 60);
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  const days = Math.floor(ageSeconds / 86400);
  const hours = Math.floor((ageSeconds % 86400) / 3600);
  return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
}

/**
 * Format token count as human-readable string.
 * Examples: "123", "1.2K", "1.5M"
 */
export function formatTokens(count: number): string {
  if (count < 1000) return String(count);
  if (count < 1000000) {
    const k = (count / 1000).toFixed(1);
    return k.endsWith('.0') ? `${Math.floor(count / 1000)}K` : `${k}K`;
  }
  const m = (count / 1000000).toFixed(1);
  return m.endsWith('.0') ? `${Math.floor(count / 1000000)}M` : `${m}M`;
}

/**
 * Format ISO 8601 timestamp as relative time or date.
 * Examples: "now", "2m ago", "Today 14:30", "Jan 15 2026"
 */
export function formatTimestamp(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 0) {
      // Today
      const hours = String(date.getHours()).padStart(2, '0');
      const mins = String(date.getMinutes()).padStart(2, '0');
      return `Today ${hours}:${mins}`;
    }
    if (diffDays < 365) {
      // This year: "Jan 15 14:30"
      const monthStr = date.toLocaleString('en-US', { month: 'short' });
      const day = date.getDate();
      const hours = String(date.getHours()).padStart(2, '0');
      const mins = String(date.getMinutes()).padStart(2, '0');
      return `${monthStr} ${day} ${hours}:${mins}`;
    }
    // Different year: "Jan 15 2025"
    const monthStr = date.toLocaleString('en-US', { month: 'short' });
    const day = date.getDate();
    const year = date.getFullYear();
    return `${monthStr} ${day} ${year}`;
  } catch (err) {
    return isoString;
  }
}

/**
 * Format currency amount.
 * Examples: "$1.23", "$0.01", "$123.45"
 */
export function formatCurrency(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

/**
 * Format percentage with one decimal.
 * Examples: "45.6%", "100.0%"
 */
export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

/**
 * Capitalize first letter of string.
 */
export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
