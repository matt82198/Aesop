/**
 * Vitest setup — jsdom environment extensions shared by all test files.
 */
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Unmount React trees between tests.
afterEach(() => {
  cleanup();
});

// jsdom does not implement EventSource; give tests a minimal stub so code
// under test (useSSE) can construct one without exploding. Tests that need
// to drive SSE events should replace this with their own mock.
if (typeof (globalThis as any).EventSource === 'undefined') {
  class StubEventSource {
    url: string;
    readyState = 0;
    onerror: ((ev: unknown) => void) | null = null;
    onmessage: ((ev: unknown) => void) | null = null;
    onopen: ((ev: unknown) => void) | null = null;
    private listeners = new Map<string, Set<(ev: MessageEvent) => void>>();

    constructor(url: string) {
      this.url = url;
    }

    addEventListener(type: string, cb: (ev: MessageEvent) => void) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type)!.add(cb);
    }

    removeEventListener(type: string, cb: (ev: MessageEvent) => void) {
      this.listeners.get(type)?.delete(cb);
    }

    /** Test helper: dispatch a named SSE event with a JSON payload. */
    emit(type: string, data: string) {
      const ev = new MessageEvent(type, { data });
      this.listeners.get(type)?.forEach((cb) => cb(ev));
    }

    close() {
      this.readyState = 2;
    }
  }
  (globalThis as any).EventSource = StubEventSource;
}
