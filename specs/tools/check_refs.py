#!/usr/bin/env python3
"""Check that references inside specs/*.md exist.

Internal refs (live under specs/): MUST exist. Broken = CI fail.
External refs (code paths to be written): warning only.
"""
import re, pathlib, sys
from pathlib import Path

ROOT = pathlib.Path(__file__).parent.parent

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
FILE_REF = re.compile(r"`([\w][\w./-]*\.(?:md|json|yaml|py|ts|tsx|js|sql|sh))`")

CODE_DIRS = {"components", "lib", "services", "app", "src", "packages", "bench", "infra", "postmortems", "fly"}

# Refs to known tool basenames (live in specs/tools/)
TOOL_BASENAMES = {
    "validate_schemas.py", "check_refs.py", "check_enums.py",
    "check_agent_scopes.py", "check_fixtures.py", "check_all.py",
}

def is_internal(ref: str) -> bool:
    if ref.startswith("/"):
        return False
    if "..." in ref or "{" in ref or "}" in ref:
        return False
    # Try resolving to ROOT first
    rel = ref[len("specs/"):] if ref.startswith("specs/") else ref
    candidate = (ROOT / rel).resolve()
    if candidate.exists():
        return True
    # Known tool basename → always internal
    if Path(ref).name in TOOL_BASENAMES:
        return True
    return False  # default: external

errors, warnings = 0, 0

for md in sorted(ROOT.rglob("*.md")):
    text = md.read_text()
    refs = set(WIKILINK.findall(text)) | set(FILE_REF.findall(text))
    for ref in sorted(refs):
        if ref.startswith("http"):
            continue
        rel = ref[len("specs/"):] if ref.startswith("specs/") else ref
        target = (ROOT / rel).resolve()
        if target.exists():
            continue
        # Known tool basename → specs/tools/<name>
        if Path(ref).name in TOOL_BASENAMES:
            target = (ROOT / "tools" / Path(ref).name).resolve()
            if target.exists():
                continue
        # fallback: relative to source
        target2 = (md.parent / ref).resolve()
        if target2.exists():
            continue
        rel_md = md.relative_to(ROOT)
        if is_internal(ref):
            print(f"❌ {rel_md} → `{ref}`  NOT FOUND (internal)")
            errors += 1
        else:
            print(f"⚠️  {rel_md} → `{ref}`  external (code not yet written)")
            warnings += 1

print(f"\n{errors} broken internal refs, {warnings} external refs pending code")
sys.exit(1 if errors else 0)
