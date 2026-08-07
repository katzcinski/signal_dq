# [AUTHZ] — server is authoritative; frontend mirrors only
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from ..settings import get_settings

VALID_ROLES = {"viewer", "steward", "owner", "admin"}


@dataclass
class Principal:
    sub: str
    name: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)

    def has_role(self, *roles: str) -> bool:
        return bool(set(self.roles) & set(roles))

    def can_write_contract(self, owned_by: str, owners: list[str]) -> bool:
        """[AUTHZ] Write permission = role × owned_by × owners membership (S3).

        `grp:`-Einträge matchen ausschließlich gegen die Gruppen des Principals
        (aus dem IdP-Claim) — fail-closed: ohne Gruppenzugehörigkeit kein Match.
        """
        if self.has_role("admin"):
            return True
        if owned_by == "platform" and self.has_role("steward", "owner"):
            return True
        if owned_by == "product" and self.has_role("owner"):
            return True
        for owner_entry in owners:
            if owner_entry.startswith("grp:"):
                if owner_entry[len("grp:"):] in self.groups:
                    return True
            elif owner_entry == self.sub:
                return True
        return False


def can_write_contract_data(principal: Principal, contract: dict[str, Any] | None) -> bool:
    """[AUTHZ] S-2: Entscheidung anhand des BESTEHENDEN Contracts (Platte/Index),
    nie anhand des Request-Bodys. Bei Neuanlage gilt die Default-Policy
    (owned_by=platform, keine Owner)."""
    if contract is None:
        return principal.can_write_contract("platform", [])
    return principal.can_write_contract(
        str(contract.get("owned_by", "platform")),
        list(contract.get("owners") or []),
    )


_ADMIN_PRINCIPAL = Principal(sub="dev", name="Development Admin", roles=["admin"])


async def _noauth_principal(
    x_dq_role: str | None = Header(default=None, alias="X-DQ-Role"),
) -> Principal:
    """No-auth mode: use X-DQ-Role header for role simulation in dev."""
    if x_dq_role and x_dq_role in VALID_ROLES:
        return Principal(sub="dev", name="Dev User", roles=[x_dq_role])
    return _ADMIN_PRINCIPAL


async def get_principal(
    x_dq_role: str | None = Header(default=None, alias="X-DQ-Role"),
    authorization: str | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    if settings.auth_mode == "noauth":
        return await _noauth_principal(x_dq_role)
    from .oidc import get_oidc_principal
    return get_oidc_principal(authorization)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str):
    """Dependency factory: raises 403 if principal lacks required roles."""
    async def _check(principal: PrincipalDep) -> Principal:
        if not principal.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: one of {list(roles)}",
            )
        return principal
    return Depends(_check)
