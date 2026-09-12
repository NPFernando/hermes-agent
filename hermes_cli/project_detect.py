"""Project auto-detection for Hermes CLI.

Detects project type from common config files and returns context
that can be used to auto-install skills or show relevant tips.
"""

import os
import json
from pathlib import Path


def detect_project(cwd: str | None = None) -> dict | None:
    """Detect project type from the working directory.

    Returns a dict with project info, or None if no project detected.
    """
    root = Path(cwd or os.getcwd())

    # Check for known project files
    checks = [
        ("package.json", _detect_node),
        ("pyproject.toml", _detect_python),
        ("setup.py", _detect_python),
        ("Cargo.toml", _detect_rust),
        ("go.mod", _detect_go),
        ("composer.json", _detect_php),
        ("Gemfile", _detect_ruby),
        ("mix.exs", _detect_elixir),
        ("pubspec.yaml", _detect_dart),
        ("CMakeLists.txt", _detect_cpp),
        ("Makefile", _detect_make),
        ("Dockerfile", _detect_docker),
        ("docker-compose.yml", _detect_docker),
        ("AGENTS.md", _detect_agents),
        ("CLAUDE.md", _detect_agents),
    ]

    for filename, detector in checks:
        path = root / filename
        if path.exists():
            result = detector(root, path)
            if result:
                return result

    return None


def _detect_node(root: Path, path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name", root.name)
        scripts = data.get("scripts", {})
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        framework = _detect_framework(deps)
        return {
            "type": "node",
            "name": name,
            "framework": framework,
            "scripts": list(scripts.keys())[:5],
            "test_cmd": _find_test_cmd(scripts, ["npm test", "npm run test", "npx jest", "npx vitest"]),
            "build_cmd": _find_script(scripts, ["build", "compile"]),
            "dev_cmd": _find_script(scripts, ["dev", "start", "serve"]),
            "lint_cmd": _find_script(scripts, ["lint", "check", "typecheck"]),
        }
    except Exception:
        return None


def _detect_python(root: Path, path: Path) -> dict | None:
    name = root.name
    test_cmd = None
    build_cmd = None
    lint_cmd = None
    framework = "python"

    # Check for common tools
    if (root / "pyproject.toml").exists():
        try:
            with open(root / "pyproject.toml", encoding="utf-8") as f:
                content = f.read()
            if "pytest" in content:
                test_cmd = "pytest"
            if "poetry" in content:
                build_cmd = "poetry build"
            if "ruff" in content:
                lint_cmd = "ruff check"
            elif "black" in content:
                lint_cmd = "black --check"
            if "django" in content.lower():
                framework = "django"
            elif "fastapi" in content.lower():
                framework = "fastapi"
            elif "flask" in content.lower():
                framework = "flask"
        except Exception:
            pass

    # Check for setup.py scripts
    if (root / "setup.py").exists():
        try:
            with open(root / "setup.py", encoding="utf-8") as f:
                content = f.read()
            if "pytest" in content:
                if not test_cmd:
                    test_cmd = "pytest"
        except Exception:
            pass

    if not test_cmd and (root / "tests").is_dir():
        test_cmd = "pytest tests/"

    return {
        "type": "python",
        "name": name,
        "framework": framework,
        "test_cmd": test_cmd or "pytest",
        "build_cmd": build_cmd,
        "lint_cmd": lint_cmd or (
            "ruff check"
            if (root / ".ruff.toml").exists() or (root / "ruff.toml").exists()
            else None
        ),
    }


def _detect_rust(root: Path, path: Path) -> dict | None:
    return {
        "type": "rust",
        "name": root.name,
        "test_cmd": "cargo test",
        "build_cmd": "cargo build",
        "lint_cmd": "cargo clippy",
        "dev_cmd": "cargo run",
    }


def _detect_go(root: Path, path: Path) -> dict | None:
    return {
        "type": "go",
        "name": root.name,
        "test_cmd": "go test ./...",
        "build_cmd": "go build ./...",
        "lint_cmd": "go vet ./...",
    }


def _detect_php(root: Path, path: Path) -> dict | None:
    return {
        "type": "php",
        "name": root.name,
        "test_cmd": "php vendor/bin/phpunit",
        "build_cmd": None,
        "lint_cmd": "php vendor/bin/phpcs",
    }


def _detect_ruby(root: Path, path: Path) -> dict | None:
    return {
        "type": "ruby",
        "name": root.name,
        "test_cmd": "bundle exec rspec",
        "build_cmd": None,
        "lint_cmd": "bundle exec rubocop",
    }


def _detect_elixir(root: Path, path: Path) -> dict | None:
    return {
        "type": "elixir",
        "name": root.name,
        "test_cmd": "mix test",
        "build_cmd": "mix compile",
    }


def _detect_dart(root: Path, path: Path) -> dict | None:
    return {
        "type": "dart",
        "name": root.name,
        "test_cmd": "flutter test" if (root / "pubspec.yaml").exists() and "flutter" in (root / "pubspec.yaml").read_text() else "dart test",
        "build_cmd": "flutter build" if (root / "pubspec.yaml").exists() and "flutter" in (root / "pubspec.yaml").read_text() else "dart compile",
    }


def _detect_cpp(root: Path, path: Path) -> dict | None:
    return {
        "type": "cpp",
        "name": root.name,
        "test_cmd": "ctest" if (root / "CTestConfig.cmake").exists() else None,
        "build_cmd": "cmake --build build",
    }


def _detect_make(root: Path, path: Path) -> dict | None:
    return {
        "type": "make",
        "name": root.name,
        "build_cmd": "make",
        "test_cmd": "make test" if _has_make_target(root, "test") else None,
    }


def _detect_docker(root: Path, path: Path) -> dict | None:
    return {
        "type": "docker",
        "name": root.name,
        "build_cmd": "docker compose build" if (root / "docker-compose.yml").exists() else "docker build -t .",
    }


def _detect_agents(root: Path, path: Path) -> dict | None:
    """Only detect AGENTS.md/CLAUDE.md when they're not in the home directory."""
    home = Path.home()
    if root == home or root.parent == home:
        return None
    return {
        "type": "agents",
        "name": root.name,
        "has_agents_md": (root / "AGENTS.md").exists(),
        "has_claude_md": (root / "CLAUDE.md").exists(),
    }


def _detect_framework(deps: dict) -> str | None:
    """Detect Node.js framework from dependencies."""
    frameworks = {
        "next": "next",
        "react": "react",
        "vue": "vue",
        "angular": "angular",
        "svelte": "svelte",
        "express": "express",
        "fastify": "fastify",
        "nuxt": "nuxt",
        "gatsby": "gatsby",
        "astro": "astro",
        "remix": "remix",
        "solid-js": "solid",
    }
    for key, name in frameworks.items():
        if key in deps or f"@{key}" in deps:
            return name
    return None


def _find_test_cmd(scripts: dict, candidates: list[str]) -> str | None:
    for c in candidates:
        parts = c.split()
        script_name = parts[-1] if parts and parts[0] in {"npm", "npx", "pnpm", "yarn"} else (parts[0] if parts else "")
        if script_name in scripts:
            return c
    return None


def _find_script(scripts: dict, names: list[str]) -> str | None:
    for name in names:
        if name in scripts:
            return f"npm run {name}"
    return None


def _has_make_target(root: Path, target: str) -> bool:
    makefile = root / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            return f"\n{target}:" in content or f"{target}:" in content.split("\n")[0]
        except Exception:
            pass
    return False


def format_project_summary(project: dict) -> str:
    """Format project info as a human-readable summary."""
    lines = [f"  📁 Project: {project['name']} ({project['type']})"]
    if project.get("framework"):
        lines.append(f"  🔧 Framework: {project['framework']}")
    if project.get("test_cmd"):
        lines.append(f"  🧪 Test: {project['test_cmd']}")
    if project.get("build_cmd"):
        lines.append(f"  🔨 Build: {project['build_cmd']}")
    if project.get("lint_cmd"):
        lines.append(f"  🔍 Lint: {project['lint_cmd']}")
    if project.get("dev_cmd"):
        lines.append(f"  ▶️  Dev: {project['dev_cmd']}")
    if project.get("scripts"):
        scmds = ", ".join(project["scripts"])
        lines.append(f"  📜 Scripts: {scmds}")
    return "\n".join(lines)
