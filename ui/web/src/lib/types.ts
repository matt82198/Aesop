/**
 * TypeScript types for Aesop UI API contracts.
 * These types are imported by U4–U7 components and must remain stable across the wave.
 */

export interface HeartbeatStatus {
  alive: 'ALIVE' | 'STALE' | 'UNKNOWN' | 'unknown' | 'not running';
  age: number; // seconds, bucketed to 3-second intervals; -1 if unknown
  threshold: number; // seconds until considered stale
}

/**
 * One fleet agent — the JSON emitted by dash/dash-extra.mjs --json
 * (served via GET /api/agents and the `agents` SSE section; also embedded
 * as `agents` inside GET /data).
 * `status`: 'running' | 'idle' age-derived, overridden by security-log
 * severities 'SUSPICIOUS' | 'HIGH' | 'DRIFT' | 'MED'.
 * ui/agents.py de-dupes colliding 13-char ids by suffixing "-2", "-3", ...
 */
export interface Agent {
  id: string;
  project: string;
  status: 'running' | 'idle' | 'SUSPICIOUS' | 'HIGH' | 'DRIFT' | 'MED' | string;
  age_s: number; // seconds since transcript mtime
  hint: string; // label, capped at 60 chars
  startedAt: string | null; // ISO 8601 transcript timestamp
  lastActivity: string | null; // ISO 8601 transcript timestamp
  runtimeSeconds?: number;
  tokensUsed?: number;
  taskLabel: string; // first prompt line, capped at 80 chars
  promptFull?: string;
}

/**
 * GET /agent?id=<id> — dispatch prompt + metadata
 * (ui/agents.py extract_agent_dispatch_prompt).
 * Error responses are {error: string} with 400 (invalid id) or 404 (no transcript).
 */
export interface AgentDetail {
  id: string;
  dispatch_prompt: string;
  dispatcher: 'main thread' | 'parent agent';
  model: string; // "unknown" when not found in transcript
  message_count: number;
  first_seen: number; // epoch seconds (file mtime)
  last_activity: number; // epoch seconds (file mtime)
}

/**
 * One rendered line of an agent transcript tail (GET /api/agent?id=).
 * `text` is a PLAIN string (backend extracts + secret-redacts it); the client
 * renders it as escaped text, never as HTML.
 */
export interface TranscriptTailEntry {
  type: string; // 'user' | 'assistant' | 'system' | 'tool_result' | 'raw' | ...
  text: string;
}

/**
 * GET /api/agent?id=<id> — full agent detail for the Inspector drawer
 * (ui/agents.py get_agent_detail). Superset of AgentDetail: adds the bounded,
 * secret-redacted transcript tail. Error responses are {error: string} with
 * 400 (invalid id) or 404 (no transcript), same as GET /agent.
 */
export interface AgentInspectorDetail {
  id: string;
  dispatch_prompt: string;
  dispatcher: 'main thread' | 'parent agent';
  model: string; // "unknown" when not found in transcript
  message_count: number;
  first_seen: number; // epoch seconds (file mtime)
  last_activity: number; // epoch seconds (file mtime)
  transcript_tail: TranscriptTailEntry[];
  tail_truncated: boolean; // true if the transcript was longer than the tail window
}

/** GET /api/session — CSRF token for same-origin JS (U2 adds this). */
export interface SessionResponse {
  token: string;
}

/** Uniform error payload shape for non-2xx JSON responses. */
export interface ApiError {
  error: string;
}

export interface Alert {
  count: number;
  lines: string[];
}

export interface TrackerItem {
  id: string;
  title: string;
  priority: 'P0' | 'P1' | 'P2';
  status: 'todo' | 'done' | 'in-progress' | 'archived';
  lane: 'proposed' | 'ranked' | 'in-progress' | 'done';
  source: string;
  tags: string[];
  notes: string | null;
  pr_link: string | null;
  created_at: string; // ISO 8601
  completed_at: string | null;
}

/**
 * The `tracker` SSE section and the tracker slice of GET /api/state.
 * NOTE: GET /api/tracker returns a BARE TrackerItem[] array (no wrapper).
 */
export interface TrackerSnapshot {
  items: TrackerItem[];
}

export interface AuditBacklogItem {
  status: '✅' | '🔵' | '⬜' | '⏸';
  tag: string; // e.g., "[sec]"
  title: string;
}

export interface AuditBacklogTier {
  tier: 'P0' | 'P1' | 'P2' | 'Needs decision';
  items: AuditBacklogItem[];
  done: number;
  inflight: number;
  todo: number;
  total: number;
}

export interface AuditBacklog {
  tiers: AuditBacklogTier[];
}

export interface Message {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string; // ISO 8601
}

export interface OrchestratorEntry {
  id?: string;
  role?: string;
  activity?: string;
  phase?: string;
  age_seconds: number;
  stale: boolean;
  updated_at?: string;
}

export interface OrchestratorStatus {
  orchestrators: OrchestratorEntry[];
}

/**
 * Repo status entry from .watchdog-repos.json (list passthrough, or
 * {repo, state} pairs when the file holds an object).
 */
export interface RepoStatus {
  repo?: string;
  state?: unknown;
  [key: string]: unknown;
}

/**
 * GET /data response AND the `data` SSE section.
 * Note: `agents` is present on GET /data only; the SSE `data` section
 * (collectors._snapshot_data) omits it — agents arrive on their own
 * `agents` SSE section.
 */
export interface DashboardData {
  watchdog: HeartbeatStatus;
  monitor: HeartbeatStatus;
  agents?: Agent[];
  repos: RepoStatus[];
  events: string[];
  alerts: Alert;
  messages: Message[];
}

/** POST /submit success response. */
export interface SubmitResponse {
  ok: boolean;
}

export interface FullState {
  data: DashboardData;
  backlog: AuditBacklog;
  agents: Agent[];
  tracker: TrackerSnapshot;
  status: OrchestratorStatus;
  cost?: CostSummary;
}

/**
 * Cost summary from GET /api/cost.
 * Mirrors ui/cost.py get_cost_summary() docstring on branch
 * feat/wave14-u3-cost-collector — verbatim shape, NOT provisional.
 */
export interface CostModelStats {
  runs: number;
  tokens_in: number;
  tokens_out: number;
  verdicts: {
    OK: number;
    FAILED: number;
    EMPTY: number;
    HUNG: number;
  };
}

export interface CostDailyTotal {
  tokens_in: number;
  tokens_out: number;
}

export interface CostOverallScorecard {
  total_runs: number;
  ok_count: number;
  failed_count: number;
  empty_count: number;
  hung_count: number;
  ok_rate: number; // 0.0-1.0
  failed_rate: number;
  empty_rate: number;
  hung_rate: number;
}

export interface CostEstimate {
  input_cost: number; // dollars
  output_cost: number; // dollars
  total_cost: number; // dollars
}

export interface CostSummary {
  models: Record<string, CostModelStats>; // keyed by model id
  daily_totals: Record<string, CostDailyTotal>; // keyed by "YYYY-MM-DD"
  overall_scorecard: CostOverallScorecard;
  skipped_lines: number;
  has_pricing: boolean;
  estimates_by_model: Record<string, CostEstimate>; // empty when has_pricing is false
}

/**
 * One row on the Wave PR Board (GET /api/wave/prs).
 * `has_pr=false` rows are feat/* branches with no open PR yet (number is null).
 * `ci` is a color-independent rollup state paired with an icon+text in the UI.
 */
export interface WavePR {
  number: number | null;
  title: string;
  branch: string;
  url: string;
  ci: 'passing' | 'failing' | 'pending' | 'none';
  mergeable: 'MERGEABLE' | 'CONFLICTING' | 'UNKNOWN' | string;
  is_draft: boolean;
  review_decision: string; // "APPROVED" | "CHANGES_REQUESTED" | "REVIEW_REQUIRED" | ""
  created_at: string; // ISO 8601, "" for branch-only rows
  blocker: string | null;
  has_pr: boolean;
}

/**
 * GET /api/wave/prs response.
 * When `available` is false (gh missing / un-authenticated), `error` carries a
 * human reason and `prs` is empty — the board renders a callout, not a crash.
 */
export interface WavePRBoardData {
  available: boolean;
  error: string | null;
  generated_at: string; // ISO 8601 UTC
  prs: WavePR[];
}

/**
 * One CI job from a workflow run, with an optional log excerpt.
 * Part of the wave failure drill-down (GET /api/wave/failure?pr=N).
 */
export interface WaveFailureJob {
  id: number;
  name: string;
  status: 'completed' | 'in_progress' | 'queued' | string;
  conclusion: 'success' | 'failure' | 'cancelled' | 'timed_out' | null | string;
  url: string;
  log_excerpt: string | null; // ~100 lines tail, null if fetch failed
}

/**
 * One workflow run (the latest run for a PR branch).
 * Part of the wave failure drill-down (GET /api/wave/failure?pr=N).
 */
export interface WaveFailureRun {
  id: string;
  name: string;
  status: 'completed' | 'in_progress' | 'queued' | string;
  conclusion: 'success' | 'failure' | 'cancelled' | 'timed_out' | null | string;
  url: string;
}

/**
 * GET /api/wave/failure?pr=N response.
 * When `available` is false (gh missing / un-authenticated), `error` carries a
 * human reason and `jobs` is empty — the drill-down renders a degraded state,
 * not a crash.
 */
export interface WaveFailureData {
  available: boolean;
  error: string | null;
  pr_number: number;
  branch: string;
  latest_run: WaveFailureRun | null;
  jobs: WaveFailureJob[];
}

/**
 * SSE event sections emitted by GET /events.
 * Initial sections: data, backlog, agents, tracker, status
 * Added in U3: cost
 */
export type SSESection =
  | 'data'
  | 'backlog'
  | 'agents'
  | 'tracker'
  | 'status'
  | 'cost';

export interface SSEConnectionStatus {
  status: 'live' | 'reconnecting' | 'error';
  lastError?: string;
}
