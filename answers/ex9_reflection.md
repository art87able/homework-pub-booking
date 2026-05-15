# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

I ran Ex7 several times (session `sess_c66f3795c46c` is the latest).
The bridge completed in 2 rounds: round 1 chose `haymarket_tap`,
structured rejected (party=12 > cap=8), round 2 chose `royal_oak`,
structured accepted. So a planner→structured handoff DID happen — but
not where I expected.

Reading the scripted plan in `starter/handoff_bridge/run.py:30-48`, the
DefaultPlanner outputs BOTH subgoals with `assigned_half: "loop"`. The
planner never assigns work to structured directly. The handoff to
structured is triggered later, inside the LoopHalf's executor loop, by
a tool call named `handoff_to_structured` (one of the framework
builtins in `sovereign_agent.tools.builtin.make_builtin_registry`).
That tool call is what `HandoffBridge.run_round` watches for — when it
appears in `LoopHalfResult.next_action`, the bridge swaps active halves.

This matters because it relocates the architectural decision. The
planner stays neutral — it just decomposes work. The executor LLM,
seeing the rule-bound nature of the booking, requests structured help.
The bridge enforces the swap by atomic-rename file IPC
(`ipc/handoff_to_structured.json`), so a crash mid-transition leaves
exactly one of {old-half, new-half} responsible for the session.

The broader lesson: planner decisions are advisory categorization;
tool-call decisions during execution are load-bearing. When debugging
"why didn't structured run," look at the executor's tool calls in
`logs/trace.jsonl`, not the planner's subgoal metadata.

### Citation

- `starter/handoff_bridge/run.py:30-48` — scripted planner output, both
  subgoals `assigned_half: "loop"`
- `starter/handoff_bridge/run.py:70-85` — scripted executor tool call
  `handoff_to_structured`
- `starter/handoff_bridge/bridge.py` — `HandoffBridge.run_round` reads
  `next_action` and routes
- A run produces `sessions/<id>/logs/trace.jsonl` with
  `bridge.round_start`, `bridge.handoff_to_structured`,
  `bridge.handoff_to_loop`, `bridge.round_complete` events

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

## Q3 — Removing one framework primitive

### Your answer

**Primitive I'd keep:** session directories (Decision 1 — physical
workspace isolation).

**Failure mode that primitive prevents:** the LLM-tool-call spiral I
observed in `make ex5-real`. Three back-to-back runs all failed
identically — Qwen3-32B called `venue_search` with wrong args ("Edinburgh"
as area instead of "Haymarket", party=10 instead of 6, date="2023-10-15"
instead of "2026-04-25") then handed off to structured without ever
calling `generate_flyer`. Without per-session directories I would have
no record of each spiral's distinct shape. With them, I have three
sibling dirs at `~/Library/Application Support/sovereign-agent/examples/
ex5-edinburgh-research/sess_{fb901fa38d53,2f9c112dea40,f2274240349d}/`
each holding the trace.jsonl + tickets that show exactly what Qwen
attempted.

Diagnosis only worked because of this isolation. I could `diff` the
tool-call sequences across runs, see that Qwen consistently widened
the area filter, and design my tool-side spiral guard
(`_VENUE_SEARCH_BUDGET = 3` in `tools.py:18`) with confidence. A flat
log file would have interleaved the three failures into a single
timeline I couldn't decompose.

If I had to give up session directories, I'd substitute them with
process-isolated tempdirs + a manual `tar` archive after each run.
That's reinvented session directories. Other primitives — tickets,
trace events, manifests — I could rebuild on top of even minimal
isolation. Without isolation, every primitive becomes archaeology.

### Citation

- `~/Library/Application Support/sovereign-agent/examples/ex5-edinburgh-research/sess_2f9c112dea40/logs/trace.jsonl` —
  one of three real Ex5 spiral traces I diffed
- `starter/edinburgh_research/tools.py:18-21` — `_VENUE_SEARCH_BUDGET`
  constant, the tool-side cap I added after diagnosis
- `docs/real-mode-failures.md:15-83` — official catalogue entry for the
  spiral, matching what I observed
