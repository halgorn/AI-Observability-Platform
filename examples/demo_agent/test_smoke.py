"""Smoke test for demo agent — uses package directly without pytest."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages" / "ai-obs-sdk" / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from ai_obs.tracer import reset_tracer
from agent import main


def test_demo_agent_emits_expected_events():
    cap = {"events": []}

    def _capture(event):
        cap["events"].append(event)

    reset_tracer()
    from ai_obs.tracer import get_tracer
    tracer = get_tracer()
    tracer.config.sample_rate = 1.0
    tracer._emit = _capture

    main()

    types = [e["type"] for e in cap["events"]]
    assert "step.start" in types
    assert "tool.invoke" in types
    assert "handoff" in types
    assert len(cap["events"]) >= 4
    reset_tracer()


def test_demo_agent_runs_id_is_stable():
    cap = {"events": []}

    def _capture(event):
        cap["events"].append(event)

    reset_tracer()
    from ai_obs.tracer import get_tracer
    tracer = get_tracer()
    tracer.config.sample_rate = 1.0
    tracer._emit = _capture

    main()
    run_ids = {e["run_id"] for e in cap["events"]}
    assert len(run_ids) == 1
    reset_tracer()
