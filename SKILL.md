---
name: research-router
description: Route internet research for bug fixes, open-source or Skill discovery, and academic questions through on-demand Skills. Use when a task needs requirement-driven query expansion, platform selection, layered search depth, source verification, or a recorded final Skill path.
metadata:
  short-description: Route research by scene, depth, platform, and evidence
---

# Research Router

Use this Skill as the independent entrypoint for internet research. It decides what kind of query the user has, how much query expansion is justified, which platform Skills are needed, and which leaf Skill actually ran.

## Required order

1. Classify the scene before judging depth:
   - `bug-fix`: find solutions, issue discussions, patches, tests, and implementation details.
   - `open-source`: discover projects, Skills, plugins, tools, and community adoption.
   - `academic`: discover papers, authors, venues, and evidence from the paper body or PDF.
2. Select one interaction mode:
   - `direct`: do not ask requirement questions; use the conditions already supplied and start.
   - `clarify`: ask one focused question at a time, update the requirement model, and continue until the target, scope, evidence, and acceptance condition are clear.
3. Convert the requirement into several meaning-preserving query variants. Query variants must come from the user's goal, capability, constraints, platform terms, and evidence requirement. Do not generate random synonyms or rely on one title keyword.
4. Read `registry/platforms.index.json`, `registry/skills.index.json`, and the selected platform/Skill entries. Load only the selected external Skill's `SKILL.md` and its directly relevant references. Do not scan the local Skill collection and do not make MCP a required dependency.
5. Select `light`, `medium`, or `deep` from query count, evidence depth, and parallel work. Platform count comes from the requirement and does not determine depth.
6. Deduplicate overlapping candidates, keep at most two platform-specific Skills per platform, and preserve a general multi-platform Skill when it reduces repeated work.
7. Execute the selected Skills. One Agent owns one platform; if that platform has multiple Skills, that Agent runs them sequentially. Deep research may run multiple platform Agents in parallel, then the main Agent merges, deduplicates, and checks evidence.
8. For every completed route, write one JSON record under `records/routes/YYYY-MM-DD/`. Record the selected depth, query variants, matched Skills, platform-Agent allocation, execution order, failures, evidence status, and the final leaf Skill path. Keep raw result bodies outside the record.
9. Return a concise result with the answer, actual source scope, final Skill path, evidence gaps, and the next action if one is required. When the user later provides a score, write a matching file under `records/feedback/YYYY-MM-DD/`.

## Depth defaults

- `light`: about 2–4 requirement-derived query variants; one Agent may use one multi-platform Skill. Add a specialist only for an explicit capability gap.
- `medium`: about 5–10 variants; use one Agent per requested platform and the highest-ranked applicable Skill or sequential specialist supplement.
- `deep`: 11 or more variants, or a request for source-level/full-text evidence; use parallel platform Agents and run each platform's matched Skills sequentially. Do not use a fixed budget as a reason to omit a required source check.

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
- Academic discovery can use `autocli` or `anysearch`; a claim-to-paper check must continue to `literature-evidence-audit` and verify the primary paper body or PDF.
