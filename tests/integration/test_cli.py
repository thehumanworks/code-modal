import json

import pytest

from code_modal.cli import main
from code_modal.sandbox import create_sandbox, terminate_sandboxes

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


def test_cli_run_roundtrip(live_sandbox, capsys):
    exit_code = main(
        [
            "run",
            "--sandbox",
            live_sandbox,
            "--",
            "printf",
            "hello",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["returncode"] == 0
    assert payload["stdout"] == "hello"


def test_cli_snapshot_directory(live_sandbox, capsys):
    exit_code = main(
        [
            "sandbox",
            "snapshot",
            "--sandbox",
            live_sandbox,
            "--path",
            "/tmp",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["image_id"]
