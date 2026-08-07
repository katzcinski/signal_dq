# [CONTRACT-SQL-FREE] — contracts carry guarantees, never SQL
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

VALID_KINDS: frozenset[str] = frozenset({"internal_gate", "consumer_contract", "provider_contract"})


@dataclass
class Guarantee:
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    severity: str = "fail"
    owned_by: str = "platform"
    # Durchsetzung bei Breach (gate|quarantine|monitor); leer ⇒ Contract-Default.
    enforcement: str = ""


@dataclass
class Contract:
    product: str
    dataset: str
    owned_by: str = "platform"
    kind: str = "internal_gate"
    owners: list[str] = field(default_factory=list)
    version: str = "0.1.0"
    lifecycle: str = "draft"
    # allowed: draft | active | deprecated
    # Enforcement-Default fürs ganze Produkt (Lite: ein Schalter); Garantien
    # können ihn je Familie überschreiben. Default 'monitor' — nie blockierend.
    enforcement_default: str = "monitor"
    guarantees: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contract":
        return cls(
            product=str(data.get("product") or data.get("dataset") or ""),
            dataset=str(data.get("dataset") or ""),
            owned_by=str(data.get("owned_by", "platform")),
            kind=str(data.get("kind", "internal_gate")),
            owners=list(data.get("owners") or []),
            version=str(data.get("version", "0.1.0")),
            lifecycle=str(data.get("lifecycle", "draft")),
            enforcement_default=str(data.get("enforcement_default", "monitor")),
            guarantees=dict(data.get("guarantees") or {}),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "dataset": self.dataset,
            "owned_by": self.owned_by,
            "kind": self.kind,
            "owners": self.owners,
            "version": self.version,
            "lifecycle": self.lifecycle,
            "enforcement_default": self.enforcement_default,
            "guarantees": self.guarantees,
        }
