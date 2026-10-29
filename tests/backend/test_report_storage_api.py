import json

from fastapi.testclient import TestClient


def test_report_crud_pagination_and_chat_use_real_database(report_app):
    with TestClient(report_app.app) as client:
        for i in range(3):
            assert client.post("/api/reports", json={"id": str(i), "answer": f"正文{i}", "timestamp": i}).status_code == 200
        page = client.get("/api/reports", params={"limit": 1, "offset": 1}).json()
        assert [r["id"] for r in page["reports"]] == ["1"]
        assert client.get("/api/reports", params={"limit": 0}).status_code == 422
        assert client.put("/api/reports/1", json={"question": "新问题"}).status_code == 200
        reply = client.post("/api/reports/1/chat", json={"role": "user", "content": "追问"})
        assert reply.status_code == 200 and reply.json()["response"]["content"] == "离线回复"
        saved = client.get("/api/reports/1").json()["report"]
        assert saved["question"] == "新问题" and saved["answer"] == "正文1"
        assert [m["role"] for m in saved["chatMessages"]] == ["user", "assistant"]
        assert client.delete("/api/reports/1").status_code == 200
        assert client.get("/api/reports/1").status_code == 404
        assert client.put("/api/reports/missing", json={"answer": "x"}).status_code == 404
        assert client.post("/api/reports", json=[]).status_code == 422
        assert client.put("/api/reports/0", json={"chatMessages": {}}).status_code == 422


def test_startup_refuses_legacy_file_that_was_not_imported(report_app, monkeypatch):
    import pytest
    from pathlib import Path
    Path(report_app.report_store.legacy_path).write_text(json.dumps({"old": {"id": "old"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unmigrated"):
        with TestClient(report_app.app):
            pass


def test_report_survives_new_store_instance(report_app):
    with TestClient(report_app.app) as client:
        client.post("/api/reports", json={"id": "persist", "answer": "持久"}).raise_for_status()
    with TestClient(report_app.app) as client:
        assert client.get("/api/reports/persist").json()["report"]["answer"] == "持久"


def test_reply_to_old_version_cannot_be_attached_to_new_report(report_app, monkeypatch):
    class ChatThatRacesWithEdit:
        def __init__(self, **kwargs):
            pass
        async def chat(self, messages, websocket):
            await report_app.report_store.patch_report("r", {"answer": "新版"}, timestamp=20)
            return "针对旧正文的回复", None
    monkeypatch.setattr(report_app, "ChatAgentWithMemory", ChatThatRacesWithEdit)
    with TestClient(report_app.app) as client:
        client.post("/api/reports", json={"id": "r", "answer": "旧正文"}).raise_for_status()
        reply = client.post("/api/reports/r/chat", json={"role": "user", "content": "追问"})
        assert reply.status_code == 409
        saved = client.get("/api/reports/r").json()["report"]
        assert saved["answer"] == "新版" and saved["chatMessages"] == []
