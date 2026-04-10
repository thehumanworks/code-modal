import io
import json
import shlex

import pytest

from code_modal import cli


def test_sandbox_create_parses_repeatable_flags(monkeypatch, capsys):
    captured = {}

    def fake_create_sandbox(**kwargs):
        captured.update(kwargs)
        return {"sandbox_id": "sb-123"}

    monkeypatch.setattr(cli, "create_sandbox", fake_create_sandbox)

    exit_code = cli.main(
        [
            "sandbox",
            "create",
            "--name",
            "agent",
            "--image",
            "im-123",
            "--volume",
            "/code=repo-vol",
            "--env",
            "FOO=bar",
            "--secret",
            "modal-secret",
            "--encrypted-port",
            "443",
            "--unencrypted-port",
            "9000",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"sandbox_id": "sb-123"}
    assert captured["sandbox_name"] == "agent"
    assert captured["image_id"] == "im-123"
    assert captured["volumes"] == {"/code": "repo-vol"}
    assert captured["env"] == {"FOO": "bar"}
    assert captured["secrets"] == ["modal-secret"]
    assert captured["encrypted_ports"] == "443"
    assert captured["unencrypted_ports"] == "9000"


def test_run_wraps_command_in_shell_and_snapshots(monkeypatch, capsys):
    captured = {}

    def fake_exec(**kwargs):
        captured.update(kwargs)
        return {"stdout": "ok\n", "stderr": "", "returncode": 0}

    monkeypatch.setattr(cli, "exec_command", fake_exec)
    monkeypatch.setattr(cli, "snapshot_sandbox", lambda sandbox_id: {"image_id": "im-999"})

    exit_code = cli.main(
        [
            "run",
            "--sandbox",
            "sb-123",
            "--snapshot",
            "--",
            "python",
            "-c",
            'print("hi there")',
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    wrapped = shlex.split(captured["command"])

    assert exit_code == 0
    assert wrapped[:2] == ["bash", "-lc"]
    assert wrapped[2] == 'python -c \'print("hi there")\''
    assert payload["snapshot"] == {"image_id": "im-999"}
    assert payload["stdout"] == "ok\n"


def test_run_detach_uses_spawn(monkeypatch, capsys):
    captured = {}

    def fake_spawn(**kwargs):
        captured.update(kwargs)
        return {"function_call_id": "fc-123"}

    monkeypatch.setattr(cli, "spawn", fake_spawn)

    exit_code = cli.main(
        [
            "run",
            "--sandbox",
            "sb-123",
            "--detach",
            "--",
            "sleep",
            "60",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"function_call_id": "fc-123"}
    assert shlex.split(captured["command"])[:2] == ["bash", "-lc"]


def test_job_poll_normalizes_pending_result(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "poll",
        lambda function_call_id: {
            "result": "pending: try again later",
            "function_call_id": function_call_id,
        },
    )

    exit_code = cli.main(["job", "poll", "--call", "fc-123"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "pending"
    assert payload["function_call_id"] == "fc-123"


def test_install_apt_builds_shell_command(monkeypatch, capsys):
    captured = {}

    def fake_exec(**kwargs):
        captured.update(kwargs)
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(cli, "exec_command", fake_exec)

    exit_code = cli.main(
        [
            "install",
            "apt",
            "--sandbox",
            "sb-123",
            "ffmpeg",
            "git",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    wrapped = shlex.split(captured["command"])

    assert exit_code == 0
    assert payload["returncode"] == 0
    assert wrapped[:2] == ["bash", "-lc"]
    assert (
        wrapped[2]
        == "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y -- ffmpeg git"
    )


def test_image_build_from_path(monkeypatch, capsys):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {"image_id": "im-abc"}

    monkeypatch.setattr(cli, "build_image_from_dockerfile", fake_build)

    exit_code = cli.main(["image", "build", "--path", "/tmp/Dockerfile"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"image_id": "im-abc"}
    assert captured["dockerfile_path"] == "/tmp/Dockerfile"
    assert captured["dockerfile_content"] is None
    assert captured["force_build"] is False


def test_image_build_from_content(monkeypatch, capsys):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {"image_id": "im-xyz"}

    monkeypatch.setattr(cli, "build_image_from_dockerfile", fake_build)

    exit_code = cli.main(["image", "build", "--content", "FROM python:3.12-slim"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"image_id": "im-xyz"}
    assert captured["dockerfile_path"] is None
    assert captured["dockerfile_content"] == "FROM python:3.12-slim"


def test_image_build_from_stdin(monkeypatch, capsys):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {"image_id": "im-stdin"}

    monkeypatch.setattr(cli, "build_image_from_dockerfile", fake_build)
    monkeypatch.setattr("sys.stdin", io.StringIO("FROM alpine:3.20\nRUN echo hi\n"))

    exit_code = cli.main(["image", "build", "--stdin"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"image_id": "im-stdin"}
    assert captured["dockerfile_path"] is None
    assert captured["dockerfile_content"] == "FROM alpine:3.20\nRUN echo hi\n"


def test_image_build_forwards_force_build(monkeypatch, capsys):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {"image_id": "im-forced"}

    monkeypatch.setattr(cli, "build_image_from_dockerfile", fake_build)

    exit_code = cli.main(
        ["image", "build", "--path", "/tmp/Dockerfile", "--force-build"]
    )

    assert exit_code == 0
    assert captured["force_build"] is True


def test_image_build_rejects_multiple_inputs(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "build_image_from_dockerfile", lambda **kwargs: {"image_id": "im-x"}
    )

    exit_code = cli.main(
        ["image", "build", "--path", "/tmp/Dockerfile", "--content", "FROM alpine"]
    )

    assert exit_code == 2


def test_image_build_returns_error_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "build_image_from_dockerfile",
        lambda **kwargs: {"is_error": True, "result": "boom"},
    )

    exit_code = cli.main(["image", "build", "--content", "FROM alpine"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["is_error"] is True


def test_volume_push_accepts_mapping_syntax(monkeypatch, capsys):
    captured = {}

    def fake_copy_to_volume(volume_name, local_path, remote_path, **kwargs):
        captured.update(
            {
                "volume_name": volume_name,
                "local_path": local_path,
                "remote_path": remote_path,
                **kwargs,
            }
        )
        return {"volume_name": volume_name, "remote_path": remote_path}

    monkeypatch.setattr(cli, "copy_to_volume", fake_copy_to_volume)

    exit_code = cli.main(
        [
            "volume",
            "push",
            "repo-vol",
            ".:/repo",
            "--recursive",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"volume_name": "repo-vol", "remote_path": "/repo"}
    assert captured["volume_name"] == "repo-vol"
    assert captured["local_path"] == "."
    assert captured["remote_path"] == "/repo"
    assert captured["recursive"] is True
    assert captured["force_overwrite"] is False
