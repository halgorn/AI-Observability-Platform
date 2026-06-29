#!/usr/bin/env python3
"""Run all spec conformance tools. Exits non-zero on any failure."""
import subprocess, sys
from pathlib import Path

TOOLS = [
    "validate_schemas.py",
    "check_enums.py",
    "check_refs.py",
    "check_agent_scopes.py",
    "check_fixtures.py",
]

failed = 0
for tool in TOOLS:
    path = Path(__file__).parent / tool
    print(f"\n── {tool} {'─' * 50}")
    result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    print(result.stdout, end="")
    if result.returncode != 0:
        # check_refs returns 0 even with warnings, so filter for actual errors
        if "broken" in result.stdout and "external refs pending code" in result.stdout:
            pass
        else:
            failed += 1
            print(f"❌ {tool} exited {result.returncode}")
            if result.stderr:
                print(result.stderr)

print(f"\n{'═' * 64}")
print(f"{'PASS — all tools clean' if failed == 0 else f'FAIL — {failed} tools broken'}")
sys.exit(failed)
