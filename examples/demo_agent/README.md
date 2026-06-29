# Demo Agent

A minimal LangGraph-style agent that demonstrates the full AI Observability Platform.

## What it does

1. **planner.think** — LLM call to plan
2. **tool.browser.fetch** — tool call (15% chance of timeout)
3. **tool.search.web** — tool call to find references
4. **agent.executor** — LLM call to produce final answer
5. **handoff** between agents

Each call emits an `Event` via `@observe`, with realistic latency, tokens, and cost.

## Run

```bash
# 1. Start the ingest API (in another terminal)
make run-ingest

# 2. Install deps
pip install -e packages/ai-obs-sdk
pip install -e examples/demo_agent

# 3. Run the agent
AI_OBS_INGEST_URL=http://localhost:8000 \
  INGEST_API_SECRET=demo \
  python examples/demo_agent/agent.py
# → run_id=... result='Executed: ...'

# 4. See the trace
# Open http://localhost:8000/docs in your browser
# Or query: curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/v1/runs/{run_id}/trace
```

## Replay

```bash
python examples/demo_agent/replay.py
# (in-process, no network)
```

## What to look for

- 4 events emitted (2 llm.call + 2 tool.invoke)
- 1 handoff
- Occasional timeout (15% prob) on `browser.fetch` → emits `error_code: TOOL_TIMEOUT`
- `run_id` in contextvars → propagates through all events

## Use this as a template

Replace `think`, `fetch`, `search`, `execute` with real agent code. The `@observe` decorator handles all instrumentation.
