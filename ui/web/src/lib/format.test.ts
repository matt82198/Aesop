import { describe, it, expect } from 'vitest';
import { formatAge, formatTokens, formatTimestamp, formatCurrency, formatPercent, capitalize } from './format';

describe('formatAge', () => {
  it('returns unknown for negative ages', () => {
    expect(formatAge(-1)).toBe('unknown');
  });

  it('formats seconds', () => {
    expect(formatAge(0)).toBe('0s');
    expect(formatAge(45)).toBe('45s');
  });

  it('formats minutes with seconds remainder', () => {
    expect(formatAge(90)).toBe('1m 30s');
    expect(formatAge(120)).toBe('2m');
  });

  it('formats hours with minutes remainder', () => {
    expect(formatAge(3600)).toBe('1h');
    expect(formatAge(3660)).toBe('1h 1m');
  });

  it('formats days with hours remainder', () => {
    expect(formatAge(86400)).toBe('1d');
    expect(formatAge(86400 + 3 * 3600)).toBe('1d 3h');
  });
});

describe('formatTokens', () => {
  it('leaves small counts alone', () => {
    expect(formatTokens(0)).toBe('0');
    expect(formatTokens(999)).toBe('999');
  });

  it('formats thousands', () => {
    expect(formatTokens(1000)).toBe('1K');
    expect(formatTokens(1200)).toBe('1.2K');
    expect(formatTokens(999999)).toBe('999K');
  });

  it('formats millions', () => {
    expect(formatTokens(1000000)).toBe('1M');
    expect(formatTokens(1500000)).toBe('1.5M');
  });
});

describe('formatTimestamp', () => {
  it('says now for very recent timestamps', () => {
    expect(formatTimestamp(new Date().toISOString())).toBe('now');
  });

  it('formats minutes ago', () => {
    const t = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatTimestamp(t)).toBe('5m ago');
  });

  it('formats hours ago', () => {
    const t = new Date(Date.now() - 3 * 3600 * 1000).toISOString();
    expect(formatTimestamp(t)).toBe('3h ago');
  });

  it('returns input on unparseable strings', () => {
    // new Date('garbage') is Invalid Date; formatter must not throw
    const out = formatTimestamp('garbage');
    expect(typeof out).toBe('string');
  });
});

describe('formatCurrency', () => {
  it('formats dollars with two decimals', () => {
    expect(formatCurrency(1.234)).toBe('$1.23');
    expect(formatCurrency(0)).toBe('$0.00');
  });
});

describe('formatPercent', () => {
  it('formats fraction as percentage with one decimal', () => {
    expect(formatPercent(0.456)).toBe('45.6%');
    expect(formatPercent(1)).toBe('100.0%');
  });
});

describe('capitalize', () => {
  it('capitalizes first letter', () => {
    expect(capitalize('running')).toBe('Running');
    expect(capitalize('')).toBe('');
  });
});
