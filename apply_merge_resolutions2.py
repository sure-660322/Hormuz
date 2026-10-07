"""在新合并工作树内解析冲突：按「main-only→取 main、其余→两侧都保留 + 定向修补」。

在 `git merge --no-commit` 产生冲突后运行：
    python apply_merge_resolutions2.py

步骤：
1. 对 main-only 变化的冲突文件取 main 版本（git checkout --ours）；
2. 其余冲突文件把两侧内容都保留（去掉冲突标记）；
3. 打印每个文件的冲突计数，便于人工复核。
"""
import re
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(
    r"<<<<<<< HEAD\r?\n(?P<head>.*?)=======\r?\n(?P<branch>.*?)>>>>>>> [^\n]*\r?\n",
    re.S,
)


def conflicted() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    files = conflicted()
    temporary = {"README.md", "backend/app/main.py"}
    print(f"conflicts: {len(files)}")
    for name in files:
        path = Path(name)
        if name in temporary:
            subprocess.run(["git", "checkout", "--ours", "--", name], check=True)
            subprocess.run(["git", "add", "--", name], check=True)
            print(f"took main version: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        resolved, count = MARKER.subn(lambda m: m.group("head") + m.group("branch"), text)
        path.write_text(resolved, encoding="utf-8", newline="")
        subprocess.run(["git", "add", "--", name], check=True)
        print(f"kept both sides ({count} conflict(s)): {name}")
    remaining = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print("remaining conflicted:", remaining or "<none>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
