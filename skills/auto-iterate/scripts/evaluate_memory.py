#!/usr/bin/env python3
"""
evaluate_memory.py - Memory store evaluation for auto-iterate.
Dimensions: 检索命中率(50%) + 信噪比(30%) + 索引完整性(20%)
Total: max 10.0
Output: last line = "---SCORE:<float>---" for machine parsing.
"""
import subprocess
import sys
import os
from pathlib import Path

SKIP_NAMES = {
    "MEMORY.md", "WhoAmI.md", "trigger-map.md", "role.md", "INDEX.md"
}


def run_cli(store: str, *args: str) -> tuple[str, str, int]:
    """Run agent-memory CLI command, return (stdout, stderr, returncode)."""
    cli = os.path.expanduser(
        "~/.claude/skills/agent-memory/scripts/cli.py"
    )
    cmd = ["python3", cli, "--store", store] + list(args)
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False)
        return r.stdout, r.stderr, r.returncode
    except (subprocess.TimeoutExpired, OSError) as e:
        return "", str(e), 1


def get_memory_files(store: str) -> list[Path]:
    """Return non-system .md files in the given store directory."""
    p = Path(store)
    return [
        f for f in p.glob("*.md")
        if f.name not in SKIP_NAMES and not f.name.startswith(".")
    ]


def _parse_fm_lines(raw_block: str) -> dict:
    """Parse key:value pairs from a raw frontmatter block string.

    :param raw_block: the text between the two '---' delimiters
    """
    return {
        k.strip(): v.strip()
        for line in raw_block.strip().splitlines()
        if ":" in line
        for k, v in [line.split(":", 1)]
    }


def parse_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter from a markdown file, return dict or None."""
    content = filepath.read_text(errors="ignore")
    if not content.strip().startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    return _parse_fm_lines(parts[1])


def _collect_keywords(files: list[Path]) -> list[str]:
    """Collect and deduplicate keywords from memory file frontmatter.

    :param files: list of memory file paths to scan
    """
    all_keywords: list[str] = []
    for f in files:
        fm = parse_frontmatter(f)
        if fm and "keywords" in fm:
            kws = [
                k.strip().strip('"').strip("'")
                for k in fm["keywords"].split(",")
            ]
            all_keywords.extend(kws)
    return list(set(all_keywords))[:8]


def _count_hits(store: str, unique_kw: list[str]) -> int:
    """Count how many keyword queries return results.

    :param store: path to the memory store directory
    :param unique_kw: deduplicated keyword list to query
    """
    hits = 0
    for q in unique_kw:
        stdout, _, rc = run_cli(store, "retrieve", q, "--top-k", "3")
        if rc == 0 and stdout.strip() and "no results" not in stdout.lower():
            hits += 1
    return hits


def evaluate_retrieval(store: str) -> tuple[float, str]:
    """检索命中率 (50%, max 5.0)"""
    files = get_memory_files(store)
    if not files:
        return 0.0, "no memory files"

    unique_kw = _collect_keywords(files)
    if not unique_kw:
        return 2.5, "no keywords in frontmatter, partial credit"

    hits = _count_hits(store, unique_kw)
    score = (hits / len(unique_kw)) * 5.0
    return round(score, 2), f"{hits}/{len(unique_kw)} keyword queries hit"


def _snr_orphan_penalty(files: list[Path]) -> tuple[float, str]:
    """Compute penalty for orphan files (no valid frontmatter).

    :param files: list of memory file paths to check
    """
    orphans = [f.name for f in files if parse_frontmatter(f) is None]
    if not orphans:
        return 0.0, ""
    msg = f"{len(orphans)} orphan(s): {', '.join(orphans[:3])}"
    return len(orphans) * 0.3, msg


def _snr_clog_penalty(store: str) -> tuple[float, str]:
    """Compute penalty for corrupted log false alarms.

    :param store: path to the memory store directory
    """
    clog = Path(store) / ".corrupted_memories.log"
    if not clog.exists():
        return 0.0, ""
    lines = clog.read_text(errors="ignore").splitlines()
    false_alarms = sum(
        1 for line in lines if "missing frontmatter" in line.lower()
    )
    if false_alarms > 10:
        return 0.5, f"corrupted log: {false_alarms} false alarms"
    return 0.0, ""


def _snr_stale_penalty(store: str) -> tuple[float, str]:
    """Compute penalty for stale memories (never accessed, >3 days old).

    :param store: path to the memory store directory
    """
    stdout, _, rc = run_cli(
        store, "stale", "--min-days", "3", "--min-retrievals", "0"
    )
    if rc != 0:
        return 0.0, ""
    stale_count = sum(
        1 for line in stdout.splitlines() if line.strip() and ".md" in line
    )
    if stale_count > 0:
        return stale_count * 0.15, f"{stale_count} stale memories"
    return 0.0, ""


def _snr_dup_penalty(store: str) -> tuple[float, str]:
    """Compute penalty for potential duplicates via consolidate dry-run.

    :param store: path to the memory store directory
    """
    stdout, _, rc = run_cli(
        store, "consolidate", "--dry-run", "--threshold", "0.80"
    )
    if rc != 0:
        return 0.0, ""
    dup_lines = [
        line for line in stdout.splitlines()
        if "similar" in line.lower() or "duplicate" in line.lower()
    ]
    if dup_lines:
        return len(dup_lines) * 0.2, f"{len(dup_lines)} potential duplicates"
    return 0.0, ""


def evaluate_snr(store: str) -> tuple[float, str]:
    """信噪比 (30%, max 3.0)

    :param store: path to the memory store directory
    """
    files = get_memory_files(store)
    if not files:
        return 0.0, "no files"

    checks = [
        _snr_orphan_penalty(files),
        _snr_clog_penalty(store),
        _snr_stale_penalty(store),
        _snr_dup_penalty(store),
    ]
    penalties = sum(p for p, _ in checks)
    details = [d for _, d in checks if d]

    score = max(0.0, 3.0 - penalties)
    return round(score, 2), "; ".join(details) if details else "clean"


def evaluate_index(store: str) -> tuple[float, str]:
    """索引完整性 (20%, max 2.0)"""
    files = get_memory_files(store)
    fnames = [f.name for f in files]
    idx_path = Path(store) / "MEMORY.md"

    if not idx_path.exists():
        return 0.0, "no MEMORY.md"

    idx_content = idx_path.read_text(errors="ignore")

    if not fnames:
        return 2.0 if idx_path.exists() else 0.0, "no files to index"

    indexed = sum(1 for fn in fnames if fn in idx_content)
    missing = [fn for fn in fnames if fn not in idx_content]

    score = (indexed / len(fnames)) * 2.0
    detail = f"{indexed}/{len(fnames)} indexed"
    if missing:
        detail += f"; missing: {', '.join(missing[:3])}"
    return round(score, 2), detail


def main() -> None:
    """Entry point: evaluate memory store quality."""
    if len(sys.argv) < 2:
        print("Usage: evaluate_memory.py <store_path> [--agent <name>]")
        sys.exit(1)

    store = os.path.expanduser(sys.argv[1])
    agent = "unknown"
    if "--agent" in sys.argv:
        idx = sys.argv.index("--agent")
        if idx + 1 < len(sys.argv):
            agent = sys.argv[idx + 1]

    print(f"=== Memory Evaluation: {agent} ===")
    print(f"Store: {store}")
    print()

    r_score, r_detail = evaluate_retrieval(store)
    s_score, s_detail = evaluate_snr(store)
    i_score, i_detail = evaluate_index(store)
    total = round(r_score + s_score + i_score, 2)

    print(f"检索命中率 (50%): {r_score:.2f}/5.00 — {r_detail}")
    print(f"信噪比    (30%): {s_score:.2f}/3.00 — {s_detail}")
    print(f"索引完整性 (20%): {i_score:.2f}/2.00 — {i_detail}")
    print(f"\n总分: {total:.2f}/10.00")
    print(f"\n---SCORE:{total:.2f}---")


if __name__ == "__main__":
    main()
