/**
 * lock.mjs — Fail-closed atomic lock acquisition for PROPOSALS.md
 *
 * Provides atomic lock operations (mkdir-based) with:
 * - Exponential backoff (configurable base delay, default 10ms)
 * - Configurable timeout (env var AESOP_LOCK_TIMEOUT_MS or config, default 30s)
 * - Stale lock detection and breaking (locks older than 10min are stale)
 * - Fail-closed: throws on timeout instead of proceeding unlocked
 *
 * Usage:
 *   import { acquireLock, releaseLock } from './lock.mjs';
 *   const lock = acquireLock(proposalsFile);
 *   try { ... } finally { releaseLock(lock); }
 */

import fs from 'node:fs';
import path from 'node:path';

// Configuration: precedence env > default
const LOCK_BASE_DELAY_MS = parseInt(process.env.AESOP_LOCK_BASE_DELAY_MS || '10', 10);
const LOCK_TIMEOUT_MS = parseInt(process.env.AESOP_LOCK_TIMEOUT_MS || '30000', 10); // 30s default
const STALE_LOCK_THRESHOLD = 10 * 60 * 1000; // 10 minutes

/**
 * Acquire an atomic lock directory for a file.
 * Implements exponential backoff + stale lock breaking.
 *
 * @param {string} filePath - Path to the file to lock (lock dir is {filePath}.lock)
 * @param {Object} opts - Optional: { timeoutMs: number }
 * @returns {string} Lock directory path
 * @throws {Error} On timeout (fail-closed; never returns null/undefined on success)
 */
export function acquireLock(filePath, opts = {}) {
  const lockDir = filePath + '.lock';
  const lockMarkerFile = path.join(lockDir, 'pid-timestamp.txt');
  const timeoutMs = opts.timeoutMs !== undefined ? opts.timeoutMs : LOCK_TIMEOUT_MS;
  const startTime = Date.now();

  let attempt = 0;

  while (true) {
    const elapsedMs = Date.now() - startTime;
    if (elapsedMs >= timeoutMs) {
      // Timeout exceeded; throw with diagnostics
      let diagnostic = '';
      try {
        if (fs.existsSync(lockDir)) {
          const markerPath = path.join(lockDir, 'pid-timestamp.txt');
          const content = fs.readFileSync(markerPath, 'utf8').trim();
          const lines = content.split('\n');
          if (lines.length >= 2) {
            const holderPid = lines[0];
            const holderAge = Date.now() - parseInt(lines[1], 10) * 1000;
            diagnostic = ` (holder pid: ${holderPid}, lock age: ${Math.round(holderAge / 1000)}s)`;
          }
        }
      } catch {
        // Ignore diagnostics errors
      }
      throw new Error(
        `Failed to acquire ${path.basename(filePath)}.lock after ${timeoutMs}ms${diagnostic}`
      );
    }

    try {
      fs.mkdirSync(lockDir, { exclusive: true });
      // Lock acquired; write pid+timestamp for staleness detection
      const lockMarker = `${process.pid}\n${Math.floor(Date.now() / 1000)}\n`;
      try {
        fs.writeFileSync(lockMarkerFile, lockMarker, 'utf8');
      } catch {
        // Marker write failed, but lock is held; continue
      }
      return lockDir;
    } catch (e) {
      if (e.code === 'EEXIST') {
        // Lock exists; check if it's stale
        try {
          const markerPath = path.join(lockDir, 'pid-timestamp.txt');
          const markerContent = fs.readFileSync(markerPath, 'utf8').trim();
          const lines = markerContent.split('\n');
          if (lines.length >= 2) {
            const lockEpoch = parseInt(lines[1], 10);
            const lockAge = Date.now() - lockEpoch * 1000;
            if (lockAge > STALE_LOCK_THRESHOLD) {
              // Stale lock detected; warn and reclaim it
              console.error(
                `Warning: Stale lock detected for ${path.basename(filePath)} (age: ${Math.round(lockAge / 1000)}s); breaking lock`
              );
              try {
                fs.rmSync(lockDir, { recursive: true, force: true });
              } catch {
                // Cleanup failed; will retry or timeout
              }
              // Retry immediately after cleanup
              attempt++;
              continue;
            }
          }
        } catch {
          // Could not read marker; assume lock is active
        }

        // Lock is held; wait and retry with exponential backoff
        attempt++;
        const delayMs = LOCK_BASE_DELAY_MS * Math.pow(2, Math.min(attempt - 1, 5)); // Cap exponential growth at 2^5 = 32x
        const start = Date.now();
        while (Date.now() - start < delayMs && Date.now() - startTime < timeoutMs) {
          // Busy-wait for calculated backoff delay
        }
      } else {
        throw e;
      }
    }
  }
}

/**
 * Release an atomic lock directory (must be owned by this process).
 * Verifies pid ownership before deletion (fail-safe: won't delete locks from other processes).
 *
 * @param {string|null} lockDir - Lock directory path (safe to pass null)
 */
export function releaseLock(lockDir) {
  if (!lockDir) {
    return;
  }

  try {
    const markerFile = path.join(lockDir, 'pid-timestamp.txt');
    let shouldDelete = false;

    try {
      const markerContent = fs.readFileSync(markerFile, 'utf8').trim();
      const lines = markerContent.split('\n');
      if (lines.length >= 1) {
        const lockPid = lines[0];
        if (lockPid === String(process.pid)) {
          shouldDelete = true;
        }
      }
    } catch {
      // If we can't read the marker, don't delete (fail-safe)
    }

    if (shouldDelete) {
      fs.rmSync(lockDir, { recursive: true, force: true });
    }
  } catch {
    // Ignore cleanup errors
  }
}
