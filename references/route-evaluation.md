# Route Evaluation

Route evaluation measures whether the selected research path produced enough evidence for the user's question. It is recorded in each route JSON under `route_evaluation`; it does not replace the source notes.

## Required fields

| Field | Range | Meaning |
| --- | ---: | --- |
| `problem_coverage` | 0-10 | How much of the requested question is covered by the collected sources. |
| `evidence_directness` | 0-10 | How directly the sources support the reported claims. Primary pages and source files score higher than search snippets. |
| `recency` | 0-10 | Whether the source dates match the requested time window. Use `null` when dates were not available. |
| `deduplication` | 0-10 | Whether repeated pages or the same claim were removed before synthesis. |
| `overall` | 0-10 | A short overall judgment based on the available dimensions. |

`execution_cost` records `query_count`, `skill_calls`, `agent_count`, and an optional `duration_seconds`. `unconfirmed_items` lists claims or requested areas that remain unsupported.

## Source coverage

`source_coverage` separates the requested evidence from what was actually collected:

```json
{
  "status": "partial",
  "requested": ["public thread body", "multi-page replies"],
  "covered": ["public thread body"],
  "missing": ["restricted replies"],
  "source_count": 3,
  "direct_source_count": 2,
  "recency_score": 8
}
```

Use `partial` when a platform or page is reachable but the evidence scope is narrower than the request. Use `unavailable` when the route cannot collect usable source material.

## Evaluation rules

1. Score source coverage against the original request, not against the number of returned pages.
2. Give direct source pages priority over search result summaries.
3. Separate an inaccessible source from a source that was read and contradicted the claim.
4. Count repeated URLs and duplicate claims once in the final evidence set.
5. Keep the route `partial` when a missing area affects the answer; add the missing area to `unconfirmed_items`.
6. Do not change shared routing rules from one route score. Use repeated records and feedback together.

## Paper basis

This lightweight evaluation follows the paper's separation of Skill quality, execution trajectory, and task outcome. See [SkillLearnBench](https://arxiv.org/abs/2604.20087), [arXiv DOI](https://doi.org/10.48550/arXiv.2604.20087), and the [benchmark repository](https://github.com/cxcscmu/SkillLearnBench).
