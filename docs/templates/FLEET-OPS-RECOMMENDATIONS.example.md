# Fleet-Ops Recommendations — machinery fixes for wave open

Rolling, append-only list maintained by the orchestration/fleet-ops monitor.
The buildsystem skill reads this at every wave open (Phase 0.3). Mark items
ADOPTED/REJECTED/IN-PROGRESS with wave number when actioned; do not delete rows.

| # | Date | Source | Severity | Recommendation | Status |
|---|------|--------|----------|----------------|--------|
| 1 | YYYY-MM-DD | [source/agent/session phase] | [HIGH/MED/LOW] | Clear, actionable recommendation describing the problem, suggested fix, and rationale. Include specific file paths or component names where applicable. | OPEN |
| 2 | YYYY-MM-DD | [source/agent/session phase] | [HIGH/MED/LOW] | Second example recommendation with similar detail level. Link to related findings if applicable. | OPEN |
| | | | | | |

## How to Use This Template

1. **Record findings at wave close:** The orchestration monitor appends new rows for every machinery issue or systemic improvement identified.
2. **Mark status transitions:** When a recommendation is adopted (wave-N or PR reference), update Status to `ADOPTED wave-N`. For rejected items, mark `REJECTED wave-N` with brief rationale.
3. **Track implementation:** Use Status column to indicate OPEN (unactioned), IN-PROGRESS (wave-X, assigned to agent/owner), ADOPTED (implemented, wave-Y), or REJECTED (not pursued, wave-Y).
4. **Preserve history:** Never delete rows — the log is append-only. This creates an auditable trail for machinery decisions.

## Notes

- **Source field:** Where did this insight come from? (session coordinator, CI failure, agent forensics, monitor signal, PR review, etc.)
- **Severity:** HIGH = blocks reliable operation or impacts multiple waves; MED = worth addressing in near term; LOW = nice-to-have optimization.
- **Implementation scope:** Recommendations should be specific enough for a developer to act on, but can span multiple waves if complex.
