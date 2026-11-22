"""Gera o JSON do badge de cobertura (endpoint do shields.io) a partir do coverage.json do coverage.py.

Uso: python scripts/coverage_badge.py coverage.json site/badges/coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def badge(percent: float) -> dict[str, object]:
    thresholds = ((90, "brightgreen"), (80, "green"), (70, "yellowgreen"), (60, "yellow"))
    color = next((name for limit, name in thresholds if percent >= limit), "red")
    return {"schemaVersion": 1, "label": "coverage", "message": f"{percent:.1f}%", "color": color}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("uso: coverage_badge.py <coverage.json> <saida.json>", file=sys.stderr)
        return 2
    source, target = Path(argv[0]), Path(argv[1])
    percent = float(json.loads(source.read_text(encoding="utf-8"))["totals"]["percent_covered"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(badge(percent)) + "\n", encoding="utf-8")
    print(f"cobertura: {percent:.1f}% -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
