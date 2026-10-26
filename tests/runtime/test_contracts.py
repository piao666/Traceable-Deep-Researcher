"""The runtime contract stays usable without provider or backend dependencies."""

import asyncio
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def contracts():
    return importlib.import_module("traceable_deep_researcher.runtime.contracts")


def test_result_defaults_are_independent_and_json_serializable():
    module = contracts()
    first = module.ResearchResult(report_markdown="first")
    second = module.ResearchResult(report_markdown="second")
    for name, value in (("sources", {}), ("context_refs", "ctx"),
                        ("warnings", "warning"), ("artifact_refs", "artifact")):
        getattr(first, name).append(value)
        assert getattr(second, name) == []
    first.cost_summary["total_usd"] = 0.0
    assert second.cost_summary == {}
    assert second.review_status == "not_requested"
    assert json.loads(json.dumps(asdict(first)))["report_markdown"] == "first"


def test_child_context_keeps_injected_dependencies_and_parent_lineage():
    module = contracts()
    dependencies = dict(event_sink=object(), checkpoint_store=object(), review_inbox=object())
    parent = module.RunContext(research_id="r1", attempt_id="a1", **dependencies)
    child = parent.child()
    sibling = parent.child()
    assert child.research_id == parent.research_id
    assert child.attempt_id == parent.attempt_id
    assert child.parent_span_id == parent.span_id
    assert len({parent.span_id, child.span_id, sibling.span_id}) == 3
    assert child.child().parent_span_id == child.span_id
    for key, dependency in dependencies.items():
        assert getattr(child, key) is dependency


def test_async_protocols_accept_in_memory_implementations():
    module = contracts()

    class Sink:
        def __init__(self):
            self.events = []

        async def emit(self, event):
            self.events.append(event)

    class Store:
        def __init__(self):
            self.values = {}

        async def load(self, context, key):
            return self.values.get((context.research_id, context.attempt_id, key))

        async def save(self, context, key, checkpoint):
            self.values[(context.research_id, context.attempt_id, key)] = checkpoint

    class Inbox:
        def __init__(self):
            self.requests = {}

        async def request(self, review):
            self.requests[review.review_id] = review

        async def response(self, review_id):
            return module.ReviewResponse(review_id=review_id, decision="approve")

    async def exercise():
        sink, store, inbox = Sink(), Store(), Inbox()
        assert isinstance(sink, module.EventSink)
        assert isinstance(store, module.CheckpointStore)
        assert isinstance(inbox, module.ReviewInbox)
        context = module.RunContext("r1", "a1", event_sink=sink,
                                    checkpoint_store=store, review_inbox=inbox)
        await context.event_sink.emit({"type": "research.started"})
        assert sink.events == [{"type": "research.started"}]
        assert await store.load(context, "plan") is None
        await store.save(context, "plan", {"step": 1})
        assert await store.load(context, "plan") == {"step": 1}
        review = module.ReviewRequest(review_id="rev1", research_id="r1",
                                      attempt_id="a1", prompt="Approve plan?")
        await inbox.request(review)
        assert inbox.requests["rev1"] is review
        response = await inbox.response("rev1")
        assert response.decision == "approve"
        assert response.comment == ""

    asyncio.run(exercise())


def test_contract_imports_do_not_load_providers_and_public_export_stays_lazy():
    script = '''
import importlib.abc
import sys
class BlockProviders(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("langchain", "langgraph", "litellm", "openai", "fastapi")) or fullname == "traceable_deep_researcher.agent":
            raise AssertionError("heavy import: " + fullname)
sys.meta_path.insert(0, BlockProviders())
import traceable_deep_researcher
from traceable_deep_researcher.runtime import RunContext, ResearchResult
from backend.server.tasks.models import ResearchTaskRequest
assert traceable_deep_researcher.__all__ == ["TraceableDeepResearcher"]
assert "traceable_deep_researcher.agent" not in sys.modules
try:
    traceable_deep_researcher.missing_attribute
except AttributeError:
    pass
else:
    raise AssertionError("unknown package attribute accepted")
'''
    process = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                             capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def test_public_class_export_resolves_and_caches_the_existing_agent_class():
    script = '''
import sys
import types
import traceable_deep_researcher
agent = types.ModuleType("traceable_deep_researcher.agent")
class ExistingAgent:
    pass
agent.TraceableDeepResearcher = ExistingAgent
sys.modules[agent.__name__] = agent
from traceable_deep_researcher import TraceableDeepResearcher
assert TraceableDeepResearcher is ExistingAgent
assert traceable_deep_researcher.TraceableDeepResearcher is ExistingAgent
'''
    process = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                             capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
