#!/usr/bin/env python3
"""Build a transparent, deterministic research route plan from one request."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry"
PLATFORM_DIRECTION_TERMS = {
    "github": ["repository", "source code", "implementation", "tests", "issues", "releases"],
    "youtube": ["tutorial", "workflow", "demo", "review", "comparison", "talk", "presentation", "walkthrough"],
    "twitter-x": ["developer", "recent discussion", "announcement", "experience", "review", "usage"],
    "v2ex": ["experience", "discussion", "problem", "recommendation", "comparison", "实际使用"],
    "discourse": ["discussion", "problem", "solution", "experience", "version", "reproduction"],
    "stackoverflow": ["error", "solution", "example", "accepted answer", "version", "api"],
    "bilibili": ["教程", "演示", "实测", "评测", "对比", "工作流"],
    "xueqiu": ["quote", "hot posts", "stock discussion", "experience", "trend", "comparison"],
    "academic": ["paper", "method", "benchmark", "evidence", "limitations", "full text"],
    "google-scholar": ["paper", "authors", "citations", "venue", "recent", "full text"],
}

CAPABILITY_TERMS = {
    "source": ("源码", "source code", "implementation", "实现"),
    "community": ("社区", "论坛", "community", "discussion", "评价", "experience", "反馈"),
    "tutorial": ("教程", "tutorial", "workflow", "演示", "demo"),
    "comparison": ("比较", "对比", "compare", "alternatives"),
    "paper": ("论文", "文献", "paper", "academic", "arxiv"),
    "issue": ("issue", "报错", "bug", "错误", "fix", "修复"),
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_phrase(value: str, limit: int = 80) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\n，。！？,;；")
    return value[:limit].strip()


def alias_matches(text: str) -> list[str]:
    aliases = read_json(REGISTRY / "aliases.json").get("aliases", {})
    lowered = text.casefold()
    found: list[str] = []
    for alias, platform_id in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        alias_lower = alias.casefold()
        if alias_lower in {"bug", "报错", "修bug", "修复问题"}:
            continue
        if re.search(r"[a-z0-9]", alias_lower):
            pattern = rf"(?<![a-z0-9]){re.escape(alias_lower)}(?![a-z0-9])"
            matched = re.search(pattern, lowered) is not None
        else:
            matched = alias_lower in lowered
        if matched and platform_id not in found:
            found.append(platform_id)

    # A bare “x” is intentionally not an alias. This contextual form is
    # specific enough to identify the platform without treating every x as X.
    if re.search(r"(?i)(?:\bx\s*(?:上|上的|平台)|x/twitter|twitter\s*/\s*x)", text):
        if "twitter-x" not in found:
            found.append("twitter-x")
    return found


def extract_requirement(request: str) -> dict[str, Any]:
    text = clean_phrase(request, 400)
    platforms = alias_matches(text)
    capabilities = [
        name for name, terms in CAPABILITY_TERMS.items()
        if any(term.casefold() in text.casefold() for term in terms)
    ]
    context = re.findall(
        r"\b(?:Python|Node(?:\.js)?|Go|Rust|Java|C\+\+|Claude Code|Codex|v\d+(?:\.\d+)*)\b",
        text,
        flags=re.IGNORECASE,
    )
    constraints: list[str] = []
    for phrase in ("开源", "免费", "无需 API Key", "无 API Key", "open source", "free", "no api key"):
        if phrase.casefold() in text.casefold():
            constraints.append(phrase)
    evidence: list[str] = []
    evidence_map = {
        "README": ("readme", "README"),
        "source": ("源码", "source code", "implementation", "实现"),
        "issues": ("issue", "问题", "报错"),
        "forums": ("论坛", "社区", "discussion", "experience", "评价", "反馈"),
        "paper body/PDF": ("论文正文", "全文", "pdf", "paper", "论文"),
        "video subtitles/metadata": ("字幕", "视频", "tutorial", "教程"),
    }
    for label, terms in evidence_map.items():
        if any(term.casefold() in text.casefold() for term in terms):
            evidence.append(label)
    if not evidence:
        evidence.append("selected source pages")

    time_terms = re.findall(
        r"(?:最近|近期|今天|本周|本月|今年|近\s*\d+\s*(?:天|周|月)|\b20\d{2}\b|recent|latest|today|this week|this month)",
        text,
        flags=re.IGNORECASE,
    )
    target_candidates = re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}", text)
    ignored = {
        "help", "find", "search", "research", "look", "youtube", "twitter", "github",
        "workflow", "source", "code", "recent", "latest", "claude", "codex",
    }
    target = next((item for item in target_candidates if item.casefold() not in ignored), "")
    if not target:
        generic_request = re.fullmatch(
            r"(?:帮我|请你?|please)?\s*(?:研究|查一下|搜索|看看|research|search)\s*(?:一下|这个)?",
            text,
            flags=re.IGNORECASE,
        )
        if not generic_request:
            target = clean_phrase(text, 60)

    return {
        "target": target,
        "goal": text,
        "capabilities": capabilities,
        "context": sorted(set(context)),
        "constraints": constraints,
        "evidence": evidence,
        "time": time_terms,
        "explicit_platforms": platforms,
    }


def decide_interaction(requirement: dict[str, Any]) -> str:
    if requirement.get("target") and requirement.get("goal"):
        return "direct"
    return "clarify"


def choose_scene(requirement: dict[str, Any]) -> str:
    text = requirement["goal"].casefold()
    if any(term in text for term in ("论文", "文献", "paper", "academic", "arxiv")):
        return "academic"
    if any(term in text for term in ("报错", "bug", "error", "issue", "修复", "fix")):
        return "bug-fix"
    if any(term in text for term in ("开源", "github", "skill", "插件", "source code", "源码")):
        return "open-source"
    return "community"


def choose_depth(requirement: dict[str, Any], scene: str) -> str:
    text = requirement["goal"].casefold()
    deep_terms = (
        "深入", "完整", "全面", "深度", "deep", "full text", "全文", "源码实现", "source code",
        "implementation", "详细核验", "cross-platform", "跨平台", "多平台", "all details",
    )
    medium_terms = (
        "比较", "对比", "compare", "几个", "multiple", "最近", "近期", "recent", "latest",
        "社区", "论坛", "评价", "experience", "tutorial", "教程",
    )
    if any(term in text for term in deep_terms):
        return "deep"
    if len(requirement.get("explicit_platforms", [])) > 1 or any(term in text for term in medium_terms):
        return "medium"
    if scene == "academic" and "paper body/PDF" in requirement.get("evidence", []):
        return "deep"
    return "light"


def _append_unique(values: list[str], value: str) -> None:
    value = clean_phrase(value, 180)
    if value and value.casefold() not in {item.casefold() for item in values}:
        values.append(value)


def generate_base_queries(requirement: dict[str, Any], depth: str) -> list[str]:
    target = requirement["target"]
    goal = requirement["goal"]
    capabilities = requirement.get("capabilities") or ["research workflow"]
    context = requirement.get("context") or []
    constraints = requirement.get("constraints") or []
    evidence = requirement.get("evidence") or ["source pages"]
    context_text = " ".join(context)
    constraint_text = " ".join(constraints)
    evidence_text = " ".join(evidence)
    queries: list[str] = []
    templates = [
        f"{target} {goal}",
        f"{target} capability {capabilities[0]}",
        f"{target} research workflow implementation",
        f"{target} open source alternatives maintenance community",
        f"{target} source code adapter tests issues releases",
        f"{target} practical experience discussion comparison",
        f"{target} tutorial demo workflow review",
        f"{target} evidence {evidence_text}",
        f"{target} {context_text} {constraint_text}".strip(),
        f"{target} user feedback recent discussion",
        f"{target} English terminology {capabilities[0]}",
        f"{target} 中文 经验 教程 讨论",
        f"{target} failure modes limitations reproducibility",
        f"{target} official documentation primary source",
        f"{target} community adoption real-world usage",
        f"{target} compare competing tools and workflows",
        f"{target} benchmark evaluation evidence",
        f"{target} issue workaround version compatibility",
        f"{target} repository examples integration",
        f"{target} recent changes releases announcements",
        f"{target} claim verification independent sources",
        f"{target} source reading result limitations",
        f"{target} platform-specific search terms",
        f"{target} acceptance criteria for {goal}",
        f"{target} alternative wording {capabilities[0]}",
        f"{target} primary evidence and counterexamples",
        f"{target} implementation details and user reports",
        f"{target} latest public results",
    ]
    for value in templates:
        _append_unique(queries, value)
    minimum = {"light": 12, "medium": 16, "deep": 20}[depth]
    return queries[: max(minimum, 12)]


def load_platform(platform_id: str) -> dict[str, Any] | None:
    path = REGISTRY / "platforms" / f"{platform_id}.json"
    if path.is_file():
        return read_json(path)
    index = read_json(REGISTRY / "platforms.index.json")
    for entry in index.get("catalog_only_platforms", []):
        if isinstance(entry, dict) and entry.get("platform_id") == platform_id:
            return entry
    return None


def select_platforms(requirement: dict[str, Any], scene: str, depth: str) -> list[str]:
    explicit = requirement.get("explicit_platforms") or []
    if explicit:
        return explicit
    text = requirement["goal"].casefold()
    if scene == "academic":
        return ["academic", "google-scholar"] if depth != "light" else ["academic"]
    if scene == "bug-fix":
        return ["github", "stackoverflow"] if depth != "light" else ["github"]
    if scene == "open-source":
        platforms = ["github"]
        if depth != "light" and any(term in text for term in ("社区", "评价", "反馈", "experience", "community")):
            platforms.extend(["v2ex", "youtube"])
        return platforms
    if depth == "deep" or any(term in text for term in ("跨平台", "多平台", "community", "社区")):
        return ["v2ex", "discourse", "youtube"]
    return ["v2ex"]


def rewrite_queries(requirement: dict[str, Any], platform_id: str, base_queries: list[str]) -> list[str]:
    terms = PLATFORM_DIRECTION_TERMS.get(platform_id, ["search", "discussion", "evidence"])
    target = requirement["target"]
    queries: list[str] = []
    for index, direction in enumerate(terms):
        seed = base_queries[index % len(base_queries)]
        _append_unique(queries, f"{target} {direction} {seed}")
    for seed in base_queries[: min(8, len(base_queries))]:
        _append_unique(queries, f"{platform_id} {seed}")
    return queries


def plan_request(request: str) -> dict[str, Any]:
    requirement = extract_requirement(request)
    interaction_mode = decide_interaction(requirement)
    scene = choose_scene(requirement)
    depth = choose_depth(requirement, scene)
    base_queries = generate_base_queries(requirement, depth)
    platform_ids = select_platforms(requirement, scene, depth)
    platforms: list[dict[str, Any]] = []
    for platform_id in platform_ids:
        entry = load_platform(platform_id) or {
            "tier": 3,
            "route_skills": [],
            "depth_routes": {"light": [], "medium": [], "deep": []},
            "status": "unregistered",
        }
        routes = entry.get("depth_routes", {})
        skill_order = routes.get(depth) or entry.get("route_skills", [])
        platforms.append(
            {
                "platform_id": platform_id,
                "tier": entry.get("tier"),
                "agent_id": f"{platform_id}-agent",
                "queries": rewrite_queries(requirement, platform_id, base_queries),
                "skill_order": skill_order,
                "status": "planned",
            }
        )
    router_path = [
        {"stage": "requirement", "value": "requirement model extracted"},
        {"stage": "interaction", "value": interaction_mode},
        {"stage": "scene", "value": scene},
        {"stage": "depth", "value": depth, "reason": "scope, evidence, and parallel work"},
        {"stage": "base-query-generation", "value": f"{len(base_queries)} variants"},
        {"stage": "platform-selection", "value": ",".join(platform_ids)},
        {"stage": "platform-query-rewrite", "value": "one query set per platform"},
        {"stage": "agent-dispatch", "value": "one agent per platform"},
    ]
    return {
        "requirement": requirement,
        "interaction_mode": interaction_mode,
        "scene": scene,
        "depth": depth,
        "query_variants": base_queries,
        "platforms": platforms,
        "router_path": router_path,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    args = parser.parse_args(argv[1:])
    print(json.dumps(plan_request(args.request), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
