"""Verify Docker client failure cannot strand untracked validation resources."""

import json
import subprocess

import pytest

from scripts import verify_a1_container as smoke_module


def test_helper_timeout_still_removes_daemon_container(monkeypatch):
    smoke = smoke_module.Smoke("test-image")
    running = {}

    def docker(*args, **kwargs):
        if args[0] == "run":
            name = args[args.index("--name") + 1] if "--name" in args else "anonymous-helper"
            running[name] = True
            # Killing this client does not stop the daemon-side container.
            raise subprocess.TimeoutExpired("docker", 1)
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, json.dumps([
                {"Config": {"Labels": {"tdr.validation.run": smoke.prefix}}}]), "")
        if args[0] == "rm":
            running.pop(args[-1])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(smoke_module, "docker", docker)
    with pytest.raises(subprocess.TimeoutExpired):
        smoke.helper("example-data", "python", "-c", "import time; time.sleep(20)")
    assert smoke.cleanup() == []
    assert running == {}


def test_cleanup_refuses_resource_owned_by_another_run(monkeypatch):
    smoke = smoke_module.Smoke("test-image")
    smoke.containers.add("foreign-container")
    removed = []

    def docker(*args, **kwargs):
        if args[0] == "inspect":
            return subprocess.CompletedProcess(args, 0, json.dumps([
                {"Config": {"Labels": {"tdr.validation.run": "another-run"}}}]), "")
        if args[0] == "rm":
            removed.append(args[-1])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(smoke_module, "docker", docker)
    assert smoke.cleanup()
    assert removed == []
