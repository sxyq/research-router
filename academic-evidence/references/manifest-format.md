# Manifest Format

Use a JSON array. Each object represents one paper.

## Minimal example

```json
[
  {
    "num": 1,
    "doi": "10.1109/TSE.2025.3587794",
    "pdf_url": "https://openreview.net/pdf?id=t46MGXBqGL",
    "page_url": "https://doi.org/10.1109/TSE.2025.3587794"
  }
]
```

## Recommended fields

- `num`: integer citation number
- `title`: paper title if already known
- `authors`: array of strings or a single semicolon-separated string
- `published_ym`: `YYYY-MM`
- `bibtex`: BibTeX entry string used in the review table
- `supporting_quote`: exact supporting quote from the PDF body
- `source`: page or section provenance such as `Introduction, p.2`
- `doi`: DOI without URL wrapper when available
- `pdf_url`: primary downloadable PDF URL
- `page_url`: venue page, DOI page, or detail page
- `local_pdf`: local relative or absolute PDF path after download
- `second_link_label`: `Page` or `DOI`
- `status`: optional audit state such as `verified` or `needs-review`

## Notes

- Keep one object per citation number.
- Prefer stable detail pages in `page_url`.
- If `page_url` is a DOI redirect, set or expect `second_link_label` to `DOI`.
- `download_pdfs.py` writes `local_pdf` back into the manifest when asked to update in place.
- `rebuild_evidence_table.py --ensure-local-pdfs <dir> --write-manifest` can download missing PDFs automatically and name them as `引用编号 + 论文标题`.
