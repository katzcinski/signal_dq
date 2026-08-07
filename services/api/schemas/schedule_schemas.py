from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScheduleUpsertIn(BaseModel):
    """Per-object scheduling toggle.

    mode=internal → Signal's poller runs the object every ``interval_seconds``.
    mode=external → an outside orchestrator (Task Chain / cron → CLI) drives it;
    mode=on_load → AP-5: der Poller startet einen Lauf, sobald die Datasphere-
    Run-Historie einen NEUEN erfolgreichen Load für das Objekt zeigt (Dedupe
    über die zuletzt gesehene externe Run-ID);
    Signal records runs but never fires the poller for it.
    """
    mode: Literal["internal", "external", "on_load"] = "internal"
    interval_seconds: int = Field(default=0, ge=0, le=31 * 24 * 3600)
    environment: str = Field(default="", max_length=64)
    execution_mode: Literal["auto", "batch", "isolated"] = "auto"
    enabled: bool = True


class ScheduleOut(BaseModel):
    schedule_id: str
    object_id: str
    mode: str
    environment: str
    execution_mode: str
    interval_seconds: int
    enabled: bool
    next_due_at: str
    last_run_at: Optional[str] = None
    last_run_id: Optional[str] = None
    last_status: Optional[str] = None
    created_by: str = ""
    created_at: str = ""
    updated_at: Optional[str] = None
