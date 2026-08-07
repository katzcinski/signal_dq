#!/usr/bin/env python3
"""G4: OpenAPI-Schema exportieren → apps/cockpit/openapi.json.

Pipeline: python scripts/export_openapi.py && (cd apps/cockpit && npm run gen:api)
CI prüft mit `git diff --exit-code`, dass FE-Typen nicht gegen das BE driften.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT))


def main() -> None:
    from services.api.main import create_app

    schema = create_app().openapi()
    out = ROOT / "apps" / "cockpit" / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {out}")


if __name__ == "__main__":
    main()
