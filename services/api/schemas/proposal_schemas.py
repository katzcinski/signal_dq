from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ProposalOut(BaseModel):
    id: str
    product: str
    check_name: str
    current_expect: str = ""
    proposed_expect: str
    rationale: str = ""
    confidence: float = 0.0
    stats: dict[str, Any] = {}
    status: str = "open"
    created_at: str = ""
    kind: str = "internal_gate"
