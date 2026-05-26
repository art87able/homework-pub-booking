# Ex7 — Handoff bridge

## Your answer

The HandoffBridge orchestrates round-trips between the loop half and
structured half. Each round: loop runs, if next_action=handoff_to_structured
the bridge writes a forward handoff file, invokes structured, and then
either marks the session complete (structured confirmed) or builds a
reverse task and loops back (structured escalated).

The reverse-task path is the interesting one. On escalation, the
bridge rewrites the initial_task into a dict that contains
prior_result + rejection_reason + retry=True. The loop half sees
this via the new executor invocation and — in a real LLM setting —
would produce a different subgoal. In the scripted offline demo we
hardcode the retry choice (royal_oak with 16 seats) so the test is
deterministic.

Every half transition emits a session.state_changed trace event via
session.append_trace_event(). The integrity check (integrity.py)
verifies the trace has at least one round_start, at least one
state_changed, and at least one tool call — catching the case where
the bridge reports success without doing real work.

The stale-handoff cleanup moves old `ipc/input/handoff_to_structured.json`
files into `handoffs_audit_dir/round_<n>_forward.json` instead of
deleting them, satisfying the "at most one handoff file in `ipc/` at
any time" rule while preserving the audit trail.

## Citations

- `starter/handoff_bridge/bridge.py::HandoffBridge.run` — round loop, forward + reverse handoff plumbing, archival of each round's forward handoff
- `starter/handoff_bridge/bridge.py::build_forward_handoff` + `build_reverse_task` — payload constructors
- `starter/handoff_bridge/integrity.py::verify_dataflow` — checks the trace contains `bridge.round_start` + `session.state_changed` + at least one `executor.tool_called`
- `sessions/examples/ex7-handoff-bridge/sess_f972b3090243/logs/trace.jsonl` — successful round-trip: round 1 proposes `haymarket_tap` for party 12, structured half rejects with `party_too_large`, round 2 proposes `royal_oak` for party 6, structured half confirms. `Bridge outcome: completed, rounds: 2`
