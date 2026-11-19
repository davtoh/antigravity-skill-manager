#!/usr/bin/env python3
"""True system-prompt and activation token overhead telemetry for skill_manager."""

from pathlib import Path
import re


def estimate_tokens(text: str) -> int:
    """Rough char-to-token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


def _parse_rule_frontmatter(rule_path: Path) -> tuple[str, str, int]:
    """Return (trigger, body_text, full_tokens) for a rule markdown file."""
    content = rule_path.read_text(encoding="utf-8", errors="ignore")
    trigger = "always_on"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if m:
        fm, body = m.group(1), m.group(2)
        tm = re.search(r"^trigger:\s*(.+)$", fm, re.MULTILINE)
        if tm:
            trigger = tm.group(1).strip().strip("'\"")
        return trigger, body, estimate_tokens(body)
    return trigger, content, estimate_tokens(content)


def measure_rules_overhead(config_root: Path) -> list[dict]:
    """Measure token overhead of rules/*.md grouped by trigger mode."""
    rules_dir = config_root / "rules"
    if not rules_dir.is_dir():
        return []
    rows = []
    for p in sorted(rules_dir.glob("*.md")):
        trigger, _body, tokens = _parse_rule_frontmatter(p)
        rows.append({"name": p.name, "trigger": trigger, "tokens": tokens})
    return rows


def measure_plugin_overhead(config_root: Path, parse_fn) -> list[dict]:
    """Measure prompt description tokens for installed plugin skills."""
    plugins_dir = config_root / "plugins"
    if not plugins_dir.is_dir():
        return []
    grouped: dict[str, dict] = {}
    for skill_md in sorted(plugins_dir.rglob("SKILL.md")):
        rel = skill_md.relative_to(plugins_dir)
        plugin_name = rel.parts[0] if rel.parts else "unknown"
        fm = parse_fn(skill_md)
        name = fm["name"] if fm else skill_md.parent.name
        desc = fm["description"] if fm else ""
        entry = grouped.setdefault(plugin_name, {"plugin": plugin_name, "count": 0, "tokens": 0})
        entry["count"] += 1
        entry["tokens"] += estimate_tokens(name + desc)
    return sorted(grouped.values(), key=lambda x: x["tokens"], reverse=True)


def print_overhead_breakdown(skills_dir: Path, custom_desc_tokens: int, custom_count: int, parse_fn) -> None:
    """Print breakdown across custom skills, global rules, and installed plugins."""
    config_root = skills_dir.parent
    rule_rows = measure_rules_overhead(config_root)
    always_tok = sum(r["tokens"] for r in rule_rows if r["trigger"] == "always_on")
    cond_tok = sum(r["tokens"] for r in rule_rows if r["trigger"] != "always_on")
    plugin_rows = measure_plugin_overhead(config_root, parse_fn)
    plugin_tok = sum(p["tokens"] for p in plugin_rows)
    plugin_cnt = sum(p["count"] for p in plugin_rows)

    print(f"\n[i] Custom Skills Prompt Overhead: ~{custom_desc_tokens} tokens ({custom_count} skill(s))")
    if rule_rows:
        print(f"[i] Rules Overhead: ~{always_tok} always_on tokens + ~{cond_tok} conditional (glob/model_decision) across {len(rule_rows)} rule(s)")
        for r in rule_rows:
            print(f"    - {r['name']:<30} [{r['trigger']:<14}] ~{r['tokens']} tokens")
    if plugin_rows:
        print(f"[i] Installed Plugin Skills Overhead: ~{plugin_tok} tokens across {plugin_cnt} skill(s) in {len(plugin_rows)} plugin(s)")
        for p in plugin_rows:
            print(f"    - {p['plugin']:<30} {p['count']:>2} skill(s)      ~{p['tokens']} tokens")
    total_always = custom_desc_tokens + always_tok + plugin_tok
    print(f"[i] Estimated Turn-1 Custom+Rules+Plugin Overhead: ~{total_always} tokens (excl. host base instructions & MCP schemas).")
    print("    Tip: Disable unused plugins or uninstall unneeded skills to keep Turn-1 context lean.\n")
