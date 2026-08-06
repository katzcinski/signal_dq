"""Check-suite endpoints: dry-run execution and git-revert. (WS3-2)"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import JSONResponse

from ..auth.provider import PrincipalDep
from ..deps import StoreDep, get_environment
from ..sse import make_progress_callback
from ..settings import get_settings

router = APIRouter(prefix="/api/checks", tags=["checks"])
logger = logging.getLogger("dq_cockpit.checks")

_revert_lock = threading.Lock()

# S-4: {dataset} wird zum Pfadsegment (checks/{dataset}/checks.yml) — gleiche
# Policy wie _SAFE_PRODUCT in contracts.py, sperrt ../-Traversal.
_SAFE_DATASET = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_dataset(dataset: str) -> str:
    if not _SAFE_DATASET.match(dataset or ""):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid dataset name {dataset!r} (allowed: ^[A-Za-z_][A-Za-z0-9_]*$)",
        )
    return dataset


def _summary_payload(summary) -> dict:
    return {
        "mode": "executed",
        "run_id": summary.run_id,
        "dataset": summary.dataset,
        "overall_status": summary.overall_status,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "warnings": summary.warnings,
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "actual_value": r.actual_value,
                "expect": r.expect,
                "severity": r.severity,
                "state": r.state,
                "kind": r.kind,
                "error": r.error,
                "duration_ms": r.duration_ms,
            }
            for r in summary.results
        ],
    }


@router.post(
    "/{dataset}/dry-run",
    responses={status.HTTP_202_ACCEPTED: {"description": "Dry-run operation started."}},
)
def dry_run_checks(
    dataset: str,
    principal: PrincipalDep,
    body: dict = Body(default={}),
    store: StoreDep = ...,
):
    """Compile contract for dataset and run checks without persisting results.

    Body: { "environment": "<env-name>", "execution_mode": "auto|batch|isolated" }
    Ohne Environment: compile-only preview. Ergebnisse werden NIE persistiert.
    """
    import yaml
    from dq_core.contract.compiler import bind_schema, compile_contract as _compile, CompileError
    from dq_core.contract.validator import validate_contract
    from dq_core.engine.check_engine import dataset_config_to_yaml, run_checks

    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Dry-runs require steward role or higher.")

    _validate_dataset(dataset)
    settings = get_settings()
    contracts_dir = Path(settings.contracts_dir)

    # Find the contract whose dataset matches (product slug or dataset name)
    contract_data = None
    for path in sorted(contracts_dir.glob("*.y*ml")):
        if path.name.endswith(".active.yml"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("dataset") == dataset or path.stem == dataset:
            contract_data = data
            break

    if not contract_data:
        raise HTTPException(status_code=404, detail=f"No contract found for dataset {dataset!r}")

    # [CONTRACT-SQL-FREE] G1 gilt auch für den Disk-Pfad (S-3).
    errors = validate_contract(contract_data)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
        )

    try:
        config = _compile(contract_data)
    except CompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    environment = body.get("environment", "")
    env_cfg = get_environment(environment) if environment else None
    if environment and env_cfg is None:
        raise HTTPException(status_code=422, detail=f"Unknown environment {environment!r}")

    if env_cfg is None:
        # No connection: return compile preview only ('{schema}' bleibt ungebunden, G2)
        return {
            "mode": "compile_only",
            "dataset": config.dataset,
            "schema": config.schema,
            "check_count": len(config.checks),
            "checks_yaml": dataset_config_to_yaml(config),
            "message": "No environment configured — compile-only preview. Provide 'environment' in body to run against HANA.",
        }

    schema = env_cfg.get("schema", "")
    bind_schema(config, schema)  # [SCHEMA-MAP]

    execution_mode = str(body.get("execution_mode", "auto"))
    op_id = str(uuid.uuid4())
    if not store.begin_operation(op_id, "dry_run", created_by=principal.sub):
        raise HTTPException(status_code=409, detail="Operation already exists.")

    def _worker() -> None:
        from dq_core.connect.db_connection import get_connection

        callback = make_progress_callback(op_id, store)
        conn = None
        try:
            callback(f'Dry-run fuer "{dataset}" wird vorbereitet ...')
            callback(f'Schema "{schema}" gebunden.')
            conn = get_connection(
                host=env_cfg.get("host", ""),
                port=int(env_cfg.get("port", 443)),
                user=env_cfg.get("user", ""),
                password=env_cfg.get("password", ""),
                schema=schema,
                on_progress=callback,
            )
            # results_db=None -> nichts wird persistiert (WS3-2)
            summary = run_checks(
                config,
                conn,
                results_db=None,
                on_progress=callback,
                execution_mode=execution_mode,
                triggered_by=principal.sub,
            )
            store.finish_operation(op_id, "finished", result_json=json.dumps(_summary_payload(summary), default=str))
        except RuntimeError as exc:
            store.finish_operation(op_id, "error", error=str(exc))
        except Exception:  # noqa: BLE001 - unexpected internals stay out of the API result
            logger.warning("Dry-run operation failed for %s", dataset, exc_info=True)
            store.finish_operation(op_id, "error", error="Dry-run failed to complete.")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"op_id": op_id})

@router.post("/{dataset}/revert")
def revert_checks(
    dataset: str,
    principal: PrincipalDep,
):
    """[AUTHZ] Revert checks/{dataset}/checks.yml to the previous git version (F7)."""
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Revert requires steward role or higher.")

    _validate_dataset(dataset)
    settings = get_settings()
    checks_path = Path(settings.checks_dir) / dataset / "checks.yml"

    if not checks_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No compiled checks found for dataset {dataset!r}",
        )

    with _revert_lock:
        try:
            import git

            repo = git.Repo(search_parent_directories=True)
            rel_path = checks_path.resolve().relative_to(repo.working_tree_dir)

            # Get the hash of the previous version
            commits = list(repo.iter_commits(paths=str(rel_path), max_count=2))
            if len(commits) < 2:
                raise HTTPException(
                    status_code=409,
                    detail="No previous version to revert to (only one commit for this file)",
                )
            prev_commit = commits[1]

            # Restore file from previous commit
            repo.git.checkout(str(prev_commit.hexsha), "--", str(rel_path))

            # Commit the revert — explizit nur diese Datei stagen (S-12)
            repo.index.add([str(rel_path)])
            revert_commit = repo.index.commit(
                f"revert: restore checks/{dataset}/checks.yml to {prev_commit.hexsha[:8]}",
                author=git.Actor(principal.name, f"{principal.sub}@dq-cockpit"),
            )

            return {
                "dataset": dataset,
                "reverted": True,
                "reverted_to_commit": str(prev_commit.hexsha),
                "revert_commit": str(revert_commit.hexsha),
            }

        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="gitpython not installed — cannot revert",
            )
        except git.InvalidGitRepositoryError:
            raise HTTPException(
                status_code=409,
                detail="Checks directory is not inside a git repository",
            )
