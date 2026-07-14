import { describe, it, expect } from 'vitest';
import { sanitizeUrl } from './sanitizeUrl';

describe('sanitizeUrl', () => {
  it('allows http URLs', () => {
    const url = 'http://example.com/path';
    expect(sanitizeUrl(url)).toBe(url);
  });

  it('allows https URLs', () => {
    const url = 'https://github.com/owner/repo/pull/123';
    expect(sanitizeUrl(url)).toBe(url);
  });

  it('allows https URLs with query params', () => {
    const url = 'https://example.com/search?q=test&lang=en';
    expect(sanitizeUrl(url)).toBe(url);
  });

  it('allows https URLs with explicit ports', () => {
    const url = 'https://example.com:8443/path';
    expect(sanitizeUrl(url)).toBe(url);
  });

  it('allows http URLs on localhost ports', () => {
    const url = 'http://localhost:8770/data';
    expect(sanitizeUrl(url)).toBe(url);
  });

  it('blocks javascript: URLs', () => {
    expect(sanitizeUrl('javascript:alert("xss")')).toBeNull();
  });

  it('blocks javascript: URLs with mixed case', () => {
    expect(sanitizeUrl('JaVaScRiPt:alert(1)')).toBeNull();
  });

  it('blocks data: URLs', () => {
    expect(sanitizeUrl('data:text/html,<script>alert("xss")</script>')).toBeNull();
  });

  it('blocks vbscript: URLs', () => {
    expect(sanitizeUrl('vbscript:msgbox("xss")')).toBeNull();
  });

  it('blocks mailto: URLs', () => {
    expect(sanitizeUrl('mailto:attacker@example.com')).toBeNull();
  });

  it('blocks file: URLs', () => {
    expect(sanitizeUrl('file:///etc/passwd')).toBeNull();
  });

  it('allows relative paths (resolve same-origin, matching old sanitizeURL)', () => {
    // Old dashboard.html sanitizeURL parses with base location.href, so a
    // relative path resolves to same-origin http and is safe/allowed.
    expect(sanitizeUrl('/path/to/page')).toBe('/path/to/page');
    expect(sanitizeUrl('relative/page')).toBe('relative/page');
  });

  it('returns the original string, not the resolved URL', () => {
    expect(sanitizeUrl('/pr/123')).toBe('/pr/123');
  });

  it('returns null for empty strings', () => {
    expect(sanitizeUrl('')).toBeNull();
    expect(sanitizeUrl('   ')).toBeNull();
  });

  it('returns null for null/undefined', () => {
    expect(sanitizeUrl(null)).toBeNull();
    expect(sanitizeUrl(undefined)).toBeNull();
  });

  it('returns null for non-string input', () => {
    expect(sanitizeUrl(123 as any)).toBeNull();
    expect(sanitizeUrl({} as any)).toBeNull();
  });

  it('trims whitespace before validating', () => {
    const url = '  https://example.com  ';
    expect(sanitizeUrl(url)).toBe('https://example.com');
  });
});
