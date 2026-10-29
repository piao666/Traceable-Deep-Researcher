"""Offline report API fixture: real HTTP/storage, isolated research providers."""

import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

@pytest.fixture
def report_app(tmp_path, monkeypatch):
    from backend.server.storage.database import Database
    root = Path(__file__).resolve().parents[2]
    url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    monkeypatch.setenv("TDR_DATABASE_URL", url)
    monkeypatch.setenv("REPORT_STORE_PATH", str(tmp_path / "reports.json"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(root / "backend"))
    # These imports belong to research/export/chat, not the report repository.
    # Unexpected use raises; the chat test supplies its own deterministic reply.
    def unavailable(*args, **kwargs):
        raise AssertionError("Real research/export providers must not run in report API tests")
    websocket = types.ModuleType("server.websocket_manager")
    websocket.WebSocketManager = type("WebSocketManager", (), {})
    websocket.run_agent = unavailable
    utilities = types.ModuleType("server.server_utils")
    for name in ["get_config_dict", "sanitize_filename", "update_environment_variables", "handle_file_upload",
                 "handle_file_deletion", "execute_multi_agents", "handle_websocket_communication"]:
        setattr(utilities, name, unavailable)
    exports = types.ModuleType("utils")
    exports.write_md_to_word = exports.write_md_to_pdf = unavailable
    chat = types.ModuleType("chat.chat")
    class FakeChat:
        def __init__(self, **kwargs):
            self.chat = AsyncMock(return_value=("离线回复", None))
    chat.ChatAgentWithMemory = FakeChat
    for name, module in [("server.websocket_manager", websocket), ("server.server_utils", utilities),
                         ("utils", exports), ("chat.chat", chat)]:
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("tdr_report_api_under_test", root / "backend/server/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = Database(url)
    db.migrate()
    yield module
    db.dispose()
