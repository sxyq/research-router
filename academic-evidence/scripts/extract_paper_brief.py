#!/usr/bin/env python3
"""Extract a bounded paper brief from a local PDF without auditing the full body."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


COMMON_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "preliminaries",
    "method",
    "methods",
    "approach",
    "experiments",
    "experimental setup",
    "results",
    "discussion",
    "limitations",
    "conclusion",
    "conclusions",
    "references",
    "acknowledgments",
}
CONTRIBUTION_MARKERS = (
    "our contributions",
    "we make the following contributions",
    "the contributions of this work",
)


def normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_heading(value: str) -> bool:
    line = normalize_line(value)
    if not 2 <= len(line) <= 120:
        return False
    lowered = line.lower().rstrip(":")
    if lowered in COMMON_HEADINGS:
        return True
    if re.match(r"^(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+", line, flags=re.I):
        return not line.endswith((".", ";", ":"))
    return False


def extract_abstract(pages: list[str]) -> tuple[str, int | None]:
    collecting = False
    parts: list[str] = []
    page_number: int | None = None
    for index, page in enumerate(pages, start=1):
        for raw_line in page.splitlines():
            line = normalize_line(raw_line)
            if not line:
                if collecting and parts and parts[-1] != "":
                    parts.append("")
                continue
            lowered = line.lower()
            if not collecting and lowered == "abstract":
                collecting = True
                page_number = index
                continue
            if not collecting and lowered.startswith("abstract:"):
                collecting = True
                page_number = index
                parts.append(line.split(":", 1)[1].strip())
                continue
            if collecting and is_heading(line) and lowered not in {"abstract", "abstract:"}:
                text = normalize_line(" ".join(parts))
                return text, page_number
            if collecting:
                parts.append(line)
                if len(" ".join(parts)) >= 6000:
                    text = normalize_line(" ".join(parts))
                    return text[:6000].rstrip(), page_number
    return normalize_line(" ".join(parts)), page_number


def extract_section_outline(pages: list[str]) -> list[dict[str, object]]:
    outline: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for page_number, page in enumerate(pages, start=1):
        for raw_line in page.splitlines():
            line = normalize_line(raw_line)
            if not is_heading(line):
                continue
            key = (line.lower(), page_number)
            if key in seen:
                continue
            seen.add(key)
            outline.append({"title": line, "page": page_number})
    return outline


def extract_contributions(pages: list[str]) -> list[dict[str, object]]:
    contributions: list[dict[str, object]] = []
    seen: set[str] = set()
    pages_seen: set[int] = set()
    for page_number, page in enumerate(pages, start=1):
        if page_number in pages_seen:
            continue
        lines = [normalize_line(line) for line in page.splitlines()]
        for index, line in enumerate(lines):
            if page_number in pages_seen:
                break
            lowered = line.lower()
            if not any(marker in lowered for marker in CONTRIBUTION_MARKERS):
                continue
            block = [line]
            for following in lines[index + 1 : index + 16]:
                if not following:
                    if len(" ".join(block)) > 180:
                        break
                    continue
                if is_heading(following):
                    break
                block.append(following)
                if len(" ".join(block)) >= 1800:
                    break
            text = normalize_line(" ".join(block))[:1800].rstrip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                pages_seen.add(page_number)
                contributions.append(
                    {
                        "text": text,
                        "type": "author-stated",
                        "source": f"primary PDF, p.{page_number}",
                    }
                )
    return contributions


def infer_title(pages: list[str]) -> str | None:
    for page in pages[:2]:
        for raw_line in page.splitlines():
            line = normalize_line(raw_line)
            if not line or is_heading(line) or len(line) > 240:
                continue
            if re.search(r"\b(?:abstract|introduction)\b", line, flags=re.I):
                continue
            return line
    return None


def build_paper_brief(
    pages: list[str],
    source: str = "",
    title: str | None = None,
) -> dict[str, object]:
    abstract_text, abstract_page = extract_abstract(pages)
    return {
        "status": "ok",
        "retrieval_stage": "paper-brief",
        "source": source,
        "title": title or infer_title(pages),
        "abstract": {
            "text": abstract_text,
            "source": "primary-pdf",
            "page": abstract_page,
            "status": "extracted" if abstract_text else "unavailable",
        },
        "section_outline": extract_section_outline(pages),
        "contributions": extract_contributions(pages),
        "full_audit": False,
    }


def read_pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on the host runtime
        raise RuntimeError("pypdf is required for paper-brief extraction") from exc
    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def read_manifest(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("papers"), list):
        return data["papers"]
    if isinstance(data, dict):
        return [data]
    raise ValueError("Manifest must be a JSON array, paper object, or object with a papers array.")


def brief_for_manifest(path: Path) -> list[dict[str, object]]:
    briefs: list[dict[str, object]] = []
    for paper in read_manifest(path):
        local_pdf = Path(str(paper.get("local_pdf") or ""))
        if not local_pdf.is_file():
            briefs.append(
                {
                    "status": "unavailable",
                    "retrieval_stage": "paper-brief",
                    "title": paper.get("title"),
                    "source": str(local_pdf),
                    "limits": ["local_pdf is missing or is not a file"],
                }
            )
            continue
        brief = build_paper_brief(
            read_pdf_pages(local_pdf),
            source=str(local_pdf),
            title=str(paper.get("title") or "") or None,
        )
        for key in ("num", "doi", "authors", "published_ym", "page_url", "pdf_url"):
            if key in paper:
                brief[key] = paper[key]
        briefs.append(brief)
    return briefs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract abstract, section outline, and author-stated contributions from selected papers."
    )
    parser.add_argument("input", type=Path, help="A local PDF or a manifest containing local_pdf paths.")
    args = parser.parse_args()
    try:
        if args.input.suffix.lower() == ".pdf":
            output: object = build_paper_brief(read_pdf_pages(args.input), source=str(args.input))
        else:
            output = brief_for_manifest(args.input)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "retrieval_stage": "paper-brief",
                    "source": str(args.input),
                    "limits": [str(exc)],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
