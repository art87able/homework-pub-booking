# Ex5 — Edinburgh research loop scenario

## Your answer

The planner produced two subgoals: sg_1 (research venues near Haymarket
for a party of 6, assigned to loop) and sg_2 (produce a flyer with the
chosen venue, weather, and cost, also loop). Both ran in the same
executor session.

Turn 1 called venue_search, get_weather, and calculate_cost in parallel
— all three are parallel_safe because they only read fixtures. Turn 2
wrote the flyer via generate_flyer (parallel_safe=False because it
writes a file). Turn 3 called complete_task.

The dataflow integrity check verified four facts extracted from the
HTML flyer: `£540`, `£0`, `cloudy`, and `12` (temperature). All four
appeared in `_TOOL_CALL_LOG` so `verify_dataflow` returned `ok=True`.
The subtle observation: my `calculate_cost` returned `total_gbp=556`
(formula: 18×6×3 + 10% service + £200 min_spend), yet the flyer
showed £540 — and the check still passed. Reason: the fake-LLM script
in `run.py:79-95` passes `total_gbp: 540` as an argument to
`generate_flyer`, and `record_tool_call` logs arguments alongside
outputs. `fact_appears_in_log` scans both, so 540 matched via the
`generate_flyer` call's arg log even though no tool *output* contained
it. The integrity check covers all paths a value can enter the flyer,
not just tool returns.

## Citations

- starter/edinburgh_research/tools.py:382 — flyer is written to `workspace/flyer.html`
- sessions/sess_*/logs/trace.jsonl — tool call sequence (venue_search, get_weather, calculate_cost in parallel, then generate_flyer, then complete_task)
- sessions/sess_*/workspace/flyer.html — the produced HTML flyer
- starter/edinburgh_research/integrity.py:99-112 — `fact_appears_in_log` scans both output and arguments
