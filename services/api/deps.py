"""Dependency providers for FastAPI routes."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends

# Make dq_core importable from service context
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root / "packages"))

from dq_core.store.sqlite_store import ResultStore
from .settings import get_settings

_store_instance: ResultStore | None = None


def get_store() -> ResultStore:
    global _store_instance
    if _store_instance is None:
        settings = get_settings()
        if settings.store_backend == "hana":
            # Kein stilles SQLite-Fallback (L-8): HANA-Store ist noch ein Stub.
            raise RuntimeError(
                "STORE_BACKEND=hana ist konfiguriert, aber HanaStore ist noch "
                "nicht implementiert (O6). Setze STORE_BACKEND=sqlite."
            )
        _store_instance = ResultStore(
            settings.sqlite_db,
            allow_diagnostics=settings.allow_local_diagnostics,
            diagnostics_ttl_days=settings.diagnostics_ttl_days,
        )
    return _store_instance


StoreDep = Annotated[ResultStore, Depends(get_store)]


def get_inventory() -> list[dict[str, Any]]:
    """Load inventory.json from data_dir."""
    import json
    settings = get_settings()
    path = Path(settings.inventory_file)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("objects") or []


def get_lineage() -> dict[str, Any]:
    """Load lineage.json from data_dir."""
    import json
    settings = get_settings()
    path = Path(settings.lineage_file)
    if not path.exists():
        return {"nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def read_environments() -> dict[str, dict[str, Any]]:
    """Load the full environments map from ENVIRONMENTS_FILE (raw, unresolved).

    Returns a name → config mapping exactly as authored on disk. Secret values
    are never resolved here (that happens lazily in ``get_environment`` for the
    immediate connection consumer) so this stays safe to hand to admin-read
    endpoints — provided the caller strips inline ``password`` before responding.
    """
    import yaml
    settings = get_settings()
    path = Path(settings.environments_file)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in data.items()}


def write_environments(envs: dict[str, dict[str, Any]]) -> None:
    """Persist the full environments map to ENVIRONMENTS_FILE.

    Writes deterministic, human-diffable YAML (sorted keys, block style). The
    caller owns the per-entry shape; this helper only serialises. Secret values
    must never be passed in here — only secret *references* (``password_ref``).
    """
    import yaml
    settings = get_settings()
    path = Path(settings.environments_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(envs, sort_keys=True, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def get_environment(name: str) -> dict[str, Any] | None:
    """[SCHEMA-MAP] Resolve environment name → {host, port, schema, ...} from ENVIRONMENTS_FILE.

    Secret hardening (Tier-2): when an entry carries a 'password_ref'
    (e.g. 'env:HANA_PW_PROD') instead of an inline 'password', resolve it via
    the server-side secret resolver so plaintext credentials stay out of the
    YAML. Inline 'password' still works for backward compatibility.
    """
    import yaml
    settings = get_settings()
    path = Path(settings.environments_file)
    if not path.exists() or not name:
        return None
    envs = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = envs.get(name)
    if isinstance(env, dict) and not env.get("password") and env.get("password_ref"):
        from .secrets import get_secret
        resolved = get_secret(env["password_ref"])
        if resolved is not None:
            env = {**env, "password": resolved}
    return env
