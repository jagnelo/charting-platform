#!/usr/bin/env python3
"""Build a local, controlled-storage visual board from the retrieved TC2000 media pack.

The board is an implementation aid, not an acceptance baseline. It deliberately keeps
each source image labelled and links it back to the source page so complementary states
can be reviewed together without pretending that unrelated captures are one screenshot.
"""

from __future__ import annotations

import csv
import html
import sys
from collections import defaultdict
from pathlib import Path


SURFACE_ORDER = (
    "factory-default-layout",
    "column-editor",
    "group-columns",
    "stack-columns",
    "data-grid-create",
    "data-grid-use",
    "data-grid-appearance",
    "market-gauge-create",
    "market-gauge-understand",
    "comparison-chart",
    "chart-timeframes",
    "projection-space",
    "event-markers",
    "past-performance",
    "floating-window",
    "reposition-tabs",
    "notes-window",
    "drag-value-column",
    "pinning-columns",
    "official-version-25-product-image",
    "bulls-shared-layout",
    "emmanuel-shared-layout",
)


def read_media(index_path: Path, media_dir: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with index_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            file_path = media_dir / row["media_file"]
            if not file_path.is_file():
                continue
            grouped[row["source_id"]].append({**row, "path": file_path.as_uri()})
    return grouped


def label(source_id: str) -> str:
    return source_id.replace("-", " ").replace("_", " ").title()


def build(pack_dir: Path, output: Path) -> None:
    grouped = read_media(pack_dir / "media-index.tsv", pack_dir / "media")
    ordered = [key for key in SURFACE_ORDER if key in grouped]
    ordered.extend(sorted(key for key in grouped if key not in ordered))
    total = sum(len(items) for items in grouped.values())
    sections: list[str] = []
    for source_id in ordered:
        items = grouped[source_id]
        cards = []
        for item in items:
            source = html.escape(item["source_type"])
            build_value = html.escape(item.get("source_build") or "unspecified")
            page = html.escape(item["page_url"], quote=True)
            media = html.escape(item["media_url"], quote=True)
            filename = html.escape(item["media_file"])
            cards.append(
                f'<article class="card"><a href="{media}"><img src="{item["path"]}" alt="{filename}"></a>'
                f'<div class="meta"><strong>{filename}</strong><span>{source} · build {build_value}</span>'
                f'<a href="{page}">source page</a></div></article>'
            )
        sections.append(f'<section><h2>{html.escape(label(source_id))} <small>{len(items)} references</small></h2><div class="grid">{"".join(cards)}</div></section>')

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>TC2000 V25 composite visual reference board</title>
<style>
:root {{ color-scheme: dark; background:#0d1217; color:#dce7ee; font:13px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
body {{ margin:0; padding:24px; }} header {{ position:sticky; top:0; z-index:2; margin:-24px -24px 20px; padding:18px 24px; background:#141d25ee; border-bottom:1px solid #33424d; backdrop-filter:blur(8px); }}
h1 {{ margin:0 0 6px; font-size:24px; }} p {{ max-width:1000px; color:#9db0bd; }} section {{ margin:28px 0 40px; }} h2 {{ border-bottom:1px solid #344550; padding-bottom:6px; }} h2 small {{ color:#7f98a8; font-size:12px; font-weight:400; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }} .card {{ overflow:hidden; background:#151d24; border:1px solid #2c3b46; border-radius:3px; }} .card img {{ display:block; width:100%; height:190px; object-fit:contain; background:#0a0e12; }} .meta {{ display:grid; gap:2px; padding:7px 8px 8px; }} .meta strong {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }} .meta span,.meta a {{ color:#8fa5b4; font-size:10px; }} a {{ color:#79b9df; }}
</style></head><body><header><h1>TC2000 Version 25 composite visual reference board</h1>
<p><strong>{total} retrieved images</strong>, grouped by product surface. This board composes complementary official/help/shared-layout media for implementation and gap analysis. It is controlled reference material, not a synthetic screenshot baseline; each card preserves its source/build context.</p></header>
{"".join(sections)}
</body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"wrote {output} with {total} images across {len(ordered)} surfaces")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: build-tc2000-reference-board.py <pack-dir> <output-html>")
    build(Path(sys.argv[1]), Path(sys.argv[2]))
