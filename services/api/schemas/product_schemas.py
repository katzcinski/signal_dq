from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ProductListItem(BaseModel):
    product: str
    owners: list[str]
    port_count: int
    own_health: str
    upstream_risk_count: int
    finding_count: int
    lifecycle: str


class ProductPortOut(BaseModel):
    dataset: str
    kind: str | None = None
    lifecycle: str | None = None
    compliance: str | None = None
    version: str | None = None


class ProductInteriorOut(BaseModel):
    id: str
    layer: str | None = None
    role: str | None = None
    coverage_flag: str | None = None


class ProductInboundDependencyOut(BaseModel):
    product: str
    pinned_version: str
    current_version: str | None = None
    compliance: str | None = None
    upstream_breach: bool
    version_drift: bool


class ProductFindingOut(BaseModel):
    finding_type: Literal["dangling_port", "contested", "boundary_leak"]
    scope: Literal["port", "interior"] | None = None
    object_id: str
    detail: str


class LineageSubgraphOut(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ProductDetailOut(BaseModel):
    product: str
    owners: list[str]
    lifecycle: str
    own_health: str
    ports: list[ProductPortOut]
    interior: list[ProductInteriorOut]
    inbound_sources: list[str]
    upstream_risk: list[ProductInboundDependencyOut]
    findings: list[ProductFindingOut]
    subgraph: LineageSubgraphOut
