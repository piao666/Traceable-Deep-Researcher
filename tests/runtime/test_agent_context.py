"""Constructor compatibility in isolation; this is not a provider integration test."""

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Optional


def isolated_agent_class():
    path = Path(__file__).parents[2] / "traceable_deep_researcher/agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    agent = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "TraceableDeepResearcher")
    agent.body = [item for item in agent.body if isinstance(item, ast.FunctionDef)
                  and item.name in {"__init__", "_resolve_mcp_strategy"}]
    from traceable_deep_researcher.utils.enum import ReportSource, ReportType, Tone

    class Config:
        prompt_family = "default"
        mcp_strategy = "fast"

        def __init__(self, path):
            pass

        def set_verbose(self, verbose):
            pass

    namespace = dict(ReportSource=ReportSource, ReportType=ReportType, Tone=Tone,
                     Optional=Optional, RunContext=object, Config=Config,
                     get_prompt_family=lambda *args: object(), get_retrievers=lambda *args: [],
                     **{name: (lambda *args: SimpleNamespace()) for name in (
                         "ResearchConductor", "ReportGenerator", "ContextManager", "BrowserManager",
                         "SourceCurator", "DeepResearchSkill", "ImageGenerator")})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[agent], type_ignores=[])), str(path), "exec"), namespace)
    return namespace["TraceableDeepResearcher"]


def test_optional_context_is_stored_without_leaking_to_llm_kwargs():
    agent_class = isolated_agent_class()
    context = object()
    researcher = agent_class("query", run_context=context, temperature=0.25)
    assert getattr(researcher, "run_context", None) is context
    assert researcher.kwargs == {"temperature": 0.25}


def test_legacy_constructor_still_works_and_context_is_explicit():
    import inspect
    agent_class = isolated_agent_class()
    researcher = agent_class("query")
    assert "run_context" in inspect.signature(agent_class).parameters
    assert researcher.run_context is None
