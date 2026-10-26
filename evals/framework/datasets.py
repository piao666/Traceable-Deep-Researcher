"""Load pinned local datasets and reject broken provenance before replay."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .manifest import content_hash
from .models import AgentCase, TaskCase
from .replay import ToolReplay


@dataclass
class Dataset:
    root: Path
    manifest: dict
    tasks: list[TaskCase]
    agents: list[AgentCase]
    sources: dict
    replays: dict
    dataset_hash: str
    source_hash: str


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _keys(value, required, label):
    _require(isinstance(value, dict) and set(value) == set(required), f"invalid {label} schema")


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _unique(items, label):
    _require(len(items) == len(set(items)), f"duplicate {label}")


def _read_json(path):
    def pairs(items):
        _unique([key for key, _ in items], "JSON key")
        return dict(items)

    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)


def _confined(root, relative):
    _require(_string(relative), "invalid dataset path")
    candidate = Path(relative)
    _require(not candidate.is_absolute() and not PureWindowsPath(relative).drive,
             "absolute dataset path is forbidden")
    target = (root / candidate).resolve()
    _require(target.is_relative_to(root), f"dataset path escapes root: {relative}")
    _require(target.is_file(), f"dataset path does not exist: {relative}")
    return target


def _load_cases(path, model):
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        _require(bool(line.strip()), f"blank case at line {number}")
        # Reuse duplicate-key and non-finite JSON checks for JSONL rows.
        def pairs(items):
            _unique([key for key, _ in items], "JSON key")
            return dict(items)
        value = json.loads(line, object_pairs_hook=pairs)
        content_hash(value)
        _require(isinstance(value, dict) and type(value.get("schema_version")) is int
                 and value["schema_version"] == 1, "unsupported case schema version")
        rows.append(model.model_validate(value))
    _require(bool(rows), "empty case file")
    return rows


def _validate_sources(sources):
    _require(isinstance(sources, dict) and bool(sources), "invalid sources schema")
    source_ids, evidence_ids = [], []
    for bundle_id, bundle in sources.items():
        _require(_string(bundle_id), "invalid source bundle ID")
        _keys(bundle, {"documents", "evidence"}, "source bundle")
        _require(isinstance(bundle["documents"], list) and isinstance(bundle["evidence"], list),
                 "invalid source bundle collections")
        documents = {}
        for document in bundle["documents"]:
            _keys(document, {"source_id", "url", "title", "text", "sha256"}, "source document")
            _require(all(_string(document[key]) for key in ("source_id", "url", "title")),
                     "invalid source document strings")
            _require(isinstance(document["text"], str), "invalid source text")
            _require(document["sha256"] == hashlib.sha256(document["text"].encode("utf-8")).hexdigest(),
                     "source text hash mismatch")
            source_ids.append(document["source_id"])
            documents[document["source_id"]] = document
        for evidence in bundle["evidence"]:
            _keys(evidence, {"evidence_id", "source_id", "start", "end", "quote"}, "evidence")
            _require(_string(evidence["evidence_id"]) and _string(evidence["source_id"]), "invalid evidence ID")
            _require(evidence["source_id"] in documents, "missing evidence source reference")
            text = documents[evidence["source_id"]]["text"]
            start, end = evidence["start"], evidence["end"]
            _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text),
                     "invalid evidence coordinates")
            _require(isinstance(evidence["quote"], str) and text[start:end] == evidence["quote"],
                     "evidence quote does not match coordinates")
            evidence_ids.append(evidence["evidence_id"])
    _unique(source_ids, "source ID")
    _unique(evidence_ids, "evidence ID")


def _validate_cases(tasks, agents, manifest, sources):
    cases = tasks + agents
    _unique([case.case_id for case in cases], "case ID")
    splits = {}
    for case in cases:
        _require(case.dataset_version == manifest["dataset_version"], "case dataset version mismatch")
        _require(case.source_bundle in sources, "missing source bundle reference")
        previous = splits.setdefault(case.group_id, case.split)
        _require(previous == case.split, "group split leakage")
        refs = case.gold_evidence if isinstance(case, TaskCase) else case.gold_output_refs
        evidence = {item["evidence_id"] for item in sources[case.source_bundle]["evidence"]}
        _require(all(ref in evidence for ref in refs), "gold evidence reference outside source bundle")
        if isinstance(case, TaskCase):
            _unique([item.id for item in case.requirements], "requirement ID")
            _unique([item.id for item in case.gold_facts], "gold fact ID")


def _identity(record):
    _require(all(_string(record[key]) for key in ("tool_name", "context", "fixture_key")),
             "invalid fixture identity")
    _require(isinstance(record["arguments"], dict), "invalid fixture arguments")
    return ToolReplay._key(record["tool_name"], record["arguments"], record["context"], record["fixture_key"])


def _validate_output(case, result, bundle):
    _require(isinstance(result, dict), "invalid output fixture result")
    if isinstance(case, TaskCase):
        _keys(result, {"report", "sources"}, "task output fixture")
        _require(isinstance(result["report"], str), "invalid output fixture report type")
        urls = {document["url"] for document in bundle["documents"]}
        _require(isinstance(result["sources"], list) and all(_string(url) and url in urls for url in result["sources"]),
                 "invalid output fixture sources")
    else:
        required = case.expected_constraints.get("required_keys", [])
        equals = case.expected_constraints.get("equals", {})
        _require(set(case.expected_constraints) <= {"required_keys", "equals"}, "unknown node constraint")
        _require(isinstance(required, list) and all(_string(key) for key in required), "invalid required_keys constraint")
        _require(isinstance(equals, dict), "invalid equals constraint")
        # A well-formed candidate may be wrong. The runner, not provenance
        # validation, judges whether its output meets these constraints.


def _validate_replays(replays, tasks, agents, sources):
    _keys(replays, {"tools", "task", "agent"}, "replays")
    _require(isinstance(replays["tools"], list), "invalid tools fixtures")
    fixtures = {}
    for record in replays["tools"]:
        _keys(record, {"tool_name", "arguments", "context", "fixture_key", "result", "max_calls"}, "tool fixture")
        _require(type(record["max_calls"]) is int and record["max_calls"] > 0, "invalid fixture max_calls")
        content_hash(record["result"])
        key = _identity(record)
        _require(key not in fixtures, "duplicate fixture identity")
        fixtures[key] = record
    used = Counter()
    for suite, cases in (("task", tasks), ("agent", agents)):
        _require(isinstance(replays[suite], dict), "invalid replay suite")
        _unique([case.replay_key for case in cases], f"{suite} replay key")
        _require(set(replays[suite]) == {case.replay_key for case in cases}, "missing or orphan replay key")
        for case in cases:
            entry = replays[suite][case.replay_key]
            _keys(entry, {"calls"}, "replay entry")
            _require(isinstance(entry["calls"], list), "invalid replay calls")
            _require(len(entry["calls"]) + 1 <= case.budget.max_tool_calls, "replay exceeds tool call budget")
            results = []
            for call in entry["calls"]:
                _keys(call, {"tool_name", "arguments", "context", "fixture_key"}, "replay call")
                _require(call["context"] == case.case_id, "replay call context differs from case")
                _require(call["tool_name"] not in {"fixture.model", "fixture.node"}, "reserved output fixture tool")
                if isinstance(case, AgentCase):
                    _require(call["tool_name"] in case.allowed_tools, "replay call tool is not allowed")
                key = _identity(call)
                _require(key in fixtures, "missing tool fixture")
                used[key] += 1
                results.append(fixtures[key]["result"])
            output = {"tool_name": "fixture.model" if suite == "task" else "fixture.node",
                      "arguments": {"input": case.agent_input(), "tool_results": results},
                      "context": case.case_id, "fixture_key": "output"}
            key = _identity(output)
            _require(key in fixtures, "missing output fixture or input projection mismatch")
            used[key] += 1
            _validate_output(case, fixtures[key]["result"], sources[case.source_bundle])
    _require(set(used) == set(fixtures), "orphan tool fixture")
    _require(all(count <= fixtures[key]["max_calls"] for key, count in used.items()),
             "replay exceeds fixture max_calls")


def load_dataset(manifest_path: Path) -> Dataset:
    """Validate byte pins, schemas, provenance, split isolation and exact replay keys."""
    try:
        manifest_path = Path(manifest_path).resolve()
        root = manifest_path.parent
        manifest = _read_json(manifest_path)
        _keys(manifest, {"schema_version", "dataset_version", "task_cases", "agent_cases", "sources", "replays", "files"}, "manifest")
        _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "unsupported manifest schema version")
        _require(manifest["dataset_version"] == "1", "unsupported dataset version")
        _require(isinstance(manifest["files"], dict), "invalid manifest files")
        references = [manifest[key] for key in ("task_cases", "agent_cases", "sources", "replays")]
        _require(all(_string(path) for path in references), "invalid manifest path")
        _unique(references, "manifest path")
        _require(set(references) == set(manifest["files"]), "missing or extra file hash pins")
        paths = {}
        for relative, expected in manifest["files"].items():
            path = _confined(root, relative)
            _require(expected == hashlib.sha256(path.read_bytes()).hexdigest(), f"dataset file hash mismatch: {relative}")
            paths[relative] = path
        tasks = _load_cases(paths[manifest["task_cases"]], TaskCase)
        agents = _load_cases(paths[manifest["agent_cases"]], AgentCase)
        sources = _read_json(paths[manifest["sources"]])
        replays = _read_json(paths[manifest["replays"]])
        _validate_sources(sources)
        _validate_cases(tasks, agents, manifest, sources)
        _validate_replays(replays, tasks, agents, sources)
        return Dataset(root, manifest, tasks, agents, sources, replays, content_hash(manifest), content_hash(sources))
    except (OSError, TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"invalid dataset: {error}") from error
