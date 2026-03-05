#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


FILES = {
    ".gitignore": ".DS_Store\n__pycache__/\n.pytest_cache/\n",
    "pyproject.toml": (
        "[project]\n"
        'name = "flow-healer-demo"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.11"\n\n'
        "[build-system]\n"
        'requires = ["setuptools>=61"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
    ),
    "demo_math.py": "def add(a: int, b: int) -> int:\n    return a - b\n",
    "tests/conftest.py": (
        "from pathlib import Path\n"
        "import sys\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n"
    ),
    "tests/test_demo_math.py": (
        "from demo_math import add\n\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    ),
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bootstrap_demo_repo.py <target-dir>", file=sys.stderr)
        return 2

    target = Path(sys.argv[1]).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    for rel_path, content in FILES.items():
        path = target / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
