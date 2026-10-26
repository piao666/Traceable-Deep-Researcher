# M0 engineering replay fixtures

Pinned JSON/JSONL files use UTF-8 with LF line endings, enforced by the root `.gitattributes`. Preserve LF when editing and recompute raw-byte pins after intentional content changes.

This version contains **8 task cases and 8 agent cases**, all in the development split, in Chinese and English. These are self-authored synthetic examples for validating dataset contracts, provenance coordinates, split isolation, deterministic replay, and output schemas. They are not a model-quality benchmark, an 80-task evaluation, human annotations, or measured research performance.

The task cases cover comparisons, repeated citations/source URLs, contradictory dated notices, as-of dates, absent evidence, empty search results, tool error payloads, and Unicode text. The eight agent cases cover planner, retriever, context selector, writer, reviewer, reviser, MCP selector, and orchestrator contracts. Empty-result and tool-error cases intentionally abstain. Tool errors here are replayed JSON payloads; they do not exercise real provider failures.

All names, measurements, notices, queries, reports, and labels were written for this repository. There is no external source content or human labeling claim. URLs under `fixtures.invalid` are identifiers and must never be fetched. Source documents are local UTF-8 JSON strings. Evidence offsets are half-open Python Unicode code-point coordinates into the exact `text`, not byte or UTF-16 offsets. Text SHA-256 values hash UTF-8 bytes.

`group_id` identifies a related task/agent pair. A group must never span development, calibration, or holdout splits; do not move an individual related case to another split. No calibration or holdout score is supported by this development-only fixture set.

`dataset_manifest.json` pins the raw bytes of both JSONL case files and both JSON source/replay files. The dataset hash is the canonical JSON hash of that manifest; the source hash is the canonical JSON hash of the source bundle object. Update the pins deliberately when editing data. The validator also rejects paths and symlinks that resolve outside this directory, duplicate identifiers, invalid evidence, broken references, and missing or orphan replay fixtures.

Replay calls match the canonical combination of tool name, argument object, case context, and fixture key. Final `fixture.model` or `fixture.node` arguments contain only `agent_input()` plus the preceding tool results. Evaluation labels, requirements, gold facts, and gold evidence are excluded from task model inputs; agent constraints and gold references are excluded from node inputs. Replay outputs are fixed engineering fixtures, not a live researcher or judge.

Validate offline from the repository root:

```powershell
$env:TDR_BLOCK_NETWORK = '1'
python scripts/validate_eval_dataset.py
python -m pytest tests/evals/test_dataset_validation.py
```
