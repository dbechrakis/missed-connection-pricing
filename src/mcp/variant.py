"""Which population the pipeline builds: one switch, read once at import.

  v1 (default)  connections within the same REPORTING airline (the operating carrier that files with BTS).
                This is the population v1 and v2 were validated on; its files and results are frozen.
  v3            connections within the same MARKETING network (the brand that sells the ticket: e.g. United
                plus SkyWest, Republic, GoJet... flights sold as United). This is how connections are actually
                ticketed, and it includes regional airlines that do not report to BTS themselves.

Set MCP_VARIANT=v3 to build or read the v3 files. Every population-dependent path gets a "_v3" suffix, so the two
variants never share or overwrite a file.
"""
from __future__ import annotations

import os

VARIANT = os.environ.get("MCP_VARIANT", "v1").strip().lower()
if VARIANT not in ("v1", "v3"):
    raise ValueError(f"MCP_VARIANT must be v1 or v3, got {VARIANT!r}")
MARKETING = VARIANT == "v3"


def sfx(name: str) -> str:
    """'connections' -> 'connections' for v1, 'connections_v3' for v3."""
    return f"{name}_v3" if MARKETING else name
