# Evaluation tools

These optional harnesses may call configured providers and are not part of Docker startup. Historical upstream results do not establish this branch's performance. Preserve individual third-party attributions.

M0 adds `python -m evals.run --suite task|agent --out <new-directory>` for
**offline engineering replay** of eight synthetic task fixtures and eight node
fixtures. It never runs a real researcher or judge. Online modes are rejected;
existing `quality_eval`, `simple_evals`, `hallucination_eval` and `context_filter`
commands retain their own provider requirements and may incur charges even when
some scoring metrics are disabled. See [usage and scope](../docs/evaluation.md).
