"""把 _integration-check 的合并冲突解析结果合并到新工作树。

用法（在新合并工作树内运行）：
    python apply_merge_resolutions.py <解析来源目录> <目标目录>

规则：
- 目标文件若无冲突标记 → 跳过（自动合并或本侧独有）。
- 目标文件有冲突标记 → 优先使用来源目录里的同名已解析文件；
  来源缺失时按「两侧都保留」自动合并。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(
    r"<<<<<<< HEAD\r?\n(?P<head>.*?)=======\r?\n(?P<branch>.*?)>>>>>>> [^\n]*\r?\n",
    re.S,
)


def conflicted_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    target = Path.cwd()
    files = conflicted_files()
    print(f"conflicted files: {len(files)}")
    for name in files:
        target_file = target / name
        source_file = source / name
        text = target_file.read_text(encoding="utf-8")
        has_marker = "<<<<<<<" in text
        if not has_marker:
            print(f"skip (no markers): {name}")
            continue
        if source_file.exists() and "<<<<<<<" not in source_file.read_text(encoding="utf-8"):
            shutil.copyfile(source_file, target_file)
            print(f"copied resolved: {name}")
            continue
        resolved, count = MARKER.subn(lambda m: m.group("head") + m.group("branch"), text)
        target_file.write_text(resolved, encoding="utf-8", newline="")
        print(f"auto combined ({count}): {name}")
    remaining = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print("remaining conflicted:", remaining or "<none>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
