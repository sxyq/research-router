#!/usr/bin/env python3
"""Download PDFs from a literature manifest with deterministic filenames."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

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


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text[:120] or "paper"


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
        data = resp.read()
    dest.write_bytes(data)


def pick_filename(paper: dict, keep_original: bool) -> str:
    num = int(paper["num"])
    if keep_original:
        pdf_url = str(paper.get("pdf_url") or "")
        path = urllib.parse.urlparse(pdf_url).path
        name = Path(path).name or f"{num}.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return name
    title = slugify(str(paper.get("title") or f"paper_{num}"))
    return f"{num:02d}_{title}.pdf"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download PDFs from a literature manifest.")
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON file.")
    parser.add_argument("dest", type=Path, help="Destination directory for PDFs.")
    parser.add_argument("--keep-original-name", action="store_true", help="Keep the original URL basename instead of 'citation number + title'.")
    parser.add_argument("--skip-existing", action="store_true", help="Only download missing PDFs and keep existing files untouched.")
    parser.add_argument("--write-manifest", action="store_true", help="Write local_pdf back into the manifest.")
    args = parser.parse_args()

    papers = read_manifest(args.manifest)
    args.dest.mkdir(parents=True, exist_ok=True)

    for paper in papers:
        pdf_url = str(paper.get("pdf_url") or "")
        if not pdf_url:
            raise ValueError(f"Paper {paper.get('num')} is missing pdf_url.")
        filename = pick_filename(paper, keep_original=args.keep_original_name)
        dest = args.dest / filename
        if not (args.skip_existing and dest.exists()):
            download(pdf_url, dest)
        if args.write_manifest:
            paper["local_pdf"] = str(dest)

    if args.write_manifest:
        write_manifest(args.manifest, papers)
    print(f"downloaded_or_checked={len(papers)} dest={args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
