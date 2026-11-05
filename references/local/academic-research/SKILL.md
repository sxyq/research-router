---
name: academic-local
description: Discover papers, follow citation links, and build source-backed academic briefs with bundled public API providers, optional SerpApi Scholar access, and selected-source reading.
---

# Bundled academic research

The core workflow uses repository scripts and Python's standard library. Anonymous discovery remains available; configured API keys extend access, and SerpApi Scholar is an explicitly selected credentialed provider. One academic Agent owns these sources within the existing route; do not create a separate platform or Skill for each API.

## Source selection and coverage

Respect the user's named sources, language, dates, and publication types. Otherwise select complementary sources for the question:

| Need | Source role | Current access |
| --- | --- | --- |
| Broad discovery and publication counts | [OpenAlex](https://help.openalex.org/api/) | Bundled `openalex` provider; optional API key |
| DOI and publication metadata | Crossref | Bundled `crossref` provider; DOI registration coverage is not a complete literature index |
| Recent preprints in supported subjects | arXiv | Bundled `arxiv` provider; distinguish preprints from published versions |
| Search, references and citing papers | [Semantic Scholar](https://api.semanticscholar.org/api-docs/) | Bundled `semantic-scholar` provider; optional API key; recommendations remain outside this script |
| Scholar candidates and additional versions | Google Scholar; [SerpApi](https://serpapi.com/google-scholar-api) when useful | Existing public `google-scholar`; optional `serpapi-scholar` with an account key |
| Biomedical literature | PubMed | Bundled `pubmed` provider retrieves metadata and available abstracts; optional NCBI key |
| Chinese journals and theses | CNKI, Wanfang and relevant institutional sources | Use accessible records or user-authorized access; report gaps in domestic coverage |

For related-work and novelty surveys, follow useful references and citing papers from selected core papers when access permits. Deduplicate DOI/identical works across sources, retaining relevant version differences. Citation counts help navigation; they do not by themselves establish quality or relevance.

Semantic Scholar may omit a publisher's references and return `data: null`; the adapter reports `unavailable`, not an empty reference list. Do not infer that the paper has no references or bypass the source's access restrictions.

Distinguish returned records from a source's total matches, and both from all literature in the field. State the actual sources, query/date/language scope, pages read, unavailable sources, and missing abstracts/full text. Few or zero hits support only a finding within that search scope. Use known core papers supplied by the user to identify concrete coverage gaps when relevant; expand queries or sources for those gaps, not to reach a fixed result count.

## API access

`scripts/fast_search.py` reads keys from the process environment; it does not print keys, include request query strings in error output, or load `.env` files. If the user uses `.env`, their launcher must load it into the process environment. Keep credentials out of chat, source, and route records; do not create accounts or purchase access as part of discovery.

| Provider | Environment variable | Access |
| --- | --- | --- |
| `openalex` | `OPENALEX_API_KEY` | Optional bearer token in the request header |
| `semantic-scholar` | `SEMANTIC_SCHOLAR_API_KEY` | Optional `x-api-key` header |
| `pubmed` | `NCBI_API_KEY` | Optional E-utilities API key |
| `serpapi-scholar` | `SERPAPI_API_KEY` | Required; consumes the selected account's search allowance |

Select providers for the current research question and the user's cost/access scope. Do not automatically switch public Scholar to SerpApi after a failure. Public-provider requests and paid-provider requests return through the same result path; missing credentials or HTTP failures use the existing `unavailable` result.

`--page` selects one page and `--limit` sets its size. `search_metadata` reports source totals and paging fields when available; OpenAlex also reports `cost_usd`, while SerpApi totals are estimates. OpenAlex supports 100 records per page and ordinary paging through the first 10,000 matches; its larger cursor retrieval is not implemented here. Semantic Scholar relevance search exposes up to 1,000 ranked matches, with up to 100 per call. Its citation/reference endpoints support up to 1,000 per call. SerpApi supports up to 20 per call. Consult current [OpenAlex authentication](https://help.openalex.org/api/authentication/), [OpenAlex paging](https://help.openalex.org/api/paging/), and the selected provider's official documentation; do not treat collection sizes, prices, or quotas from a social post as permanent values.

```bash
python3 scripts/fast_search.py --provider openalex --query "large language models peer review" --limit 100 --page 2
python3 scripts/fast_search.py --provider semantic-scholar --query "large language models peer review" --limit 10
python3 scripts/fast_search.py --provider semantic-scholar --query "large language models peer review" --paper-id DOI:10.1001/jama.2023.24641 --relation citations --limit 10
python3 scripts/fast_search.py --provider pubmed --query "large language models peer review" --limit 10
# Use only after the user has configured and selected this account-backed service.
python3 scripts/fast_search.py --provider serpapi-scholar --query "large language models peer review" --limit 10
```

## Discovery and metadata

Use the selected `fast_search.py` providers without changing the route's scene, depth, platform scope, or selected-paper reading path. Run useful query variants from the research plan. OpenAlex, Semantic Scholar, PubMed, and Crossref expose metadata and abstracts when available; arXiv returns public abstracts and paper URLs. Public Scholar and SerpApi Scholar provide discovery snippets, not full abstracts. Stop on challenge or rate-limit responses and report the actual source gap.

API metadata, abstract snippets, and an open-access URL do not mean the full paper was read. Keep discovery separate from selected-source evidence.

For a selected record, use `academic-evidence/scripts/academic_public.py metadata --doi DOI`, `--arxiv ID`, or `--url URL` to retrieve public metadata and an abstract when available.

## Selected source reading

Use `academic-evidence/scripts/academic_public.py read --url URL --term "agent-selected evidence phrase"` to retrieve a public HTML paper and return matching paragraphs, headings, title, and abstract. For arXiv, the reader tries the public HTML version and a public HTML mirror; if neither is available, it returns the Atom metadata and abstract with a partial status.

For a PDF, `academic-evidence/scripts/download_pdfs.py` downloads a selected public PDF to the user-designated directory. `academic-evidence/scripts/extract_paper_brief.py` can extract PDF text when `pypdf` is already available; it does not install dependencies. If PDF text extraction is unavailable, report that gap and use accessible publisher/arXiv HTML when present.

The Agent selects papers, interprets methods/results, maps claims to passages, distinguishes author statements from verified evidence, and compares studies. Python scripts only retrieve, normalize, or extract source material. Metadata and abstracts do not replace a primary source for detailed claims.

External `anysearch`, `paper-research-router`, and `literature-evidence-audit` remain optional enhancements and are not required for any depth.
