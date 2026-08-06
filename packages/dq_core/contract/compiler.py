"""Guarantees → check_library → CheckDef Compiler. [DETERMINISM] [SCHEMA-MAP]

Der EINZIGE Ort, an dem aus einer semantischen Garantie (Contract-Schema v1,
HANDOVER §1.5) ausführbares SQL wird. Es gibt KEINEN Roh-SQL-Pfad — Gate G1
gilt absolut; `type: sql` o. ä. existiert nicht.

Gates:  G1  kein SQL im Contract; jede Garantie mappt auf ein Library-Template
        G2  '{schema}' bleibt wörtlich im Output und wird erst zur Laufzeit
            gebunden (bind_schema) — nie hartkodiert
        S2  dreistufige Identifier-Verteidigung: Regex → optionale Inventar-
            Existenzprüfung → Quote-Escaping
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..library.check_library import check_by_id, load_library
from ..engine.models import CheckDef, DatasetConfig, VALID_ENFORCEMENT, VALID_OWNERS, VALID_SEVERITIES, VALID_KINDS

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

# Erkennt ungebundene Template-Tokens (<SPALTE>, :<YEAR>) — NICHT '{schema}'.
_UNBOUND_TOKEN = re.compile(r":?<[A-Za-z0-9_]+>")


class CompileError(ValueError):
    pass


@dataclass(frozen=True)
class SegmentDetailSpec:
    check_name: str
    segment_column: str
    detail_sql: str
    threshold_value: float
    max_segments: int


def _ident(value: Any, where: str, known: set[str] | None = None) -> str:
    """S2: validate one identifier. Regex, optional inventory existence, escape."""
    s = str(value or "")
    if not SAFE_IDENTIFIER.match(s):
        raise CompileError(f"[S2] Unsicherer Identifier {s!r} in {where}")
    if known is not None and s not in known:
        raise CompileError(f"[S2] Identifier {s!r} in {where} existiert nicht im Inventar")
    return s.replace('"', '""')  # defense-in-depth; Regex lässt kein '"' zu


def _idents(values: Iterable[Any], where: str, known: set[str] | None = None) -> list[str]:
    out = [_ident(v, where, known) for v in values]
    if not out:
        raise CompileError(f"Leere Identifier-Liste in {where}")
    return out


def _severity(g: dict[str, Any], default: str) -> str:
    sev = str(g.get("severity") or default)
    if sev not in VALID_SEVERITIES:
        raise CompileError(f"Unbekannte severity {sev!r}")
    return sev


def _enforcement(g: dict[str, Any], default: str) -> str:
    """Durchsetzungsmodus einer Garantie: eigenes Feld > Contract-Default.
    Nur ein Dataclass-Feld — SQL bleibt unberührt (G1/G2)."""
    mode = str(g.get("enforcement") or default)
    if mode not in VALID_ENFORCEMENT:
        raise CompileError(f"Unbekannter enforcement-Modus {mode!r}")
    return mode


def parse_iso_duration(s: str) -> int:
    """ISO-8601-Dauer (PT26H, P1D …) → Sekunden."""
    m = _ISO_DURATION.match(str(s or ""))
    if not m or not any(m.groups()):
        raise CompileError(f"max_age muss ISO-8601-Dauer sein (z. B. PT24H), nicht {s!r}")
    d, h, mi, sec = (int(g or 0) for g in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def _bind(template_id: str, dataset: str, params: dict[str, Any]) -> str:
    """Template-SQL binden. '{schema}' bleibt wörtlich erhalten (G2)."""
    entry = check_by_id(template_id)
    if entry is None or not entry.get("sql_template"):
        raise CompileError(f"Unbekannte/leere templateId {template_id!r}")
    sql = entry["sql_template"].replace("{dataset}", dataset)
    # längste Tokens zuerst, damit <MAX> nicht in <MAX_X> kollidiert
    for token in sorted(params.keys(), key=len, reverse=True):
        sql = sql.replace(token, str(params[token]))
    leftover = _UNBOUND_TOKEN.search(sql)
    if leftover:
        raise CompileError(f"{template_id}: ungebundener Parameter {leftover.group(0)!r}")
    return sql


def _mk(template_id: str, dataset: str, params: dict[str, Any], *,
        name: str, expect: str, severity: str, owner: str, unit: str = "",
        kind: str = "internal_gate", enforcement: str = "monitor") -> CheckDef:
    return CheckDef(name=name, sql=_bind(template_id, dataset, params),
                    expect=expect, severity=severity, type=template_id,
                    unit=unit, owned_by=owner, kind=kind, enforcement=enforcement)


# ── Typed literal binding for the generic checks[] path ───────────────────────
# Guarantees compile through _ident/_bind; library-instantiated checks bind each
# param by its declared `type` (check_library.json). identifier → S2 (_ident);
# literals are escaped per type and injected where the template supplies the
# surrounding quotes. `expr` (raw SQL fragments — cross_field's <REGEL>, the
# compiler-only <KEY_EXPR>) is deliberately NOT bindable here: raw SQL stays
# deferred (HANDOVER §5).
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def _lit_number(value: Any, where: str) -> str:
    s = str(value).strip()
    if not _NUMBER.match(s):
        raise CompileError(f"[checks] {where}: {value!r} ist keine Zahl")
    return s


def _lit_string(value: Any, where: str) -> str:
    """String-/Regex-Literal: einfache Quotes verdoppeln; die umschließenden
    Quotes liefert das Template ('<TOKEN>'). Ein Ausbruch aus dem Literal ist
    damit unmöglich (HANA kennt kein Backslash-Escaping in String-Literalen)."""
    return str(value).replace("'", "''")


def _lit_value_list(value: Any, where: str) -> str:
    """value_list → komma-getrennte, je Eintrag gequotete SQL-Liste ('a','b').
    Die Klammern liefert das Template (… NOT IN (<TOKEN>))."""
    items = list(value) if isinstance(value, (list, tuple)) else [value]
    items = [str(v) for v in items if str(v) != ""]
    if not items:
        raise CompileError(f"[checks] {where}: leere Werteliste")
    return ", ".join("'" + v.replace("'", "''") + "'" for v in items)


_LITERAL_BINDERS = {
    "number": _lit_number,
    "string": _lit_string,
    "regex": _lit_string,
    "value_list": _lit_value_list,
}


def _bind_typed(template: str, dataset: str, bound: dict[str, str], *, where: str) -> str:
    """Einmalige Token-Substitution. '{schema}' bleibt wörtlich (G2). Eine
    einzige re.sub-Passage verhindert, dass ein Literalwert, der zufällig ein
    anderes Token enthält (z. B. Regex mit '<MIN>'), erneut ersetzt wird."""
    unbound = set(_UNBOUND_TOKEN.findall(template)) - set(bound)
    if unbound:
        raise CompileError(
            f"{where}: Template-Token {sorted(unbound)!r} ohne Parameter (Library-Inkonsistenz)"
        )
    sql = template.replace("{dataset}", dataset)
    if not bound:
        return sql
    pattern = re.compile("|".join(re.escape(t) for t in sorted(bound, key=len, reverse=True)))
    return pattern.sub(lambda m: bound[m.group(0)], sql)


def _compile_check(chk: dict[str, Any], dataset: str, *, owner: str,
                   cols: set[str] | None, where: str,
                   enforcement_default: str = "monitor") -> CheckDef:
    """Eine library-instanziierte checks[]-Position → CheckDef. Die semantische
    Validierung (id existiert, Parameter vollständig & typgerecht) lebt hier,
    nicht im (bewusst library-agnostischen) Validator."""
    cid = str(chk.get("id") or "")
    entry = check_by_id(cid)
    if entry is None:
        raise CompileError(f"{where}: unbekannte Check-ID {cid!r}")
    template = entry.get("sql_template") or ""
    if not template:
        raise CompileError(
            f"{where}: Check {cid!r} hat kein sql_template — Roh-SQL ist in dieser "
            f"Iteration nicht freigeschaltet (HANDOVER §5)"
        )
    specs = {p["token"]: p for p in entry.get("params", [])}
    given = chk.get("params") or {}
    if not isinstance(given, dict):
        raise CompileError(f"{where}: params muss ein Objekt sein")
    missing = set(specs) - set(given)
    if missing:
        raise CompileError(f"{where}: fehlende Parameter {sorted(missing)!r} für {cid!r}")
    extra = set(given) - set(specs)
    if extra:
        raise CompileError(f"{where}: unbekannte Parameter {sorted(extra)!r} für {cid!r}")
    bound: dict[str, str] = {}
    for token, spec in specs.items():
        ptype = str(spec.get("type") or "")
        w = f"{where}.params.{token}"
        if ptype == "identifier":
            bound[token] = _ident(given[token], w, cols)
        elif ptype in _LITERAL_BINDERS:
            bound[token] = _LITERAL_BINDERS[ptype](given[token], w)
        else:
            raise CompileError(
                f"{where}: Parametertyp {ptype!r} ({token}) ist im checks:-Pfad nicht "
                f"unterstützt (Roh-SQL-Ausdrücke sind deferred)"
            )
    expect = str(chk.get("expect") or entry.get("default_expect") or "")
    if not expect:
        raise CompileError(f"{where}: expect fehlt (kein default_expect in der Library)")
    severity = str(chk.get("severity") or entry.get("default_severity") or "warn")
    if severity not in VALID_SEVERITIES:
        raise CompileError(f"{where}: unbekannte severity {severity!r}")
    idents = [bound[t] for t, s in specs.items() if s.get("type") == "identifier"]
    name = "_".join([cid, *idents]) if idents else cid
    return CheckDef(name=name, sql=_bind_typed(template, dataset, bound, where=where),
                    expect=expect, severity=severity, type=cid,
                    unit=str(entry.get("unit") or ""), owned_by=owner,
                    enforcement=_enforcement(chk, enforcement_default))


def compile_contract(
    contract: dict[str, Any],
    *,
    inventory_columns: set[str] | None = None,
) -> DatasetConfig:
    """Contract-Dict (validiert, §1.5) → DatasetConfig mit '{schema}'-Platzhalter.

    `inventory_columns`: optionaler Spalten-Snapshot des Datasets; wenn gesetzt,
    wird jede referenzierte Spalte gegen das Inventar geprüft (S2 Stufe 2).
    """
    dataset = _ident(contract.get("dataset") or contract.get("product"), "dataset")
    owner = str(contract.get("owned_by", "platform"))
    if owner not in VALID_OWNERS:
        raise CompileError(f"owned_by muss {sorted(VALID_OWNERS)} sein, nicht {owner!r}")
    kind = str(contract.get("kind", "internal_gate"))
    if kind not in VALID_KINDS:
        raise CompileError(f"kind muss {sorted(VALID_KINDS)} sein, nicht {kind!r}")
    g = contract.get("guarantees") or {}
    enf_default = str(contract.get("enforcement_default") or "monitor")
    if enf_default not in VALID_ENFORCEMENT:
        raise CompileError(f"Unbekannter enforcement_default {enf_default!r}")
    cols = inventory_columns
    checks: list[CheckDef] = []

    schema_g = g.get("schema")
    if schema_g:
        expected = _idents(schema_g.get("columns") or [], "guarantees.schema.columns", cols)
        closed = (schema_g.get("mode") or "closed") == "closed"
        checks.append(_mk(
            "schema", dataset, {},
            name="schema_columns",
            expect=("= %d" % len(expected)) if closed else (">= %d" % len(expected)),
            severity=_severity(schema_g, "critical"), owner=owner, kind=kind,
            enforcement=_enforcement(schema_g, enf_default),
        ))

    for i, key in enumerate(g.get("keys") or []):
        kcols = _idents(key.get("columns") or [], f"guarantees.keys[{i}].columns", cols)
        sev = _severity(key, "critical")
        enf = _enforcement(key, enf_default)
        if len(kcols) == 1:
            checks.append(_mk("duplicate", dataset, {"<SPALTE>": kcols[0]},
                              name=f"key_{kcols[0]}_unique", expect="= 0",
                              severity=sev, owner=owner, kind=kind, enforcement=enf))
        else:
            key_expr = " || '|' || ".join(f'"{c}"' for c in kcols)
            checks.append(_mk("duplicate_composite", dataset, {"<KEY_EXPR>": key_expr},
                              name="key_" + "_".join(kcols) + "_unique", expect="= 0",
                              severity=sev, owner=owner, kind=kind, enforcement=enf))

    for i, ref in enumerate(g.get("referential") or []):
        where = f"guarantees.referential[{i}]"
        fk = _idents(ref.get("fk") or [], f"{where}.fk", cols)
        pk = _idents(ref.get("parent_key") or [], f"{where}.parent_key", None)
        parent = _ident(ref.get("parent"), f"{where}.parent")
        if len(fk) != 1 or len(pk) != 1:
            raise CompileError(f"{where}: zusammengesetzte FKs sind in v1 nicht unterstützt")
        checks.append(_mk(
            "reference_integrity", dataset,
            {"<DIMENSION>": parent, "<FK>": fk[0], "<PK>": pk[0]},
            name=f"ref_{fk[0]}_{parent}", expect="= 0",
            severity=_severity(ref, "fail"), owner=owner, kind=kind,
            enforcement=_enforcement(ref, enf_default),
        ))

    fresh = g.get("freshness")
    if fresh:
        col = _ident(fresh.get("column"), "guarantees.freshness.column", cols)
        seconds = parse_iso_duration(fresh.get("max_age"))
        checks.append(_mk("freshness", dataset, {"<SPALTE>": col},
                          name=f"freshness_{col}", expect=f"< {seconds}",
                          severity=_severity(fresh, "warn"), owner=owner, unit="s", kind=kind,
                          enforcement=_enforcement(fresh, enf_default)))

    vol = g.get("volume")
    if vol and vol.get("min_rows") is not None:
        min_rows = int(vol["min_rows"])
        checks.append(_mk("row_count", dataset, {},
                          name="volume_min_rows", expect=f">= {min_rows}",
                          severity=_severity(vol, "warn"), owner=owner, kind=kind,
                          enforcement=_enforcement(vol, enf_default)))
    # volume.baseline=rolling ist Observability-Konfiguration (dq_baselines),
    # kein Contract-Check. volume_anomaly bleibt ein interner Runtime-Check.

    for i, comp in enumerate(g.get("completeness") or []):
        col = _ident(comp.get("column"), f"guarantees.completeness[{i}].column", cols)
        max_null_pct = round(100.0 - float(comp.get("min_pct", 100)), 4)
        segment_by = comp.get("segment_by")
        if segment_by:
            seg = _ident(segment_by, f"guarantees.completeness[{i}].segment_by", cols)
            checks.append(CheckDef(
                name=f"completeness_{col}_by_{seg}",
                sql=_segment_scalar_sql(dataset, col, seg, max_null_pct),
                expect="= 0",
                severity=_severity(comp, "warn"),
                type="completeness_pct_segment",
                unit="segments",
                owned_by=owner,
                kind=kind,
                enforcement=_enforcement(comp, enf_default),
            ))
        else:
            checks.append(_mk("completeness_pct", dataset, {"<SPALTE>": col},
                              name=f"completeness_{col}", expect=f"<= {max_null_pct}",
                              severity=_severity(comp, "warn"), owner=owner, unit="%", kind=kind,
                              enforcement=_enforcement(comp, enf_default)))

    for i, nn in enumerate(g.get("not_null") or []):
        sev = _severity(nn, "fail")
        enf = _enforcement(nn, enf_default)
        for col in _idents(nn.get("columns") or [], f"guarantees.not_null[{i}].columns", cols):
            checks.append(_mk("missing", dataset, {"<SPALTE>": col},
                              name=f"{col}_not_null", expect="= 0",
                              severity=sev, owner=owner, kind=kind, enforcement=enf))

    # checks[]: library-instanziierte Checks (interne Gates, HANDOVER Iteration 1).
    # Additiv zu den Garantien und nach ihnen kompiliert — eine Quelle, ein
    # compiler_hash. Bindung typgesteuert (S2 für Identifier, Escaping für Literale).
    checks_in = contract.get("checks") or []
    if not isinstance(checks_in, list):
        raise CompileError("checks muss eine Liste sein")
    seen = {c.name for c in checks}
    for i, chk in enumerate(checks_in):
        if not isinstance(chk, dict):
            raise CompileError(f"checks[{i}] muss ein Objekt sein")
        cd = _compile_check(chk, dataset, owner=owner, cols=cols, where=f"checks[{i}]",
                            enforcement_default=enf_default)
        if cd.name in seen:  # readable name collided (same check+column twice) → disambiguate
            cd.name = f"{cd.name}_{i}"
        seen.add(cd.name)
        checks.append(cd)

    return DatasetConfig(
        dataset=dataset,
        schema="{schema}",  # [SCHEMA-MAP] G2: Bindung erst zur Laufzeit
        contract_version=str(contract.get("version") or ""),
        owned_by=owner,
        checks=checks,
    )


def compiler_hash(contract: dict[str, Any]) -> str:
    """A4: Determinismus-Hash = f(Contract-Inhalt, Library-Version)."""
    import yaml
    contract_hash = hashlib.sha256(
        yaml.safe_dump(_compiled_contract_payload(contract), sort_keys=True).encode()
    ).hexdigest()[:16]
    library_version = str(load_library().get("version", "1"))
    return hashlib.sha256(f"{contract_hash}:{library_version}".encode()).hexdigest()[:16]


def compiled_contract_hash(contract: dict[str, Any]) -> str:
    """Hash only fields that can change compiled checks.yml output."""
    import yaml
    return hashlib.sha256(
        yaml.safe_dump(_compiled_contract_payload(contract), sort_keys=True).encode()
    ).hexdigest()[:16]


def _compiled_contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    payload = dict(contract)
    payload.pop("observability", None)
    return payload


def segment_detail_specs(
    contract: dict[str, Any],
    *,
    schema: str = "{schema}",
    inventory_columns: set[str] | None = None,
) -> list[SegmentDetailSpec]:
    dataset = _ident(contract.get("dataset") or contract.get("product"), "dataset")
    g = contract.get("guarantees") or {}
    specs: list[SegmentDetailSpec] = []
    for i, comp in enumerate(g.get("completeness") or []):
        if not comp.get("segment_by"):
            continue
        col = _ident(comp.get("column"), f"guarantees.completeness[{i}].column", inventory_columns)
        seg = _ident(comp.get("segment_by"), f"guarantees.completeness[{i}].segment_by", inventory_columns)
        max_null_pct = round(100.0 - float(comp.get("min_pct", 100)), 4)
        max_segments = int(comp.get("max_segments") or 50)
        max_segments = min(max(max_segments, 1), 500)
        sql = _segment_detail_sql(dataset, col, seg, max_null_pct, max_segments, schema=schema)
        specs.append(SegmentDetailSpec(
            check_name=f"completeness_{col}_by_{seg}",
            segment_column=seg,
            detail_sql=sql,
            threshold_value=max_null_pct,
            max_segments=max_segments,
        ))
    return specs


def _segment_null_pct_expr(column: str) -> str:
    return (
        f'ROUND(100.0 * COUNT(CASE WHEN "{column}" IS NULL THEN 1 END) '
        "/ NULLIF(COUNT(*), 0), 2)"
    )


def _segment_select_sql(
    dataset: str,
    column: str,
    segment_column: str,
    threshold: float,
    *,
    schema: str = "{schema}",
) -> str:
    expr = _segment_null_pct_expr(column)
    return (
        f'SELECT "{segment_column}" AS segment_value, {expr} AS actual_value '
        f'FROM "{schema}"."{dataset}" '
        f'GROUP BY "{segment_column}" '
        f'HAVING {expr} > {threshold}'
    )


def _segment_scalar_sql(dataset: str, column: str, segment_column: str, threshold: float) -> str:
    return (
        "SELECT COUNT(*) FROM ("
        + _segment_select_sql(dataset, column, segment_column, threshold)
        + ") violating_segments"
    )


def _segment_detail_sql(
    dataset: str,
    column: str,
    segment_column: str,
    threshold: float,
    max_segments: int,
    *,
    schema: str = "{schema}",
) -> str:
    return (
        _segment_select_sql(dataset, column, segment_column, threshold, schema=schema)
        + f" ORDER BY actual_value DESC LIMIT {int(max_segments)}"
    )


def bind_schema(config: DatasetConfig, schema: str) -> DatasetConfig:
    """[SCHEMA-MAP] Laufzeit-Bindung: ersetzt '{schema}' in allen Checks.

    Der einzige Ort, an dem der Platzhalter aufgelöst wird (G2).
    """
    bound = _ident(schema, "environment.schema")
    config.schema = bound
    for c in config.checks:
        c.sql = c.sql.replace("{schema}", bound)
    return config
