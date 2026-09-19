---
name: academic-evidence
description: Process discovered academic papers into verified evidence using primary PDFs, normalized metadata, stable local files, and auditable Markdown tables.
metadata:
  short-description: Verify paper evidence after academic discovery
---

# Academic Evidence Processing

This is the post-discovery evidence stage of `research-router`. It does not search for papers or replace the academic discovery Skills. It receives candidate papers from the academic route and turns them into either a bounded paper brief or defensible claim-to-evidence records.

## When the Router must call this module

Call this module after paper discovery when the user asks for any of the following:

- a selected-paper brief with abstract, section outline, and author-stated contributions
- original supporting text, claim verification, or citation audit
- literature review tables with evidence quotes
- paper PDFs, local numbered files, or normalized publication dates
- verification of a method, experiment, limitation, or empirical claim

For a simple paper list or metadata lookup, the Router may stop after discovery.

## Retrieval stages

Use the smallest stage that answers the request. This staged flow applies to papers found through Google Scholar, OpenAlex, arXiv, Crossref, publisher pages, or another academic discovery route.

1. `discovery`: return candidate metadata and links. A Google Scholar result snippet is discovery-only and is not a complete abstract.
2. `paper-brief`: after the user selects papers, supplement the abstract from a trusted source, extract the paper's section outline, and record only contributions explicitly stated by the authors. Use `academic-evidence/scripts/extract_paper_brief.py` for a local PDF.
3. `full-audit`: only after an explicit request for detailed evidence, read the primary PDF or body for methods, results, limitations, and exact quotations.

`paper-brief` should report missing abstract, outline, or contribution fields as unavailable. Do not infer a contribution and label it as author-stated. A formal table of contents is uncommon in papers; use `section_outline` for headings instead.

## Full-audit processing order

1. Receive the candidate-paper manifest and the user's claim or target section.
2. Map each claim to one primary paper; do not trust an existing table without rereading source artifacts.
3. Normalize title, authors, publication year-month, page/DOI labels, and source links.
4. Download one stable PDF per paper when local evidence is required.
5. Read the PDF body and locate the shortest passage that supports the claim. Title and abstract alone do not support a detailed method or result claim.
6. Record the quote, section/page provenance, evidence status, and unresolved gaps.
7. Rebuild or update the Markdown evidence table, then run the table verifier.

## Source priority

Prefer the official PDF or publisher PDF, then the official venue/DOI page, then arXiv, OpenReview, PMLR, ACL, or Crossref metadata. A search snippet or secondary summary is discovery evidence only.

## Bundled resources

- [references/manifest-format.md](references/manifest-format.md) defines the paper manifest.
- [references/table-spec.md](references/table-spec.md) defines the default and extended evidence tables.
- `scripts/fetch_metadata.py` fills metadata from DOI, venue, and arXiv sources.
- `scripts/download_pdfs.py` downloads deterministic numbered PDFs.
- `scripts/extract_paper_brief.py` extracts a selected paper's abstract, section outline, and author-stated contributions.
- `scripts/rebuild_evidence_table.py` renders a table and can fetch missing PDFs.
- `scripts/verify_evidence_table.py` verifies rows, links, local files, numbering, and dates.

## Router 输出要求

The parent Router records discovery Skills separately from this processing module. A completed academic route reports the candidate discovery path, the evidence-processing path `academic-evidence`, each paper's evidence status, and any unresolved claim. The smallest final Skill for evidence work is `academic-evidence`.

Do not fabricate a quote, upgrade `partial` evidence to `verified`, or report a completed PDF audit when a local PDF or body passage is missing.
