# Antigravity Skill Manager

A lightweight, zero-dependency Python CLI to discover, search, install, and manage
[Antigravity](https://antigravity.google) skills from external repositories
(such as [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official))
on demand — without bloating your system prompt.

---

## Why On-Demand Skill Management?

In Antigravity, skills use **progressive disclosure**:

- Every installed skill's `name` and `description` are injected into the agent's system prompt on **every interaction** (~50–120 tokens each).
- The full `SKILL.md` body and bundled scripts are only loaded when a skill is actually triggered.
- Installing dozens of skills at once silently drains thousands of tokens per turn and can cause trigger conflicts.

**The solution:** keep skill repositories cloned locally and install/uninstall skills on demand using this tool or the companion [`skill-hub`](https://github.com/davtoh/antigravity-skills) Antigravity skill.

---

## Installation

### Option A — pip (recommended, adds `skill-manager` to PATH)

```bash
pip install git+https://github.com/davtoh/antigravity-skill-manager
```

### Option B — clone and run directly

```bash
# Clone to any folder you like, e.g. ~/src/skill-manager
git clone https://github.com/davtoh/antigravity-skill-manager ~/src/skill-manager
python ~/src/skill-manager/skill_manager.py --help
```

### Option C — add the clone to PATH (Windows CMD/PowerShell)

```powershell
# Add to your User PATH permanently (run once)
$p = [Environment]::GetEnvironmentVariable("Path","User")
[Environment]::SetEnvironmentVariable("Path","$p;$HOME\src\skill-manager","User")
```

---

## Directory Layout

```
~/src/
├── skill-manager/               # This repo
│   ├── skill_manager.py         # Main script (zero dependencies beyond stdlib)
│   ├── skill-manager.cmd        # Windows CMD shim (optional)
│   ├── skill-manager.ps1        # Windows PowerShell shim (optional)
│   ├── config.example.json      # Example config (real config is machine-local, not tracked)
│   └── README.md
├── claude-plugins-official/     # Example: cloned skill repository
└── my-custom-skills/            # Example: any other local skill folder
```

> **Config and state files** (`config.json`, `installed.json`) are stored in your platform's
> standard config directory and are **never committed to git** — they contain machine-local paths.
>
> | Platform | Config location |
> |---|---|
> | Windows | `%APPDATA%\skill-manager\` |
> | macOS / Linux | `$XDG_CONFIG_HOME/skill-manager/` or `~/.config/skill-manager/` |

Installed Antigravity skills live at:

- **Global:** `~/.gemini/config/skills/<skill-name>/`
- **Workspace-local:** `<project-root>/.agents/skills/<skill-name>/`

---

## Usage

All examples use `skill-manager` (available after pip install or adding the clone to PATH).
You can also substitute `python skill_manager.py` if running from the cloned directory.

### First-time setup — register a skill source

```bash
skill-manager add-source claude-plugins-official \
  https://github.com/anthropics/claude-plugins-official.git
```

### Search for skills by task or keyword

```bash
skill-manager search "create skill"
skill-manager search "security audit"
skill-manager search "ui design"
```

### List all available skills across sources

```bash
skill-manager list-all
```

### View skill details and estimated token cost

```bash
skill-manager info skill-creator
```

### Install a skill

```bash
# By name (supports aliases, e.g. create-skill → skill-creator)
skill-manager install skill-creator

# Install to current workspace only instead of globally
skill-manager install skill-creator --target workspace

# Install from a local directory
skill-manager install ~/path/to/custom-skill

# Install directly from a Git URL
skill-manager install https://github.com/example/my-skill-repo.git

# Overwrite an already-installed skill
skill-manager install skill-creator --force
```

### Check installed skills and their system-prompt token footprint

```bash
skill-manager list-installed
```

### Uninstall a skill (reclaim prompt tokens)

```bash
skill-manager uninstall skill-creator
```

### Sync and update all registered sources

```bash
skill-manager update-sources
```

### Register a new repository or local folder

```bash
skill-manager add-source my-repo https://github.com/example/skills.git
skill-manager add-source local-skills ~/path/to/local-skill-folder
```

---

## Environment Variable Overrides

| Variable | Default | Description |
|---|---|---|
| `SKILL_SOURCES_DIR` | `~/src` | Where external repos are cloned |
| `SKILL_MANAGER_DIR` | Platform config dir | Where `config.json` and `installed.json` are stored |
| `ANTIGRAVITY_SKILLS_DIR` | `~/.gemini/config/skills` | Antigravity global skills directory |

---

## Companion Skill — `skill-hub`

Once you have your Antigravity skills repo set up, install the companion
[`skill-hub`](https://github.com/davtoh/antigravity-skills) skill globally.
It teaches Antigravity to use `skill-manager` directly from chat:

- *"Is there a skill for reviewing pull requests?"*
- *"Install the session-report skill."*
- *"What skills do I have installed and how many tokens do they use?"*
- *"Uninstall skill-creator to save tokens."*
- *"Update skill sources from GitHub."*

---

## Related Repositories

| Repo | Purpose |
|---|---|
| [davtoh/antigravity-skill-manager](https://github.com/davtoh/antigravity-skill-manager) | This tool |
| [davtoh/antigravity-skills](https://github.com/davtoh/antigravity-skills) | Personal global skills collection (includes `skill-hub`) |
| [davtoh/antigravity-rules](https://github.com/davtoh/antigravity-rules) | Personal global rules (security standards, etc.) |
| [davtoh/git-history-purger](https://github.com/davtoh/git-history-purger) | Example of a skill bundled inside its own tool repo |
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | Upstream community skill and plugin catalog |
