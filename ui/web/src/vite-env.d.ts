/// <reference types="vite/client" />

interface Window {
  /**
   * CSRF token injected by ui/render.py's sentinel substitution in the built
   * index.html; absent on the raw Vite dev server (api.ts then falls back to
   * GET /api/session).
   */
  __AESOP_CSRF_TOKEN__?: string;
}
