"""Naming-convention semantics for the Signal inventory + lineage layer.

Conservative derivation of architectural metadata (layer / layerCode / role /
confidence) from a Datasphere object's technical name, object type and
semantic usage. Ported from the Meridian (datasphere-tools) inventory engine,
trimmed to the pure transforms Signal needs.

The QUNIS layer convention is **lowercase only**. Legacy uppercase prefixes
like ``B_`` / ``H_`` are space/schema qualifiers from external tenants, not
layer markers — they intentionally map to ``layer="unknown"``.

Framework-free: pure stdlib only (``hashlib`` + ``re``), so it satisfies the
dq_core G7 gate and can be imported both as a package module
(``dq_core.lineage._semantics``) and in script mode (``_semantics``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# Bumped in lockstep with the Meridian inventory format Signal must match.
SCHEMA_VERSION = 6

# ---------------------------------------------------------------------------
# Layer derivation (QUNIS four-layer architecture)
# ---------------------------------------------------------------------------

# Ordered: most specific prefix first. Lowercase only.
PREFIX_LAYER: tuple[tuple[str, str, str], ...] = (
    # (prefix, layer, layerCode)
    ("ic_", "integrated_core", "ic"),
    ("bc_", "business_core", "bc"),
    ("r_",  "raw",             "r"),
    ("i_",  "raw",             "r"),   # legacy "inbound"
    ("b_",  "integrated_core", "ic"),  # legacy lowercase "base"
    ("s_",  "serving",         "s"),
    ("c_",  "serving",         "s"),   # legacy "consumption"
)

LAYER_RANK: dict[str, int] = {
    "raw": 0,
    "integrated_core": 1,
    "business_core": 2,
    "serving": 3,
    "unknown": -1,
}


# ---------------------------------------------------------------------------
# Role derivation defaults
# ---------------------------------------------------------------------------

_OBJECT_TYPE_ROLE: dict[str, str] = {
    "local-tables":         "table",
    "remote-tables":        "table",
    "analytic-models":      "analytic_model",
    "consumption-models":   "consumption",
    "data-flows":           "flow",
    "transformation-flows": "flow",
    "replication-flows":    "flow",
    "task-chains":          "flow",
    "intelligent-lookups":  "other",
    "data-access-controls": "other",
    "business-entities":    "other",
    "fact-models":          "fact",
    "er-models":            "other",
}

_SEMANTIC_USAGE_ROLE: dict[str, str] = {
    "Fact":               "fact",
    "Dimension":          "dimension",
    "Text":               "text",
    "Hierarchy":          "hierarchy",
    "Analytical Dataset": "fact",
    "Relational Dataset": "other",
}


# ---------------------------------------------------------------------------
# Naming model (customer-configurable layer prefixes / type suffixes)
# ---------------------------------------------------------------------------

# The four canonical layers are fixed (the architecture-review rank logic
# depends on them). A customer convention only remaps *prefixes* onto these
# layers — it never invents new ones.
CANONICAL_LAYERS: tuple[str, ...] = (
    "raw", "integrated_core", "business_core", "serving",
)


@dataclass(frozen=True)
class LayerRule:
    """One prefix → canonical layer mapping."""

    prefix: str
    layer: str            # one of CANONICAL_LAYERS
    code: str = ""
    label: str = ""
    legacy: bool = False


@dataclass(frozen=True)
class SuffixRule:
    """One object-type / role suffix rule.

    ``regex`` overrides the literal ``endswith`` match when set — the QUNIS
    default uses it to preserve historical patterns such as ``_fact(_v)?$``.
    ``object_types`` lists the Datasphere object types the suffix is valid
    for; an empty tuple means the suffix drives role classification only.
    ``classify=False`` keeps a suffix out of role derivation (e.g. the generic
    ``_v`` view suffix, which the type check still recognises).
    """

    suffix: str
    role: str = "other"
    object_types: tuple[str, ...] = ()
    regex: str = ""
    classify: bool = True


class NamingModel:
    """A complete naming convention: layer prefixes + type/role suffixes.

    Construction precompiles the suffix and anti-pattern regexes once, so
    matching is cheap. The default instance (:data:`QUNIS_DEFAULT`) reproduces
    the historical QUNIS behaviour; pass a custom instance to the
    ``build_inventory_object`` / ``build_lineage_graph`` callers to remap
    prefixes for another tenant.
    """

    def __init__(
        self,
        *,
        name: str = "QUNIS-Standard",
        layers: "tuple[LayerRule, ...] | list[LayerRule]" = (),
        suffixes: "tuple[SuffixRule, ...] | list[SuffixRule]" = (),
        case_sensitive: bool = True,
        separator: str = "_",
        non_descriptive_patterns: "tuple[str, ...] | list[str]" = (),
        semantic_usage_role: "dict[str, str] | None" = None,
        object_type_role: "dict[str, str] | None" = None,
    ) -> None:
        self.name = name
        self.layers = tuple(layers)
        self.suffixes = tuple(suffixes)
        self.case_sensitive = bool(case_sensitive)
        self.separator = separator or "_"
        self.non_descriptive_patterns = tuple(non_descriptive_patterns)
        self.semantic_usage_role = dict(
            semantic_usage_role if semantic_usage_role is not None else _SEMANTIC_USAGE_ROLE
        )
        self.object_type_role = dict(
            object_type_role if object_type_role is not None else _OBJECT_TYPE_ROLE
        )
        self._suffix_compiled: list[tuple[re.Pattern[str], SuffixRule]] = []
        for rule in self.suffixes:
            pattern = rule.regex or (re.escape(rule.suffix) + "$")
            self._suffix_compiled.append((re.compile(pattern, re.IGNORECASE), rule))
        self._nd_compiled: list[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self.non_descriptive_patterns
        ]

    # -- layer -------------------------------------------------------------
    def match_layer(self, technical_name: str) -> tuple[str, str]:
        """Return ``(layer, code)`` for a name, or ``("unknown", "?")``."""
        if not technical_name:
            return "unknown", "?"
        hay = technical_name if self.case_sensitive else technical_name.lower()
        for rule in self.layers:
            pfx = rule.prefix if self.case_sensitive else rule.prefix.lower()
            if pfx and hay.startswith(pfx):
                return rule.layer, rule.code or "?"
        return "unknown", "?"

    # -- role / suffix -----------------------------------------------------
    def classification_role(self, technical_name: str) -> str | None:
        """First matching suffix role (``classify=True`` rules only)."""
        name = technical_name or ""
        for pattern, rule in self._suffix_compiled:
            if not rule.classify:
                continue
            if pattern.search(name):
                return rule.role
        return None

    def type_suffix_match(self, technical_name: str) -> "SuffixRule | None":
        """First suffix rule carrying ``object_types`` that matches the name."""
        name = technical_name or ""
        for pattern, rule in self._suffix_compiled:
            if not rule.object_types:
                continue
            if pattern.search(name):
                return rule
        return None

    def expected_suffix_for_type(self, object_type: str) -> str:
        """Shortest suffix declared valid for ``object_type`` (or "")."""
        candidates = [r.suffix for r in self.suffixes if object_type in r.object_types]
        return min(candidates, key=len) if candidates else ""

    def layer_prefix_hint(self) -> str:
        """Human-readable list of non-legacy prefixes, e.g. ``r_/ic_/bc_/s_``."""
        return "/".join(r.prefix for r in self.layers if not r.legacy)

    def non_descriptive_match(self, technical_name: str) -> "re.Match[str] | None":
        for pattern in self._nd_compiled:
            m = pattern.search(technical_name or "")
            if m:
                return m
        return None

    # -- derivations (instance methods so a model is self-contained) -------
    def derive_role(
        self,
        technical_name: str,
        object_type: str,
        semantic_usage: str | None,
    ) -> str:
        """Best-effort role classification.

        Combines (in order): explicit name suffix, then ``semanticUsage``,
        then ``objectType``. Falls back to ``"other"``.
        """
        suffix_role = self.classification_role(technical_name)
        if suffix_role:
            return suffix_role
        if semantic_usage:
            mapped = self.semantic_usage_role.get(semantic_usage)
            if mapped:
                return mapped
        return self.object_type_role.get(object_type or "", "other")

    def derive_confidence(
        self,
        technical_name: str,
        object_type: str,
        semantic_usage: str | None,
        layer: str,
        role: str,
    ) -> float:
        """Confidence that ``layer`` + ``role`` reflect reality (0..1).

        * Start at 0.5.
        * +0.3 when layer != "unknown" (prefix matched).
        * +0.2 when suffix and semanticUsage agree on role; else +0.1 if suffix agrees.
        * +0.1 when objectType agrees with role.
        * Clamp to [0, 1].
        """
        score = 0.5
        if layer != "unknown":
            score += 0.3

        suffix_role = self.classification_role(technical_name)
        if suffix_role and suffix_role == role:
            if semantic_usage and self.semantic_usage_role.get(semantic_usage) == role:
                score += 0.2
            else:
                score += 0.1

        if self.object_type_role.get(object_type or "") == role:
            score += 0.1

        return max(0.0, min(1.0, round(score, 3)))


_QUNIS_LAYER_LABELS = {
    "raw": "Raw Zone",
    "integrated_core": "Integrated Core",
    "business_core": "Business Core",
    "serving": "Serving",
}
_QUNIS_LEGACY_PREFIXES = {"i_", "b_", "c_"}

# The built-in QUNIS convention. Reproduces the historical PREFIX_LAYER /
# suffix-role / review-suffix behaviour exactly, so nothing changes until a
# custom model is supplied.
QUNIS_DEFAULT = NamingModel(
    name="QUNIS-Standard",
    layers=tuple(
        LayerRule(
            prefix=pfx,
            layer=layer,
            code=code,
            label=_QUNIS_LAYER_LABELS.get(layer, ""),
            legacy=(pfx in _QUNIS_LEGACY_PREFIXES),
        )
        for pfx, layer, code in PREFIX_LAYER
    ),
    suffixes=(
        SuffixRule("_fact_v", "fact", ("views",), r"(?i)_fact(_v)?$"),
        SuffixRule("_dim_v", "dimension", ("views",), r"(?i)_dim(_v)?$"),
        SuffixRule("_txt", "text", (), r"(?i)_txt$"),
        SuffixRule("_text", "text", (), r"(?i)_text$"),
        SuffixRule("_hier_v", "hierarchy", ("views",), r"(?i)_hier(?:_[a-z0-9_]*)?(_v)?$"),
        SuffixRule("_hdir", "hierarchy", (), r"(?i)_hdir(?:_[a-z0-9_]*)?(_v)?$"),
        SuffixRule("_am", "analytic_model", ("analytic-models",), r"(?i)_am$"),
        SuffixRule("_lt", "table", ("local-tables",), r"(?i)_lt$"),
        SuffixRule("_consumption_v", "consumption", (), r"(?i)_consumption(_v)?$"),
        SuffixRule("_v", "view", ("views",), r"(?i)_v$", classify=False),
    ),
    case_sensitive=True,
    separator="_",
    non_descriptive_patterns=(
        r"(?:^|_)(?:TEST|TEMP|TMP|COPY(?:_OF)?|OLD|NEW\d*|BACKUP|DRAFT|DUMMY|SAMPLE)(?:_|$)"
        r"|_V\d+$|VIEW\d+$|\d{3,}$",
    ),
)


def default_naming_model() -> NamingModel:
    """Return the built-in QUNIS naming model (a sensible default)."""
    return QUNIS_DEFAULT


# Backwards-friendly module-level helpers (delegate to a model). Kept so the
# integrator can call them without holding a NamingModel reference.
def derive_layer(technical_name: str, model: "NamingModel | None" = None) -> tuple[str, str]:
    """Return ``(layer, layerCode)`` for a technical name."""
    return (model or QUNIS_DEFAULT).match_layer(technical_name)


def derive_role(
    technical_name: str,
    object_type: str,
    semantic_usage: str | None,
    model: "NamingModel | None" = None,
) -> str:
    return (model or QUNIS_DEFAULT).derive_role(technical_name, object_type, semantic_usage)


def derive_confidence(
    technical_name: str,
    object_type: str,
    semantic_usage: str | None,
    layer: str,
    role: str,
    model: "NamingModel | None" = None,
) -> float:
    return (model or QUNIS_DEFAULT).derive_confidence(
        technical_name, object_type, semantic_usage, layer, role,
    )


# ---------------------------------------------------------------------------
# SQL fingerprint (for duplicate-logic detection)
# ---------------------------------------------------------------------------

_FP_LINE_COMMENT = re.compile(r"--[^\n]*")
_FP_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_FP_WHITESPACE = re.compile(r"\s+")


def normalise_sql(sql: str | None) -> str:
    """Strip comments, collapse whitespace, lowercase."""
    if not sql:
        return ""
    text = _FP_LINE_COMMENT.sub("", sql)
    text = _FP_BLOCK_COMMENT.sub("", text)
    text = _FP_WHITESPACE.sub(" ", text).strip().lower()
    return text


def sql_fingerprint(sql: str | None) -> str:
    """Stable SHA1 of normalised SQL. Empty SQL → empty string (not hashed)."""
    text = normalise_sql(sql)
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Lineage source-scope parsing
# ---------------------------------------------------------------------------

# Qualified external reference: "H.H_Foo", "Sales.x"
_EXTERNAL_SPACE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]{0,31})\.([A-Za-z0-9_][\w]*)$")

# Datasphere-ish identifier.
_DSP_LIKE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Tokens that look like SQL/regex parser noise. Short, lowercase, no
# underscores, common short words. Kept intentionally tight.
_NOISE_TOKENS = frozenset({
    "auf", "intrastat", "txt", "tmp", "tbl", "src", "tgt", "x", "y", "t",
    "a", "b", "c", "d",
})


def _guess_kind_from_name(name: str, model: "NamingModel | None" = None) -> str | None:
    """Heuristic kind hint based on suffix; None if no match."""
    return (model or QUNIS_DEFAULT).classification_role(name)


def parse_external_source(
    name: str,
    *,
    in_space: bool,
    model: "NamingModel | None" = None,
) -> dict[str, Any]:
    """Classify a lineage source name.

    Returns a dict with ``sourceScope`` (one of ``local`` / ``external_space``
    / ``external_system`` / ``external_raw`` / ``parser_noise``),
    ``externalSpace`` (optional), ``sourceKind`` (optional), and ``confidence``.
    ``in_space`` is the flag the producer computes (``source in known_local_ids``).
    """
    if in_space:
        return {"sourceScope": "local", "confidence": 1.0}

    n = (name or "").strip()
    if not n:
        return {"sourceScope": "parser_noise", "confidence": 0.0}
    if n.upper().startswith("S4:") and len(n) > 3:
        return {
            "sourceScope": "external_system",
            "sourceSystem": "S4",
            "externalKey": n[3:],
            "confidence": 0.9,
        }

    m = _EXTERNAL_SPACE_RE.match(n)
    if m:
        space, ident = m.group(1), m.group(2)
        kind = _guess_kind_from_name(ident, model)
        return {
            "sourceScope": "external_space",
            "externalSpace": space,
            "sourceKind": kind,
            "confidence": 0.9,
        }

    # Noise heuristics: short lowercase, no underscores, or a known noise word.
    lower = n.lower()
    if (
        lower in _NOISE_TOKENS
        or (len(n) < 4 and "_" not in n)
        or not _DSP_LIKE_RE.match(n)
    ):
        return {"sourceScope": "parser_noise", "confidence": 0.2}

    # Looks like a real identifier from another tenant/schema we couldn't
    # match. Treat as external_raw with mid confidence.
    kind = _guess_kind_from_name(n, model)
    return {
        "sourceScope": "external_raw",
        "sourceKind": kind,
        "confidence": 0.6,
    }


__all__ = [
    "SCHEMA_VERSION",
    "PREFIX_LAYER",
    "LAYER_RANK",
    "CANONICAL_LAYERS",
    "LayerRule",
    "SuffixRule",
    "NamingModel",
    "QUNIS_DEFAULT",
    "default_naming_model",
    "derive_layer",
    "derive_role",
    "derive_confidence",
    "normalise_sql",
    "sql_fingerprint",
    "parse_external_source",
]
