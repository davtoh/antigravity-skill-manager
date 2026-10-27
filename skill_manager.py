#!/usr/bin/env python3
"""
Antigravity Skill Manager (skill_manager.py)
A lightweight, zero-dependency utility to discover, search, install,
uninstall, and manage Antigravity skills from external repositories and local folders.

Portable across Windows, macOS, and Linux. All paths are resolved relative
to the user's home directory or overridable via environment variables:

  SKILL_SOURCES_DIR   — Where to clone/find external skill repos (default: ~/src)
  SKILL_MANAGER_DIR   — Where to store config and state (default: ~/.config/skill-manager
                         or %APPDATA%/skill-manager on Windows)
  ANTIGRAVITY_SKILLS_DIR — Global skills directory (default: ~/.gemini/config/skills)
"""

import sys
import os
import re
import json
import shutil
import argparse
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Portable path resolution — zero hardcoded machine-local paths
# ---------------------------------------------------------------------------

def _resolve_config_dir() -> Path:
    """Cross-platform config dir: %APPDATA%/skill-manager on Windows,
    $XDG_CONFIG_HOME/skill-manager (or ~/.config/skill-manager) elsewhere."""
    env_override = os.environ.get("SKILL_MANAGER_DIR")
    if env_override:
        return Path(env_override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "skill-manager"


def _resolve_sources_dir() -> Path:
    """Where to clone external repositories. Defaults to ~/src on all platforms."""
    env_override = os.environ.get("SKILL_SOURCES_DIR")
    return Path(env_override) if env_override else Path.home() / "src"


def _resolve_global_skills_dir() -> Path:
    """The Antigravity global skills directory."""
    env_override = os.environ.get("ANTIGRAVITY_SKILLS_DIR")
    return Path(env_override) if env_override else Path.home() / ".gemini" / "config" / "skills"


DEFAULT_SOURCES_DIR = _resolve_sources_dir()
GLOBAL_SKILLS_DIR = _resolve_global_skills_dir()
_CONFIG_DIR = _resolve_config_dir()
CONFIG_FILE = _CONFIG_DIR / "config.json"
INSTALLED_FILE = _CONFIG_DIR / "installed.json"

DEFAULT_SOURCES = [
    {
        "name": "claude-plugins-official",
        "type": "git",
        "path": str(DEFAULT_SOURCES_DIR / "claude-plugins-official"),
        "url": "https://github.com/anthropics/claude-plugins-official.git",
        "description": "Anthropic official Claude Code plugins and skills repository"
    }
]

KNOWN_ALIASES = {
    "create-skill": "skill-creator",
    "create_skill": "skill-creator",
    "make-skill": "skill-creator",
    "prompt-improver": "claude-md-improver",
    "security-scanner": "claude-security"
}


# ---------------------------------------------------------------------------
# Config & Registry helpers
# ---------------------------------------------------------------------------

def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "sources": DEFAULT_SOURCES,
            "global_skills_dir": str(GLOBAL_SKILLS_DIR)
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Warning: Failed to parse {CONFIG_FILE}: {e}", file=sys.stderr)
        return {"sources": DEFAULT_SOURCES, "global_skills_dir": str(GLOBAL_SKILLS_DIR)}


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_installed_registry():
    if not INSTALLED_FILE.exists():
        return {}
    try:
        with open(INSTALLED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_installed_registry(data):
    INSTALLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INSTALLED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------

def parse_skill_frontmatter(file_path):
    """Parses YAML frontmatter from a SKILL.md file without external dependencies."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        fm_text = match.group(1)
        name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
        name = name_match.group(1).strip().strip("'\"") if name_match else file_path.parent.name

        desc_match = re.search(
            r"^description:\s*(?:>[-+]?|\|[-+]?)?\s*\n?(.*?)(?=\n[a-zA-Z0-9_-]+:|\Z)",
            fm_text, re.DOTALL | re.MULTILINE
        )
        description = ""
        if desc_match:
            raw_desc = desc_match.group(1)
            lines = [line.strip() for line in raw_desc.splitlines() if line.strip()]
            description = " ".join(lines).strip().strip("'\"")

        return {
            "name": name,
            "description": description,
            "raw_frontmatter": fm_text,
            "full_content_len": len(content)
        }
    except Exception:
        return None


def discover_skills_in_directory(dir_path, source_name="local"):
    """Scans a directory for all SKILL.md files and extracts metadata."""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return []

    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".agents"}
    discovered = []

    for skill_file in dir_path.rglob("SKILL.md"):
        parts = skill_file.parts
        if any(skip in parts for skip in skip_dirs):
            continue

        fm = parse_skill_frontmatter(skill_file)
        if not fm:
            continue

        skill_dir = skill_file.parent
        plugin_name = None
        for i, part in enumerate(parts):
            if part in ("plugins", "external_plugins") and i + 1 < len(parts):
                plugin_name = parts[i + 1]
                break

        discovered.append({
            "name": fm["name"],
            "aliases": [k for k, v in KNOWN_ALIASES.items() if v == fm["name"]],
            "description": fm["description"],
            "skill_dir": str(skill_dir),
            "skill_file": str(skill_file),
            "source": source_name,
            "plugin": plugin_name or "",
            "size_chars": fm["full_content_len"]
        })

    return discovered


def get_all_available_skills(config):
    all_skills = []
    for src in config.get("sources", []):
        src_path = Path(src.get("path", ""))
        skills = discover_skills_in_directory(src_path, source_name=src.get("name", "source"))
        all_skills.extend(skills)
    return all_skills


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_skills(query, config):
    skills = get_all_available_skills(config)
    q = query.lower().strip()
    words = [w for w in re.split(r"\s+", q) if w]

    results = []
    for s in skills:
        score = 0
        name = s["name"].lower()
        desc = s["description"].lower()
        plugin = s["plugin"].lower()
        aliases = [a.lower() for a in s["aliases"]]

        if q in aliases or any(q == a for a in aliases):
            score += 150
        if q == name:
            score += 120
        elif q in name:
            score += 70
        if q and q == plugin:
            score += 50
        elif q and q in plugin:
            score += 30
        for w in words:
            if w in name:
                score += 35
            if any(w in a for a in aliases):
                score += 30
            if w in plugin:
                score += 20
            if w in desc:
                score += 10

        if score > 0:
            results.append((score, s))

    results.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in results]


def estimate_tokens(text):
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args, config):
    query = " ".join(args.query)
    print(f"\n[?] Searching for skills matching: '{query}'...")
    results = search_skills(query, config)

    if not results:
        print(f"[-] No skills found matching '{query}'.")
        print("    Try 'skill-manager list-all' or run 'skill-manager update-sources' to sync upstream.\n")
        return

    print(f"[+] Found {len(results)} matching skill(s):\n")
    for s in results[:10]:
        name_str = s["name"]
        if s["aliases"]:
            name_str += f" (aliases: {', '.join(s['aliases'])})"
        print(f"  * {name_str}")
        if s["plugin"]:
            print(f"    Plugin: {s['plugin']} (from source: {s['source']})")
        print(f"    Description: {s['description'][:140]}{'...' if len(s['description']) > 140 else ''}")
        print(f"    Path: {s['skill_dir']}")
        print(f"    System prompt cost if installed: ~{estimate_tokens(s['name'] + s['description'])} tokens")
        print()


def cmd_list_all(args, config):
    skills = get_all_available_skills(config)
    print(f"\n[+] Total available skills across sources: {len(skills)}\n")
    for s in sorted(skills, key=lambda x: x["name"]):
        plugin_str = f" [{s['plugin']}]" if s["plugin"] else ""
        print(f"  - {s['name']:<28} {plugin_str:<18} (source: {s['source']})")
        if s["description"]:
            print(f"    {s['description'][:100]}...")
    print(f"\nTo install any of these, run: skill-manager install <skill-name>\n")


def cmd_list_installed(args, config):
    target_dir = Path(config.get("global_skills_dir", str(GLOBAL_SKILLS_DIR)))
    print(f"\n[*] Installed Antigravity Global Skills ({target_dir}):")
    if not target_dir.exists():
        print("  (Skills directory does not exist yet)\n")
        return

    installed = []
    total_tokens = 0
    for child in target_dir.iterdir():
        if child.is_dir():
            skill_md = child / "SKILL.md"
            if skill_md.exists():
                fm = parse_skill_frontmatter(skill_md)
                name = fm["name"] if fm else child.name
                desc = fm["description"] if fm else ""
                tokens = estimate_tokens(name + desc)
                total_tokens += tokens
                installed.append((name, desc, tokens, child))

    if not installed:
        print("  No global skills installed.\n")
        return

    for name, desc, tokens, path in sorted(installed, key=lambda x: x[0]):
        print(f"  * {name:<24} (~{tokens} prompt tokens)")
        if desc:
            print(f"    {desc[:110]}...")
        print(f"    Location: {path}")

    print(f"\n[i] Total estimated system prompt overhead: ~{total_tokens} tokens across {len(installed)} installed skill(s).")
    print(f"    Tip: Uninstall unneeded skills using 'skill-manager uninstall <skill-name>' to keep context minimal.\n")


def resolve_skill_source(identifier, config):
    local_path = Path(identifier)
    if local_path.is_dir() and (local_path / "SKILL.md").exists():
        return local_path

    lookup_name = KNOWN_ALIASES.get(identifier.lower().strip(), identifier.lower().strip())

    all_skills = get_all_available_skills(config)
    for s in all_skills:
        if s["name"].lower() == lookup_name or identifier.lower() in [a.lower() for a in s["aliases"]]:
            return Path(s["skill_dir"])

    for s in all_skills:
        if lookup_name in s["name"].lower() or lookup_name in s["skill_dir"].lower():
            return Path(s["skill_dir"])

    return None


def cmd_install(args, config):
    identifier = args.skill.strip()
    target_mode = args.target.lower()
    force = args.force

    if target_mode == "global":
        dest_base = Path(config.get("global_skills_dir", str(GLOBAL_SKILLS_DIR)))
    elif target_mode == "workspace":
        dest_base = Path.cwd() / ".agents" / "skills"
    else:
        dest_base = Path(target_mode)

    dest_base.mkdir(parents=True, exist_ok=True)

    if identifier.startswith("http://") or identifier.startswith("https://") or identifier.startswith("git@"):
        print(f"[*] Git URL detected: {identifier}")
        repo_name = identifier.rstrip("/").split("/")[-1].replace(".git", "")
        dest_clone = DEFAULT_SOURCES_DIR / repo_name
        if not dest_clone.exists():
            print(f"[*] Cloning into {dest_clone}...")
            subprocess.run(["git", "clone", identifier, str(dest_clone)], check=True)
        sources = config.get("sources", [])
        if not any(s.get("path") == str(dest_clone) for s in sources):
            sources.append({
                "name": repo_name,
                "type": "git",
                "path": str(dest_clone),
                "url": identifier,
                "description": f"Imported repository {repo_name}"
            })
            config["sources"] = sources
            save_config(config)
            print(f"[+] Added {repo_name} to skill sources.")

        skills = discover_skills_in_directory(dest_clone, source_name=repo_name)
        if not skills:
            print(f"[-] No SKILL.md found in {identifier}")
            return
        if len(skills) == 1:
            skill_source_dir = Path(skills[0]["skill_dir"])
        else:
            print(f"[?] Multiple skills found in {repo_name}:")
            for sk in skills:
                print(f"    - {sk['name']}")
            print("Please specify which skill to install by name.")
            return
    else:
        skill_source_dir = resolve_skill_source(identifier, config)

    if not skill_source_dir or not (skill_source_dir / "SKILL.md").exists():
        print(f"[-] Error: Could not locate skill '{identifier}' in configured sources or local filesystem.", file=sys.stderr)
        print("    Try 'skill-manager search <keyword>' to locate the exact skill name.\n", file=sys.stderr)
        sys.exit(1)

    fm = parse_skill_frontmatter(skill_source_dir / "SKILL.md")
    skill_name = args.name if args.name else (fm["name"] if fm else skill_source_dir.name)
    target_skill_dir = dest_base / skill_name

    if target_skill_dir.exists() and not force:
        print(f"[!] Skill '{skill_name}' is already installed at: {target_skill_dir}")
        print("    Use --force to overwrite.\n")
        return

    if target_skill_dir.exists() and force:
        shutil.rmtree(target_skill_dir)

    print(f"[*] Installing '{skill_name}' from:\n    {skill_source_dir}\n    to:\n    {target_skill_dir}...")
    shutil.copytree(skill_source_dir, target_skill_dir)

    registry = load_installed_registry()
    registry[skill_name] = {
        "installed_path": str(target_skill_dir),
        "source_path": str(skill_source_dir),
        "name": skill_name,
        "description": fm["description"] if fm else "",
        "token_estimate": estimate_tokens((fm["name"] if fm else "") + (fm["description"] if fm else ""))
    }
    save_installed_registry(registry)

    print(f"[+] Successfully installed '{skill_name}' into Antigravity!")
    print(f"    Active location: {target_skill_dir / 'SKILL.md'}")
    print(f"    Prompt overhead: ~{estimate_tokens((fm['name'] if fm else '') + (fm['description'] if fm else ''))} tokens.")
    print(f"    Antigravity will now automatically detect this skill!\n")


def cmd_uninstall(args, config):
    skill_name = args.skill.strip()
    target_mode = args.target.lower()

    if target_mode == "global":
        dest_base = Path(config.get("global_skills_dir", str(GLOBAL_SKILLS_DIR)))
    elif target_mode == "workspace":
        dest_base = Path.cwd() / ".agents" / "skills"
    else:
        dest_base = Path(target_mode)

    target_skill_dir = dest_base / skill_name
    if not target_skill_dir.exists():
        print(f"[-] Skill '{skill_name}' not found in {dest_base}.\n", file=sys.stderr)
        return

    print(f"[*] Removing '{skill_name}' from {target_skill_dir}...")
    shutil.rmtree(target_skill_dir)

    registry = load_installed_registry()
    if skill_name in registry:
        del registry[skill_name]
        save_installed_registry(registry)

    print(f"[+] Successfully uninstalled '{skill_name}'.")
    print(f"    Tokens reclaimed for future prompts!\n")


def cmd_add_source(args, config):
    name = args.name.strip()
    url_or_path = args.path_or_url.strip()

    sources = config.get("sources", [])
    if any(s.get("name") == name for s in sources):
        print(f"[!] Source '{name}' already exists in configuration.")
        return

    if url_or_path.startswith("http") or url_or_path.startswith("git@"):
        dest_dir = DEFAULT_SOURCES_DIR / name
        if not dest_dir.exists():
            print(f"[*] Cloning git repository to {dest_dir}...")
            subprocess.run(["git", "clone", url_or_path, str(dest_dir)], check=True)
        src_entry = {
            "name": name,
            "type": "git",
            "path": str(dest_dir),
            "url": url_or_path,
            "description": args.description or f"Repository {name}"
        }
    else:
        local_path = Path(url_or_path)
        if not local_path.exists():
            print(f"[-] Error: Path '{url_or_path}' does not exist.", file=sys.stderr)
            return
        src_entry = {
            "name": name,
            "type": "local",
            "path": str(local_path.resolve()),
            "url": "",
            "description": args.description or f"Local source {name}"
        }

    sources.append(src_entry)
    config["sources"] = sources
    save_config(config)

    skills = discover_skills_in_directory(src_entry["path"], source_name=name)
    print(f"[+] Added source '{name}' with {len(skills)} skill(s) discovered.\n")


def cmd_update_sources(args, config):
    sources = config.get("sources", [])
    print(f"\n[*] Updating skill sources ({len(sources)} registered)...")
    for s in sources:
        if s.get("type") == "git":
            p = Path(s.get("path", ""))
            if p.exists() and (p / ".git").exists():
                print(f"  - Pulling latest updates for '{s['name']}' in {p}...")
                res = subprocess.run(["git", "-C", str(p), "pull"], capture_output=True, text=True)
                print(f"    {res.stdout.strip()}")
            else:
                print(f"  - [!] Skipping '{s['name']}', git directory not found.")
        else:
            print(f"  - Source '{s['name']}' is local folder; nothing to pull.")

    all_skills = get_all_available_skills(config)
    print(f"\n[+] Up-to-date! Total available skills across sources: {len(all_skills)}\n")


def cmd_info(args, config):
    identifier = args.skill.strip()
    skill_dir = resolve_skill_source(identifier, config)
    if not skill_dir or not (skill_dir / "SKILL.md").exists():
        print(f"[-] Skill '{identifier}' not found.", file=sys.stderr)
        return

    fm = parse_skill_frontmatter(skill_dir / "SKILL.md")
    print(f"\nSkill Information: {fm['name']}")
    print("=" * (20 + len(fm["name"])))
    print(f"Path:        {skill_dir}")
    print(f"Frontmatter Name: {fm['name']}")
    aliases = [k for k, v in KNOWN_ALIASES.items() if v == fm["name"]]
    print(f"Aliases:     {', '.join(aliases) if aliases else 'None'}")
    print(f"Prompt Cost: ~{estimate_tokens(fm['name'] + fm['description'])} tokens")
    print(f"\nDescription:\n{fm['description']}\n")

    subitems = [p.name for p in skill_dir.iterdir() if p.name != "SKILL.md"]
    if subitems:
        print(f"Bundled assets / scripts: {', '.join(subitems)}")

    global_target = GLOBAL_SKILLS_DIR / fm["name"]
    if global_target.exists():
        print(f"\nStatus: INSTALLED globally at {global_target}")
    else:
        print(f"\nStatus: NOT installed (available in source repo)")
    print()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Skill Manager: Discover, install, and manage skills while saving tokens."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("search", help="Search available skills by task or keyword")
    p_search.add_argument("query", nargs="+", help="Keywords or task description")

    subparsers.add_parser("list-all", help="List all skills available in sources")
    subparsers.add_parser("list-installed", help="List currently installed Antigravity skills and token stats")

    p_info = subparsers.add_parser("info", help="Show detailed information about a skill")
    p_info.add_argument("skill", help="Skill name or path")

    p_install = subparsers.add_parser("install", help="Install a skill to Antigravity")
    p_install.add_argument("skill", help="Skill name, local directory, or git repo URL")
    p_install.add_argument("--target", default="global", help="'global' (default), 'workspace', or explicit path")
    p_install.add_argument("--name", default=None, help="Override installed skill directory/name")
    p_install.add_argument("--force", action="store_true", help="Overwrite if already exists")

    p_uninstall = subparsers.add_parser("uninstall", help="Uninstall a skill from Antigravity")
    p_uninstall.add_argument("skill", help="Skill name to remove")
    p_uninstall.add_argument("--target", default="global", help="'global' (default), 'workspace', or explicit path")

    p_add_src = subparsers.add_parser("add-source", help="Register a new skill repository or folder")
    p_add_src.add_argument("name", help="Identifier name for this source")
    p_add_src.add_argument("path_or_url", help="Local folder path or git URL")
    p_add_src.add_argument("--description", default="", help="Description of this source")

    subparsers.add_parser("update-sources", help="Git pull all registered repository sources")

    args = parser.parse_args()
    config = load_config()

    dispatch = {
        "search": cmd_search,
        "list-all": cmd_list_all,
        "list-installed": cmd_list_installed,
        "info": cmd_info,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "add-source": cmd_add_source,
        "update-sources": cmd_update_sources,
    }
    dispatch[args.command](args, config)


if __name__ == "__main__":
    main()
