#!/usr/bin/env python3
"""Rebuild a markdown evidence table from a literature manifest."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import urllib.request
from pathlib import Path

KNOWN_COLUMNS = {
    "num": "编号",
    "title": "论文标题",
    "authors": "作者",
    "published_ym": "年月",
    "supporting_quote": "原文支撑",
    "source": "出处",
    "links": "链接",
    "bibtex": "BibTeX",
    "status": "状态",
}
UA = "research-router/academic-evidence/1.0"
CTX = ssl.create_default_context()


def read_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and data.get("num") is not None:
        return [data]
    if isinstance(data, dict) and isinstance(data.get("papers"), list):
        return data["papers"]
    raise ValueError("Manifest must be a JSON array, a single paper object, or an object with a 'papers' array.")


def write_manifest(path: Path, papers: list[dict]) -> None:
    path.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_authors(value) -> str:
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "; ".join(parts)
    if isinstance(value, str):
        return value.strip()
    return ""


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text[:120] or "paper"


def numbered_title_filename(paper: dict) -> str:
    num = int(paper["num"])
    title = slugify(str(paper.get("title") or f"paper_{num}"))
    return f"{num:02d}_{title}.pdf"


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
        dest.write_bytes(resp.read())


def resolve_existing_local(paper: dict, manifest_path: Path) -> Path | None:
    local_pdf = str(paper.get("local_pdf") or "").strip()
    if not local_pdf:
        return None
    path = Path(local_pdf)
    if path.is_absolute():
        return path if path.exists() else None
    resolved = manifest_path.parent / path
    return resolved if resolved.exists() else None


def relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def ensure_local_pdfs(papers: list[dict], manifest_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for paper in papers:
        existing = resolve_existing_local(paper, manifest_path)
        if existing is not None:
            continue
        pdf_url = str(paper.get("pdf_url") or "").strip()
        if not pdf_url:
            raise ValueError(f"Paper {paper.get('num')} is missing pdf_url and cannot be downloaded.")
        dest = dest_dir / numbered_title_filename(paper)
        download(pdf_url, dest)
        paper["local_pdf"] = relative_or_absolute(dest, manifest_path.parent)


def escape_cell(value: str) -> str:
    value = str(value or "").replace("|", r"\|")
    return " ".join(value.split())


def build_links(paper: dict) -> str:
    parts = []
    if paper.get("pdf_url"):
        parts.append(f"[Official PDF]({paper['pdf_url']})")
    label = paper.get("second_link_label") or ("DOI" if str(paper.get("page_url") or "").startswith("https://doi.org/") else "Page")
    if paper.get("page_url"):
        parts.append(f"[{label}]({paper['page_url']})")
    if paper.get("local_pdf"):
        parts.append(f"[Local PDF]({paper['local_pdf']})")
    return " / ".join(parts)


def cell_value(paper: dict, column: str) -> str:
    if column == "num":
        return f"[{int(paper['num'])}]"
    if column == "authors":
        return normalize_authors(paper.get("authors"))
    if column == "links":
        return build_links(paper)
    return str(paper.get(column, "") or "")


def render_table(papers: list[dict], columns: list[str]) -> str:
    header = "| " + " | ".join(KNOWN_COLUMNS[col] for col in columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, sep]
    for paper in sorted(papers, key=lambda p: int(p["num"])):
        row = [escape_cell(cell_value(paper, col)) for col in columns]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild a markdown evidence table from a manifest.")
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON file.")
    parser.add_argument("--output", type=Path, help="Write markdown table to this path.")
    parser.add_argument("--ensure-local-pdfs", type=Path, help="Download missing local PDFs into this directory before rebuilding.")
    parser.add_argument("--write-manifest", action="store_true", help="Write updated local_pdf paths back into the manifest.")
    parser.add_argument(
        "--columns",
        default="title,authors,published_ym,bibtex,supporting_quote,links",
        help="Comma-separated columns. Known columns: " + ", ".join(KNOWN_COLUMNS),
    )
    args = parser.parse_args()

    columns = [col.strip() for col in args.columns.split(",") if col.strip()]
    unknown = [col for col in columns if col not in KNOWN_COLUMNS]
    if unknown:
        raise ValueError("Unknown columns: " + ", ".join(unknown))

    papers = read_manifest(args.manifest)
    if args.ensure_local_pdfs:
        ensure_local_pdfs(papers, args.manifest, args.ensure_local_pdfs)
        if args.write_manifest:
            write_manifest(args.manifest, papers)

    table = render_table(papers, columns)
    if args.output:
        args.output.write_text(table, encoding="utf-8", newline="\n")
    else:
        print(table, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
