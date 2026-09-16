# Evidence Table Spec

Use this file when the user asks for a table schema, a default column set, or a final audit checklist.

## Default Table

Use this table when the user does not specify otherwise:

| 论文标题 | 作者 | 年月 | BibTeX | 原文支撑 | 链接 |
|---|---|---|---|---|---|

Recommended link cell patterns:

- `[Official PDF](...) / [Page](...) / [Local PDF](...)`
- `[Official PDF](...) / [DOI](...) / [Local PDF](...)`

## Common Variants

### Minimal evidence table

| 论文标题 | 作者 | 年月 | BibTeX | 原文支撑 | 链接 |
|---|---|---|---|---|---|

### Extended audit table

| 编号 | 论文标题 | 作者 | 年月 | BibTeX | 原文支撑 | 出处 | 链接 | 状态 |
|---|---|---|---|---|---|---|---|---|

Use the extended version when the user explicitly asks for page/section provenance, BibTeX, or audit status.

## Date Normalization

- Normalize to `YYYY-MM`.
- If only year is available initially, keep auditing until month is found from a primary metadata source when feasible.
- Prefer Crossref for DOI-backed normalization.

## Quote Rules

- Use PDF body text, not title-only or abstract-only evidence, unless the user explicitly allows weaker evidence.
- Keep quotes short.
- Preserve the original wording exactly when the user asks for support text.

## Final Checklist

- Table row count matches expected paper count.
- Each row maps to exactly one paper.
- Each local PDF exists.
- Numbered PDF prefixes match citation numbers.
- Link labels are semantically correct: `Page` for detail pages, `DOI` for DOI redirects.
- Chinese headings and headers were re-opened after writeback to catch encoding damage.
