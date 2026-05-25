# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

I ran Ex7 several times. The bridge completed in two rounds: round 1
chose `haymarket_tap`, structured rejected (`party=12 > cap=8`), round 2
chose `royal_oak`, structured accepted. So a planner → structured handoff
DID happen — but not where I expected.

Reading the scripted plan in `starter/handoff_bridge/run.py`, the
DefaultPlanner outputs both subgoals with `assigned_half: "loop"`. The
planner never assigns work to structured directly. The handoff to
structured is triggered later, inside the LoopHalf's executor loop, by
a tool call named `handoff_to_structured` (one of the framework
builtins from `sovereign_agent.tools.builtin.make_builtin_registry`).
That tool call is what `HandoffBridge.run` watches for — when the
LoopHalf result reports `next_action == "handoff_to_structured"`, the
bridge swaps active halves by writing
`ipc/input/handoff_to_structured.json` via `write_handoff`.

This matters because it relocates the architectural decision. The
planner stays neutral — it just decomposes work. The executor LLM,
seeing the rule-bound nature of the booking, requests structured help.
The bridge enforces the swap by atomic-rename file IPC (one
`handoff_to_structured.json` per round, archived under
`handoffs_audit_dir` after each reverse handoff), so a crash
mid-transition leaves exactly one of {old half, new half} responsible
for the session.

The broader lesson: planner decisions are advisory categorisation;
tool-call decisions during execution are load-bearing. When debugging
"why didn't structured run," read the executor's tool calls in
`logs/trace.jsonl`, not the planner's subgoal metadata.

### Citation

- `starter/handoff_bridge/run.py` — scripted planner output, both
  subgoals `assigned_half: "loop"`
- `starter/handoff_bridge/bridge.py::HandoffBridge.run` — reads
  `loop_result.next_action` and routes
- A run produces `sessions/<id>/logs/trace.jsonl` with
  `bridge.round_start` (one per round) and `session.state_changed`
  events naming `from`/`to` halves for every transition
- Rejected forward handoffs are preserved under
  `sessions/<id>/handoffs_audit/round_<n>_forward.json`

---

## Q2 — Dataflow integrity catch

### Your answer

My Ex5 offline run (`make ex5`) passed with `dataflow OK: verified 4
fact(s) against tool outputs`. The four facts the check extracted from
the HTML flyer were `£540`, `£0`, `cloudy`, and `12` (temperature). All
appeared in `_TOOL_CALL_LOG` so the check returned `ok=True`.

The interesting observation is HOW they appeared. My `calculate_cost`
returned `total_gbp=556` (formula: 18×6×3 + 10% service + £0 hire +
£200 min_spend), but the flyer showed £540. The check still passed
because the fake-LLM script in `run.py:79-95` passed `total_gbp: 540`
as an argument to `generate_flyer`, and `record_tool_call` logs
arguments too. `fact_appears_in_log` scans both `output` and
`arguments` of every record, so 540 matched the flyer claim via the
`generate_flyer` call's args.

This is exactly the failure mode the check is designed for: an LLM
that fabricates a number can do so anywhere — output of one tool, args
of another, free-text response. By logging both directions of every
tool call, the audit covers all paths the value could have entered
the flyer. The public test
`test_verify_dataflow_catches_obvious_fabrication` plants
`"Total: £9999"` against a log containing only `540` and confirms
`ok=False` with `9999` in `unverified_facts`. I reproduced this
locally as a sanity test.

The reproducible recipe: after any `make ex5` run, sed `£540`→`£9999`
in `<session>/workspace/flyer.html` and call `verify_dataflow(...)` —
it fails with that specific value flagged.

### Citation

- `starter/edinburgh_research/run.py:79-95` — fake-LLM scripts
  `total_gbp: 540` in `generate_flyer` args
- `starter/edinburgh_research/integrity.py:99-112` —
  `fact_appears_in_log` scans both `output` AND `arguments`
- `tests/public/test_ex5_scaffold.py:167-178` —
  `test_verify_dataflow_catches_obvious_fabrication`
- The 4 verified facts in any `make ex5` run trace appear in
  `<session>/logs/trace.jsonl` `tool_call.complete` events

---

## Q3 — First production failure + the primitive that surfaces it

### Your answer

**Primitive:** the ticket state machine — every operation leaves a
permanent, forward-only record under `tickets/`.

**Failure mode:** *phantom double-booking from a retried customer
request.* In production, a customer on a flaky café WiFi will submit
the same booking twice within <2s because their browser/phone retries
the HTTP request after a stalled TCP connection. The loop half spawns
two sessions (different `sess_<hex>` ids, different `sender`s computed
from `hashlib.sha1(f"{venue_id}-{date}-{time}")[:8]` — same suffix
because the booking is identical). Both flow through `confirm_booking`
in Rasa; both pass `party_size <= 8` and `deposit_gbp <= 300`; both
get a deterministic `booking_reference = BK-<sha1(venue|date|time|party)>`
— *the same reference, twice.* The venue's calendar (a downstream
integration outside our process) receives two commit calls naming the
same slot.

The ticket state machine surfaces this because each session writes a
ticket under `tickets/` transitioning `pending → handoff_to_structured
→ committed`, with the booking reference stamped at completion. A
reconciliation cron that scans `sessions/*/tickets/*.json` for
duplicate `booking_reference` values across distinct `session_id`s
catches the phantom-double within one cron cycle — no app-level
deduplication required. Without that durable, forward-only trail,
you'd discover the double-booking only when the customer arrives at a
pub that's already full.

The proper fix is a venue-side lease (only one party can hold a slot,
the second commit returns 409). But the ticket state machine is the
*primitive that makes the failure visible* — it gives us a single
queryable log to detect it, attribute it, and pre-empt customer impact
before someone walks in to a problem.

### Citation

- `rasa_project/actions/actions.py::ActionValidateBooking.run` — emits
  `booking_reference = "BK-" + sha1(venue_id|date|time|party_int)[:8]`
- `starter/rasa_half/validator.py::normalise_booking_payload` — builds
  the Rasa `sender` from `sha1(venue|date|time)[:8]`; identical bookings
  share the same `sender` suffix, which is the smoking gun the
  reconciliation job correlates on
- `sessions/<id>/tickets/` — forward-only ticket records, the audit
  surface a deduplication job would scan
