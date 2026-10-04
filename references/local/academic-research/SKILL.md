---
name: academic-local
description: Discover papers and build source-backed academic briefs using bundled OpenAlex, Crossref, arXiv, Google Scholar, and public HTML retrieval.
---

# Bundled academic research

The core workflow uses repository scripts and public endpoints. It does not require sibling academic Skills or API credentials.

## Discovery and metadata

Use `scripts/fast_search.py` with `openalex`, `crossref`, `arxiv`, or `google-scholar`. Run several query variants when the Agent's research plan calls for them. OpenAlex and Crossref results include public metadata and abstracts when exposed; arXiv returns its public abstract and paper URLs. Google Scholar is bounded HTML discovery and may return snippets only; stop on challenge or rate-limit responses.

For a selected record, use `academic-evidence/scripts/academic_public.py metadata --doi DOI`, `--arxiv ID`, or `--url URL` to retrieve public metadata and an abstract when available.

## Selected source reading

Use `academic-evidence/scripts/academic_public.py read --url URL --term "agent-selected evidence phrase"` to retrieve a public HTML paper and return matching paragraphs, headings, title, and abstract. For arXiv, the reader tries the public HTML version and a public HTML mirror; if neither is available, it returns the Atom metadata and abstract with a partial status.

For a PDF, `academic-evidence/scripts/download_pdfs.py` downloads a selected public PDF to the user-designated directory. `academic-evidence/scripts/extract_paper_brief.py` can extract PDF text when `pypdf` is already available; it does not install dependencies. If PDF text extraction is unavailable, report that gap and use accessible publisher/arXiv HTML when present.

The Agent selects papers, interprets methods/results, maps claims to passages, distinguishes author statements from verified evidence, and compares studies. Python scripts only retrieve, normalize, or extract source material. Metadata and abstracts do not replace a primary source for detailed claims.

External `anysearch`, `paper-research-router`, and `literature-evidence-audit` remain optional enhancements and are not required for any depth.
