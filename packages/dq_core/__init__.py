"""dq_core — framework-free Data Quality engine package.

[ENGINE-FROZEN] — engine/ subpackage must not import any web framework.
"""
from .engine.models import (
    CheckDef,
    CheckResult,
    DatasetConfig,
    RunSummary,
    VALID_OWNERS,
    VALID_SEVERITIES,
)

__all__ = [
    "CheckDef",
    "CheckResult",
    "DatasetConfig",
    "RunSummary",
    "VALID_OWNERS",
    "VALID_SEVERITIES",
]
