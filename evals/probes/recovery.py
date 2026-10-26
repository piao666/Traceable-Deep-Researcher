"""Minimal persistent checkpoint experiment, independent of production storage."""

import argparse
import importlib.metadata
import json
import sqlite3
from pathlib import Path
from typing import TypedDict

from evals.framework.network_guard import offline_network


def probe_sqlite(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE events (research_id TEXT, seq INTEGER, UNIQUE(research_id, seq))")
        connection.execute("INSERT INTO events VALUES (?, ?)", ("probe", 1))
    duplicate_rejected = False
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO events VALUES (?, ?)", ("probe", 2))
            connection.execute("INSERT INTO events VALUES (?, ?)", ("probe", 1))
    except sqlite3.IntegrityError:
        duplicate_rejected = True
    with sqlite3.connect(path) as connection:
        persisted = [row[0] for row in connection.execute("SELECT seq FROM events ORDER BY seq")]
    return {"persisted_seq": persisted, "duplicate_rejected": duplicate_rejected}


class ReviewState(TypedDict):
    draft: str
    decision: str


def probe_graph(path: Path, stage: str) -> dict:
    # Optional dependencies are confined to this experiment.
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    def review(state: ReviewState):
        return {"decision": interrupt({"draft": state["draft"]})}

    workflow = StateGraph(ReviewState)
    workflow.add_node("review", review)
    workflow.add_edge(START, "review")
    workflow.add_edge("review", END)
    config = {"configurable": {"thread_id": "m0-review-probe"}}
    with offline_network(), SqliteSaver.from_conn_string(str(path)) as saver:
        graph = workflow.compile(checkpointer=saver)
        if stage == "pause":
            output = graph.invoke({"draft": "Synthetic fixture draft"}, config)
            if not output.get("__interrupt__"):
                raise RuntimeError("graph did not persist an interrupt")
            result = {"status": "waiting_for_review"}
        else:
            if graph.get_state(config).next != ("review",):
                raise RuntimeError("persisted review checkpoint not found")
            output = graph.invoke(Command(resume="approve"), config)
            if output.get("decision") != "approve" or graph.get_state(config).next:
                raise RuntimeError("graph did not finish after resume")
            result = {"status": "resumed", "decision": output["decision"]}
    result["dependencies"] = {name: importlib.metadata.version(name)
                               for name in ("langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite")}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--stage", choices=("pause", "resume"), required=True)
    args = parser.parse_args()
    print(json.dumps(probe_graph(args.database, args.stage)))


if __name__ == "__main__":
    main()
