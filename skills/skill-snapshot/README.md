# Skill Snapshot

[中文文档](README_CN.md)

A Claude Code skill for creating snapshots of your skills with version control. Store backups in a private GitHub repository and restore any version when needed.

## Features

- **Snapshot Management**: Save, restore, list, and diff skill versions
- **Private GitHub Storage**: Automatically creates and syncs to a private repository
- **Smart Scanning**: Automatically identifies which skills need backup
- **Version Tags**: Each snapshot is tagged (e.g., `my-skill/v1`, `my-skill/v2`)

## Installation

Copy the `skill-snapshot` folder to your Claude Code skills directory:

```bash
cp -r skill-snapshot ~/.claude/skills/
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize private GitHub repository |
| `scan` | Scan skills and identify which need backup |
| `save <skill> [message]` | Save a snapshot |
| `restore <skill> [version]` | Restore to a specific version |
| `list [skill]` | List all snapshots |
| `diff <skill> [version]` | Compare current with a snapshot |

## Usage Examples

### First-time Setup

```
User: Initialize skill snapshots
Claude: [Executes init - creates private repo]
```

### Save Before Modifying

```
User: Save my-skill snapshot before I modify it
Claude: [Executes save my-skill "pre-modification backup"]
Output: Saved snapshot my-skill/v1
```

### Restore When Things Break

```
User: my-skill is broken, restore to v1
Claude: [Executes restore my-skill v1]
Output: Restored to my-skill/v1
```

### Scan for Backup Candidates

```
User: Which skills need backup?
Claude: [Executes scan]
Output:
  [Needs Backup]
    ✓ my-skill (5 files, 68K) [Has: my-skill/v1]
    ○ new-skill (3 files, 12K) [Not backed up]

  [Skipped]
    ✗ external-plugin - Symlink (externally installed)
    ✗ git-managed-skill - Has its own Git version control
```

## Skip Rules

The `scan` command automatically skips:

| Rule | Reason |
|------|--------|
| `archive/` directory | Archived skills |
| Symlinks | Externally installed skills |
| `skill-snapshot` itself | The snapshot tool itself |
| Contains `.git/` | Has its own version control |
| Contains `.venv/` or `node_modules/` | Contains large dependencies |
| Size > 10MB | Too large |
| Missing `SKILL.md` | Not a valid skill |

## Requirements

- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- Git installed
- macOS or Linux (uses bash scripts)

## Storage Structure

```
~/.claude/skill-snapshots/          # Local repository
├── my-skill/
│   ├── SKILL.md
│   └── scripts/
├── another-skill/
│   └── SKILL.md
└── README.md

GitHub Tags:
├── my-skill/v1
├── my-skill/v2
└── another-skill/v1
```

## License

MIT License - see [LICENSE](LICENSE)
