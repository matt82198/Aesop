import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useHashRoute, normalizeHash, ROUTES } from './useHashRoute';

function setHash(hash: string) {
  window.location.hash = hash;
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

afterEach(() => {
  window.location.hash = '';
});

describe('normalizeHash', () => {
  it('passes through known routes', () => {
    for (const r of ROUTES) {
      expect(normalizeHash(r)).toBe(r);
    }
  });

  it('normalizes empty hash to #/', () => {
    expect(normalizeHash('')).toBe('#/');
  });

  it('normalizes unknown hashes to #/', () => {
    expect(normalizeHash('#/bogus')).toBe('#/');
    expect(normalizeHash('#work')).toBe('#/');
  });
});

describe('useHashRoute', () => {
  it('returns #/ initially with no hash', () => {
    const { result } = renderHook(() => useHashRoute());
    expect(result.current).toBe('#/');
  });

  it('follows hashchange events', () => {
    const { result } = renderHook(() => useHashRoute());
    act(() => setHash('#/work'));
    expect(result.current).toBe('#/work');
    act(() => setHash('#/cost'));
    expect(result.current).toBe('#/cost');
    act(() => setHash('#/activity'));
    expect(result.current).toBe('#/activity');
  });

  it('normalizes unknown hash changes to #/', () => {
    const { result } = renderHook(() => useHashRoute());
    act(() => setHash('#/work'));
    expect(result.current).toBe('#/work');
    act(() => setHash('#/nonsense'));
    expect(result.current).toBe('#/');
  });

  it('reads the initial hash on mount', () => {
    window.location.hash = '#/cost';
    const { result } = renderHook(() => useHashRoute());
    expect(result.current).toBe('#/cost');
  });
});
