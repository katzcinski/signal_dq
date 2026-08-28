#!/usr/bin/env python3
"""Baut aus einer Artifact-Seite eine eigenstaendige, verschickbare HTML-Datei.

Die Seiten unter `docs/interactive/` sind fuer den Artifact-Host geschrieben:
sie beginnen direkt mit `<title>`/`<style>` und holen ihre Schriften vom
Google-CDN. Zum Weitergeben an Kunden braucht es dagegen **eine** Datei, die
ohne Host und ohne Netz funktioniert — inklusive Schriften, damit die Typografie
auch offline und ohne externen Aufruf stimmt (fuer viele Kunden-IT-Abteilungen
ist Letzteres der eigentliche Punkt).

    python3 scripts/build_pitch_standalone.py \
        docs/interactive/kundenpitch-datasphere-bdc.html \
        --out dist/Signal_Datasphere.html

Ohne Netzzugang faellt das Skript auf den CDN-Link zurueck (Datei bleibt
verwendbar, Schriften werden dann beim Oeffnen geladen).
"""
from __future__ import annotations

import argparse
import base64
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Deutsch (inkl. Umlaute und Eszett) liegt vollstaendig im latin-Subset; die
# uebrigen Subsets — kyrillisch, griechisch, vietnamesisch — sparen wir uns.
KEEP_SUBSET = "latin"


def fetch(url: str) -> bytes:
    """Erst urllib, dann curl — je nach Umgebung geht mal das eine, mal das andere."""
    try:
        return urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read()
    except Exception:
        return subprocess.run(
            ["curl", "-sS", "-A", UA, url], capture_output=True, check=True
        ).stdout


def inline_fonts(css_url: str) -> str | None:
    """Google-Fonts-CSS in @font-face-Regeln mit eingebetteten woff2 uebersetzen."""
    try:
        css = fetch(css_url).decode("utf-8")
    except Exception as exc:  # kein Netz / blockiert
        print(f"  ! Schriften nicht erreichbar ({exc}) — CDN-Link bleibt stehen", file=sys.stderr)
        return None

    blocks = re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S)
    rules: list[str] = []
    for subset, block in blocks:
        if subset != KEEP_SUBSET:
            continue
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        family = re.search(r"font-family: '([^']+)'", block)
        weight = re.search(r"font-weight: (\d+)", block)
        if not (url and family and weight):
            continue
        payload = base64.b64encode(fetch(url.group(1))).decode()
        rules.append(
            f"@font-face{{font-family:'{family.group(1)}';font-style:normal;"
            f"font-weight:{weight.group(1)};font-display:swap;"
            f"src:url(data:font/woff2;base64,{payload}) format('woff2');}}"
        )
    if not rules:
        return None
    print(f"  {len(rules)} Schriftschnitte eingebettet")
    return "\n".join(rules)


def build(src: Path, out: Path) -> None:
    raw = src.read_text(encoding="utf-8")

    title_match = re.search(r"<title>(.*?)</title>", raw, re.S)
    title = title_match.group(1).strip() if title_match else src.stem

    css_link = re.search(r'<link rel="stylesheet" href="(https://fonts\.googleapis\.com[^"]+)"', raw)
    fonts_css = inline_fonts(css_link.group(1)) if css_link else None

    # Kopfzeilen der Artifact-Fassung entfernen: Titel und die Font-<link>s.
    body = re.sub(r"<title>.*?</title>\s*", "", raw, flags=re.S)
    body = re.sub(r'<link rel="(?:preconnect|stylesheet)"[^>]*>\s*', "", body)

    # Den Seiten-<style> in den Kopf ziehen, damit nichts erst im Body greift.
    style_match = re.search(r"<style>(.*?)</style>", body, re.S)
    page_css = style_match.group(1) if style_match else ""
    body = re.sub(r"<style>.*?</style>\s*", "", body, flags=re.S, count=1)

    head_css = "\n".join(part for part in (fonts_css, page_css) if part)
    fallback_link = (
        ""
        if fonts_css or not css_link
        else f'\n<link rel="stylesheet" href="{css_link.group(1)}">'
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!doctype html>\n"
        '<html lang="de">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        '<meta name="color-scheme" content="dark">\n'
        '<meta name="theme-color" content="#0A0C0F">'
        f"{fallback_link}\n"
        f"<style>\n{head_css}\n</style>\n"
        "</head>\n"
        f"<body>\n{body.strip()}\n</body>\n"
        "</html>\n",
        encoding="utf-8",
    )
    print(f"  {out} — {out.stat().st_size / 1024:.0f} KB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Artifact-HTML unter docs/interactive/")
    ap.add_argument("--out", type=Path, required=True, help="Zieldatei (.html)")
    args = ap.parse_args()
    build(args.source, args.out)


if __name__ == "__main__":
    main()
