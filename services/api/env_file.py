from __future__ import annotations

from pathlib import Path


def read_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _parse_env_value(value.strip())
    return values


def write_env_updates(path: str | Path, updates: dict[str, str]) -> None:
    env_path = Path(path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    rendered = {key: f"{key}={_format_env_value(value)}" for key, value in updates.items()}
    remaining = dict(rendered)
    output: list[str] = []

    for raw_line in lines:
        key = _line_key(raw_line)
        if key is None or key not in rendered:
            output.append(raw_line)
            continue
        output.append(rendered[key])
        remaining.pop(key, None)

    if remaining:
        if output and output[-1].strip():
            output.append("")
        output.extend(remaining[key] for key in updates if key in remaining)

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _line_key(raw_line: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, _ = line.split("=", 1)
    return key.strip() or None


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _format_env_value(value: str) -> str:
    if not value:
        return ""
    if any(ch.isspace() for ch in value) or "#" in value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value
