#!/usr/bin/env python3
"""Verify evidence-table rows and local PDF links in markdown."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HEADER_MAP = {
    "编号": "num",
    "论文标题": "title",
    "题目": "title",
    "作者": "authors",
    "年月": "published_ym",
    "发表时间年月": "published_ym",
    "原文支撑": "supporting_quote",
    "支撑原文": "supporting_quote",
    "链接": "links",
    "BibTeX": "bibtex",
    "出处": "source",
    "状态": "status",
}


def read_manifest(path: Path) -> dict[int, dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        papers = data
    elif isinstance(data, dict) and data.get("num") is not None:
        papers = [data]
    else:
        papers = data.get("papers", [])
    return {int(p["num"]): p for p in papers}


def parse_pipe_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_rows(markdown: str) -> list[dict]:
    blocks = []
    current = []
    for line in markdown.splitlines():
        if line.strip().startswith("|"):
            current.append(line.rstrip())
        else:
            if current:
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)

    table = None
    for block in blocks:
        if len(block) >= 3 and "---" in block[1]:
            table = block
            break
    if table is None:
        return []

    raw_headers = parse_pipe_row(table[0])
    headers = [HEADER_MAP.get(h, h) for h in raw_headers]
    rows = []
    for line in table[2:]:
        cells = parse_pipe_row(line)
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        row["links"] = re.findall(r"\[(.*?)\]\((.*?)\)", row.get("links", ""))
        if "num" in row and row["num"]:
            row["num"] = int(str(row["num"]).strip("[]"))
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a markdown literature evidence table.")
    parser.add_argument("markdown", type=Path, help="Markdown file containing the evidence table.")
    parser.add_argument("--manifest", type=Path, help="Optional manifest JSON to compare against.")
    parser.add_argument("--expected-count", type=int, help="Expected row count.")
    args = parser.parse_args()

    text = args.markdown.read_text(encoding="utf-8-sig")
    rows = parse_rows(text)
    manifest = read_manifest(args.manifest) if args.manifest else {}
    manifest_keys = sorted(manifest)
    issues = []

    if "??" in text:
        issues.append("Found '??' in markdown; inspect for encoding damage.")

    if args.expected_count is not None and len(rows) != args.expected_count:
        issues.append(f"Row count mismatch: expected {args.expected_count}, found {len(rows)}.")

    if rows and "num" not in rows[0]:
        if manifest and len(rows) == len(manifest_keys):
            for row, num in zip(rows, manifest_keys):
                row["num"] = num
        else:
            for idx, row in enumerate(rows, 1):
                row["num"] = idx

    for row in rows:
        num = int(row["num"])
        published_ym = str(row.get("published_ym", "")).strip()
        if published_ym and not re.fullmatch(r"\d{4}-\d{2}", published_ym):
            issues.append(f"[{num}] invalid published_ym: {published_ym}")

        labels = [label for label, _ in row["links"]]
        if len(labels) != 3:
            issues.append(f"[{num}] expected 3 links, found {len(labels)}")
            continue
        if labels[0] != "Official PDF":
            issues.append(f"[{num}] first link should be Official PDF, found {labels[0]}")
        if labels[1] not in {"Page", "DOI"}:
            issues.append(f"[{num}] second link should be Page or DOI, found {labels[1]}")
        if labels[2] != "Local PDF":
            issues.append(f"[{num}] third link should be Local PDF, found {labels[2]}")

        local_path = Path(row["links"][2][1])
        if not local_path.is_absolute():
            local_path = args.markdown.parent / local_path
        if not local_path.exists():
            issues.append(f"[{num}] missing local PDF: {local_path}")
        elif not local_path.name.startswith(f"{num:02d}_"):
            issues.append(f"[{num}] local PDF prefix mismatch: {local_path.name}")

        paper = manifest.get(num)
        if paper:
            title = str(paper.get("title") or "").strip()
            if title and row.get("title", "").strip() != title:
                issues.append(f"[{num}] title mismatch vs manifest")
            manifest_ym = str(paper.get("published_ym") or "").strip()
            if manifest_ym and published_ym and published_ym != manifest_ym:
                issues.append(f"[{num}] published_ym mismatch vs manifest")

    if issues:
        for issue in issues:
            print(issue)
        return 1
    print(f"OK rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
