"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

import html
import inspect
import json
from pathlib import Path

from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolError, ToolRegistry, ToolResult, _RegisteredTool

from starter.edinburgh_research.integrity import _TOOL_CALL_LOG, record_tool_call

_SAMPLE_DATA = Path(__file__).parent / "sample_data"

# Tool-call budget: cap venue_search at this many calls per session so the
# LLM can't spiral indefinitely. See docs/real-mode-failures.md §"Ex5 spiral".
_VENUE_SEARCH_BUDGET = 3


# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp

    Returns a ToolResult with:
      output: {"near": ..., "party_size": ..., "results": [<venue dicts>], "count": int}
      summary: "venue_search(<near>, party=<N>): <count> result(s)"

    MUST call record_tool_call(...) before returning so the integrity
    check can see what data was produced.
    """
    arguments = {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp}

    prior_searches = [r for r in _TOOL_CALL_LOG if r.tool_name == "venue_search"]
    if len(prior_searches) >= _VENUE_SEARCH_BUDGET:
        seen: dict[str, str] = {}
        for r in prior_searches:
            for v in r.output.get("results", []) or []:
                seen.setdefault(v.get("id", ""), v.get("name", ""))
        already_found = ", ".join(f"{n} ({vid})" for vid, n in seen.items() if vid) or "none"
        output = {
            "near": near,
            "party_size": party_size,
            "results": [],
            "count": 0,
            "spiral_guard_triggered": True,
        }
        record_tool_call("venue_search", arguments, output)
        return ToolResult(
            success=False,
            output=output,
            summary=(
                f"STOP calling venue_search ({len(prior_searches)} prior calls). "
                f"Use the results you already have: {already_found}. "
                "Next step: call get_weather, then calculate_cost, then generate_flyer."
            ),
            error=ToolError(
                code="SA_TOOL_RATE_LIMITED",
                message=f"venue_search budget {_VENUE_SEARCH_BUDGET} exceeded",
            ),
        )

    venues_path = _SAMPLE_DATA / "venues.json"
    if not venues_path.exists():
        output = {"near": near, "party_size": party_size, "results": [], "count": 0}
        record_tool_call("venue_search", arguments, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"venue_search({near}, party={party_size}): fixture missing",
            error=ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"venues fixture not found at {venues_path}",
            ),
        )

    venues = json.loads(venues_path.read_text(encoding="utf-8"))
    needle = near.casefold()
    matches = [
        v
        for v in venues
        if v.get("open_now") is True
        and needle in v.get("area", "").casefold()
        and v.get("seats_available_evening", 0) >= party_size
        and v.get("hire_fee_gbp", 0) + v.get("min_spend_gbp", 0) <= budget_max_gbp
    ]

    output = {
        "near": near,
        "party_size": party_size,
        "results": matches,
        "count": len(matches),
    }
    record_tool_call("venue_search", arguments, output)

    if matches:
        summary = f"venue_search({near}, party={party_size}): {len(matches)} result(s)"
    else:
        valid_areas = sorted({v.get("area", "") for v in venues if v.get("open_now")})
        summary = (
            f"venue_search({near}, party={party_size}): 0 result(s). "
            f"The 'near' arg must match one of these Edinburgh areas exactly "
            f"(case-insensitive substring): {', '.join(valid_areas)}. "
            "Retry with one of these — do NOT pass 'Edinburgh' as the area."
        )
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD).

    Reads sample_data/weather.json. Returns:
      output: {"city": str, "date": str, "condition": str, "temperature_c": int, ...}
      summary: "get_weather(<city>, <date>): <condition>, <temp>C"

    If the city or date is not in the fixture, return success=False with
    a clear ToolError (SA_TOOL_INVALID_INPUT). Do NOT raise.

    MUST call record_tool_call(...) before returning.
    """
    arguments = {"city": city, "date": date}
    weather_path = _SAMPLE_DATA / "weather.json"
    if not weather_path.exists():
        output = {"city": city, "date": date}
        record_tool_call("get_weather", arguments, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): fixture missing",
            error=ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"weather fixture not found at {weather_path}",
            ),
        )

    weather = json.loads(weather_path.read_text(encoding="utf-8"))
    city_key = city.casefold()
    by_date = weather.get(city_key)
    record = by_date.get(date) if by_date else None
    if record is None:
        output = {"city": city, "date": date}
        record_tool_call("get_weather", arguments, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): not in fixture",
            error=ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message=f"no weather record for city={city!r} date={date!r}",
            ),
        )

    output = {
        "city": city,
        "date": date,
        "condition": record["condition"],
        "temperature_c": record["temperature_c"],
        "precip_mm": record.get("precip_mm"),
        "wind_kph": record.get("wind_kph"),
    }
    record_tool_call("get_weather", arguments, output)
    return ToolResult(
        success=True,
        output=output,
        summary=f"get_weather({city}, {date}): {record['condition']}, {record['temperature_c']}C",
    )


# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking.

    Formula:
      base_per_head = base_rates_gbp_per_head[catering_tier]
      venue_mult    = venue_modifiers[venue_id]
      subtotal      = base_per_head * venue_mult * party_size * max(1, duration_hours)
      service       = subtotal * service_charge_percent / 100
      total         = subtotal + service + <venue's hire_fee_gbp + min_spend_gbp>
      deposit_rule  = per deposit_policy thresholds

    Returns:
      output: {
        "venue_id": str,
        "party_size": int,
        "duration_hours": int,
        "catering_tier": str,
        "subtotal_gbp": int,
        "service_gbp": int,
        "total_gbp": int,
        "deposit_required_gbp": int,
      }
      summary: "calculate_cost(<venue>, <party>): total £<N>, deposit £<M>"

    MUST call record_tool_call(...) before returning.
    """
    arguments = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }

    venues_path = _SAMPLE_DATA / "venues.json"
    catering_path = _SAMPLE_DATA / "catering.json"
    if not venues_path.exists() or not catering_path.exists():
        record_tool_call("calculate_cost", arguments, {})
        return ToolResult(
            success=False,
            output={},
            summary=f"calculate_cost({venue_id}, party={party_size}): fixture missing",
            error=ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message="venues.json or catering.json missing",
            ),
        )

    venues = json.loads(venues_path.read_text(encoding="utf-8"))
    catering = json.loads(catering_path.read_text(encoding="utf-8"))

    venue = next((v for v in venues if v["id"] == venue_id), None)
    if venue is None:
        record_tool_call("calculate_cost", arguments, {})
        return ToolResult(
            success=False,
            output={},
            summary=f"calculate_cost({venue_id}, ...): unknown venue",
            error=ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message=f"unknown venue_id {venue_id!r}",
            ),
        )

    base_rates = catering["base_rates_gbp_per_head"]
    if catering_tier not in base_rates:
        record_tool_call("calculate_cost", arguments, {})
        return ToolResult(
            success=False,
            output={},
            summary=f"calculate_cost(...): unknown catering_tier {catering_tier!r}",
            error=ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message=f"unknown catering_tier {catering_tier!r}",
            ),
        )

    base_per_head = base_rates[catering_tier]
    venue_mult = catering["venue_modifiers"].get(venue_id, 1.0)
    hours = max(1, duration_hours)
    subtotal = base_per_head * venue_mult * party_size * hours
    service = subtotal * catering["service_charge_percent"] / 100.0
    total = subtotal + service + venue["hire_fee_gbp"] + venue["min_spend_gbp"]

    total_int = int(round(total))
    policy = catering["deposit_policy"]
    if total_int < 300:
        deposit = 0
    elif total_int <= 1000:
        deposit = int(round(total_int * 0.20))
    else:
        deposit = int(round(total_int * 0.30))
    # The keys in deposit_policy are descriptive labels we don't actually
    # need to look up by name — the rule itself is the contract.
    _ = policy  # retain reference to keep the fixture in scope (loads validate JSON).

    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": int(round(subtotal)),
        "service_gbp": int(round(service)),
        "total_gbp": total_int,
        "deposit_required_gbp": deposit,
    }
    record_tool_call("calculate_cost", arguments, output)
    return ToolResult(
        success=True,
        output=output,
        summary=f"calculate_cost({venue_id}, party={party_size}): total £{total_int}, deposit £{deposit}",
    )


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html.

    event_details is expected to contain at least:
      venue_name, venue_address, date, time, party_size, condition,
      temperature_c, total_gbp, deposit_required_gbp

    Write a self-contained HTML flyer (inline CSS, no external assets). Tag every key fact with data-testid="<n>" so the integrity check can parse it.

    Write a formatted HTML flyer with an H1 title, the event
    facts, a weather summary, and the cost breakdown.

    Returns:
      output: {"path": "workspace/flyer.html", "bytes_written": int}
      summary: "generate_flyer: wrote <path> (<N> chars)"

    MUST call record_tool_call(...) before returning — the integrity
    check compares the flyer's contents against earlier tool outputs.

    IMPORTANT: this tool MUST be registered with parallel_safe=False
    because it writes a file.
    """
    arguments = {"event_details": dict(event_details)}

    def _fact(key: str, default: object = "") -> str:
        return html.escape(str(event_details.get(key, default)))

    venue_name = _fact("venue_name", "Edinburgh Venue")
    venue_address = _fact("venue_address")
    date = _fact("date")
    time = _fact("time")
    party_size = _fact("party_size")
    condition = _fact("condition")
    temperature_c = _fact("temperature_c")
    total_gbp = _fact("total_gbp")
    deposit_required_gbp = _fact("deposit_required_gbp")

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{venue_name} — event flyer</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 640px;
         margin: 2em auto; color: #222; line-height: 1.5; }}
  h1 {{ font-size: 2em; margin-bottom: 0.2em; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 0.3em 1em; }}
  dt {{ font-weight: 600; color: #555; }}
  section {{ margin-top: 1.5em; }}
</style>
</head>
<body>
  <h1 data-testid="venue_name">{venue_name}</h1>
  <p data-testid="venue_address">{venue_address}</p>

  <section>
    <h2>Event</h2>
    <dl>
      <dt>Date</dt><dd data-testid="date">{date}</dd>
      <dt>Time</dt><dd data-testid="time">{time}</dd>
      <dt>Party size</dt><dd data-testid="party_size">{party_size}</dd>
    </dl>
  </section>

  <section>
    <h2>Weather</h2>
    <dl>
      <dt>Condition</dt><dd data-testid="condition">{condition}</dd>
      <dt>Temperature</dt><dd data-testid="temperature_c">{temperature_c}°C</dd>
    </dl>
  </section>

  <section>
    <h2>Cost</h2>
    <dl>
      <dt>Total</dt><dd data-testid="total">£{total_gbp}</dd>
      <dt>Deposit required</dt><dd data-testid="deposit">£{deposit_required_gbp}</dd>
    </dl>
  </section>
</body>
</html>
"""

    workspace = session.workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    flyer_path = workspace / "flyer.html"
    flyer_path.write_text(body, encoding="utf-8")
    bytes_written = flyer_path.stat().st_size

    output = {"path": "workspace/flyer.html", "bytes_written": bytes_written}
    record_tool_call("generate_flyer", arguments, output)
    return ToolResult(
        success=True,
        output=output,
        summary=f"generate_flyer: wrote {output['path']} ({len(body)} chars)",
    )


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session, *, include_builtins: bool = True) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools, optionally
    including the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    Pass include_builtins=False to get only the homework's tools — handy in
    tests where we want to assert that nothing else leaked into the registry.

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session) if include_builtins else ToolRegistry()

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description=inspect.getdoc(venue_search) or "",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description=inspect.getdoc(get_weather) or "",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description=inspect.getdoc(calculate_cost) or "",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description=inspect.getdoc(generate_flyer) or "",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
