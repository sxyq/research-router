---
name: research-router
description: Route internet research for bug fixes, open-source or Skill discovery, and academic questions through on-demand Skills. Use when a task needs semantic requirement matching, platform selection, sub-agent depth, source verification, or a recorded final Skill path.
metadata:
  short-description: Route research by scene, depth, platform, and evidence
---

# Research Router

Use this Skill as the independent entrypoint for internet research. It decides what kind of query the user has, which platform Skills are needed, how many sub-agents are useful, and which leaf Skill actually ran.

## Required order

1. Classify the scene before judging depth:
   - `bug-fix`: find solutions, issue discussions, patches, tests, and implementation details.
   - `open-source`: discover projects, Skills, plugins, tools, and community adoption.
   - `academic`: discover papers, authors, venues, and evidence from the paper body or PDF.
2. Select one interaction mode:
   - `direct`: do not ask requirement questions; use the conditions already supplied and start.
   - `clarify`: ask one focused question at a time, update the requirement model, and continue until the target, scope, evidence, and acceptance condition are clear.
3. Build a semantic requirement model before generating any search text. Match the requirement against platform capabilities, Skill responsibilities, boundaries, evidence needs, language, recency, and access constraints. Search text is an adapter input after routing, not the routing method.
4. Read `registry/platforms.index.json`, `registry/skills.index.json`, and the selected platform/Skill entries. Load only the selected source or internal processing Skill's `SKILL.md` and its directly relevant references. Do not scan the local Skill collection and do not make MCP a required dependency.
   For the small-forum catalog, read [references/small-forums.md](references/small-forums.md) and `registry/small-forums.index.json`. Use `scripts/discourse_search.py` for public Discourse communities; use the catalog's adapter mode for other sites.
5. Select `light`, `medium`, or `deep` after semantic matching. `light` stays in the main conversation and starts 0 sub-agents; `medium` starts 2 by default and may grow to at most 4 when the task needs it; `deep` has no fixed sub-agent limit and expands by platform or evidence responsibility. The requirement still determines which platforms they cover.
6. Deduplicate overlapping candidates, keep at most two platform-specific Skills per platform, and preserve a general multi-platform Skill when it reduces repeated work.
7. Execute the selected Skills in the main conversation for `light`, or with the allocated sub-agents for `medium` and `deep`. Each sub-agent has one explicit platform or evidence role; multiple Skills on one platform run sequentially within that role. Parallel sub-agents return to the main Agent for merging, deduplication, and evidence review.
8. For every completed route, write one JSON record under `records/routes/YYYY-MM-DD/`. Record the selected depth, query variants, matched Skills, platform-Agent allocation, execution order, failures, evidence status, and the final leaf Skill path. Keep raw result bodies outside the record.
9. Return a concise result with the answer, actual source scope, final Skill path, evidence gaps, and the next action if one is required. When the user later provides a score, write a matching file under `records/feedback/YYYY-MM-DD/`.

When `scene` is `academic`, treat paper discovery and evidence processing as separate stages. After candidates are found, explicitly append the internal `academic-evidence` module whenever the request needs claim support, PDF body text, normalized citation metadata, local PDFs, or an evidence table.

Use semantic matching for every scene. Read the request as a goal, target object, domain, constraints, evidence standard, time range, language, and expected output. Only after the route is selected may the chosen Skill translate that model into platform-specific search terms.

## Depth defaults

- `light`: allocate 0 sub-agents; the main conversation handles the semantic route, adapter query expressions, and result synthesis.
- `medium`: allocate 2 sub-agents by default; add sub-agents for separate platform, supplement, or evidence-review responsibilities up to a maximum of 4.
- `deep`: allocate as many sub-agents as the task needs for distinct platform or evidence roles; there is no fixed upper limit. The reason is the required parallel work and verification scope, not the number of query expressions.

Read the relevant reference before applying details:

- [scene-routing.md](references/scene-routing.md)
- [depth-routing.md](references/depth-routing.md)
- [interaction-modes.md](references/interaction-modes.md)
- [query-generation.md](references/query-generation.md)
- [evidence-requirements.md](references/evidence-requirements.md)
- [deduplication.md](references/deduplication.md)
- [scoring-policy.md](references/scoring-policy.md)
- [failure-attribution.md](references/failure-attribution.md)

## Boundaries

- Registry entries describe known routes and candidate external Skills; they do not prove that a third-party Skill is installed or currently runnable.
- Do not copy external Skills into this directory. Resolve an installed Skill by its canonical name/path, or report it unavailable and ask before installation.
- Do not write route records, private credentials, browser cookies, or raw research caches into a project directory.
- GitHub discovery can use `github-search`; a source-level request must continue to `github-analyze` and inspect README, tree, source, dependencies, tests, Issues, and Releases.
- Academic discovery can use `autocli` or `anysearch`; a claim-to-paper check must continue to the internal `academic-evidence` module and verify the primary paper body or PDF.
