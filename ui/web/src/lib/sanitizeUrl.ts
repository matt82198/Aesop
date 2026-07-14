/**
 * URL sanitization for safe rendering in anchor tags.
 * Prevents XSS by allowlisting only http: and https: schemes.
 *
 * Semantics ported from the old dashboard.html sanitizeURL():
 * - The URL is parsed with `location.href` as the base, so relative URLs
 *   resolve same-origin (http/https) and are therefore allowed.
 * - Anything whose resolved protocol is not http:/https: (javascript:,
 *   data:, vbscript:, file:, mailto:, ...) is rejected.
 * - Unparseable input is treated as unsafe.
 *
 * Returns the ORIGINAL string when safe (never the resolved form), or null
 * when unsafe so the caller can render an inert, href-less element.
 */

export function sanitizeUrl(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') {
    return null;
  }

  const trimmed = url.trim();
  if (!trimmed) {
    return null;
  }

  try {
    const base =
      typeof location !== 'undefined' ? location.href : 'http://localhost/';
    const parsed = new URL(trimmed, base);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return trimmed;
    }
    return null;
  } catch (err) {
    // Unparseable URL: treat as unsafe.
    return null;
  }
}
