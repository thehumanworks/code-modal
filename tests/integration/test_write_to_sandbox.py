"""Integration tests for `write_to_sandbox` against Modal (creates real sandboxes)."""

import uuid

import modal
import pytest

from code_modal.sandbox import create_sandbox, terminate_sandboxes, write_to_sandbox

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_sandbox():
    created = create_sandbox(
        timeout=600,
        idle_timeout=120,
    )
    sandbox_id = created["sandbox_id"]
    try:
        yield sandbox_id
    finally:
        terminate_sandboxes([sandbox_id])


def _read_remote(sandbox_id: str, remote_path: str, *, as_text: bool) -> str | bytes:
    sandbox = modal.Sandbox.from_id(sandbox_id)
    if as_text:
        return sandbox.filesystem.read_text(remote_path)
    return sandbox.filesystem.read_bytes(remote_path)


def test_write_text_roundtrip(live_sandbox):
    path = f"/tmp/code_modal_write_test_{uuid.uuid4().hex}.txt"
    payload = "hello ütf-8\nline2"
    out = write_to_sandbox(live_sandbox, path, payload)
    assert out["is_error"] is False
    assert out["sandbox_id"] == live_sandbox
    assert out["remote_path"] == path
    assert _read_remote(live_sandbox, path, as_text=True) == payload


def test_write_bytes_roundtrip(live_sandbox):
    path = f"/tmp/code_modal_write_test_{uuid.uuid4().hex}.bin"
    payload = b"\x00\xff\xfebinary"
    out = write_to_sandbox(live_sandbox, path, payload)
    assert out["is_error"] is False
    assert _read_remote(live_sandbox, path, as_text=False) == payload


def test_write_bytearray_uses_write_bytes(live_sandbox):
    path = f"/tmp/code_modal_write_test_{uuid.uuid4().hex}.bin"
    payload = bytearray(b"abc")
    out = write_to_sandbox(live_sandbox, path, payload)
    assert out["is_error"] is False
    assert _read_remote(live_sandbox, path, as_text=False) == bytes(payload)


def test_write_creates_nested_path(live_sandbox):
    path = f"/tmp/nested/{uuid.uuid4().hex}/deep/file.txt"
    payload = "nested ok"
    out = write_to_sandbox(live_sandbox, path, payload)
    assert out["is_error"] is False
    assert _read_remote(live_sandbox, path, as_text=True) == payload


def test_write_overwrites_existing_file(live_sandbox):
    path = f"/tmp/code_modal_write_test_{uuid.uuid4().hex}.txt"
    assert write_to_sandbox(live_sandbox, path, "first")["is_error"] is False
    assert write_to_sandbox(live_sandbox, path, "second")["is_error"] is False
    assert _read_remote(live_sandbox, path, as_text=True) == "second"


def test_write_unknown_sandbox_returns_error():
    fake_id = "sb-invalid000000000000000000000000"
    out = write_to_sandbox(fake_id, "/tmp/x.txt", "x")
    assert out["is_error"] is True
    assert "not found" in out["result"].lower()
