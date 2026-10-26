"""Reproducibility metadata containing hashes, never environment credentials."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE_DIRS = ("traceable_deep_researcher", "backend", "evals", "tests", "scripts", "docs", "frontend/nextjs/types")
ROOT_INPUTS = ("pyproject.toml", "frontend/nextjs/package.json", "frontend/nextjs/package-lock.json", "frontend/nextjs/tsconfig.json")


def content_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def source_fingerprint(root: Path) -> str:
    """Include newly created code, excluding generated data and dependency trees."""
    entries = {}
    for relative in ROOT_INPUTS:
        path = root / relative
        if path.is_file():
            entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    for directory in SOURCE_DIRS:
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root).as_posix()
            if (not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".json", ".jsonl", ".md"}
                    or relative.startswith("evals/results/")
                    or any(p in {"__pycache__", "node_modules", ".next", "runs", "results", "benchmark_results"} for p in path.parts)):
                continue
            entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return content_hash(entries)


def _git(root: Path, *args) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL,
                                       timeout=10).decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError):
        return None


def create_manifest(root: Path, *, dataset_hash: str, source_hash: str,
                    config: dict, prompt_inputs: dict, seed: int) -> dict:
    dependencies = {}
    for name in ("pydantic", "pytest"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    status = _git(root, "status", "--porcelain")
    fingerprint = source_fingerprint(root)
    diff = _git(root, "diff", "HEAD", "--", *SOURCE_DIRS, *ROOT_INPUTS)
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "code_commit": _git(root, "rev-parse", "HEAD"),
            "dirty": bool(status) if status is not None else None,
            "source_fingerprint": fingerprint,
            "dirty_diff_hash": content_hash({"tracked_diff": diff, "source_fingerprint": fingerprint}),
            "python": platform.python_version(), "dependencies": dependencies,
            "mode": "offline", "evaluation_kind": "engineering_replay",
            "providers": {"model": "fixture-v1", "judge": None},
            "dataset_hash": dataset_hash, "source_hash": source_hash,
            "config_hash": content_hash(config), "prompt_hash": content_hash(prompt_inputs),
            "seed": seed, "provider_calls": 0, "known_cost_usd": 0}
