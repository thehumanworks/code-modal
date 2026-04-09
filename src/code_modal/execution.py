from .constants import DEFAULT_WORKDIR
from modal.stream_type import StreamType
import shlex
import modal


def _build_exec_kwargs(
    command_timeout: int,
    pty: bool = False,
    secrets: list[str] | None = None,
    env: dict[str, str] | None = None,
    workdir: str = DEFAULT_WORKDIR,
    pipe_to_devnull: bool = False,
):

    exec_kwargs = {
        "timeout": command_timeout,
        "pty": pty,
        "workdir": workdir,
    }
    if pipe_to_devnull:
        exec_kwargs["stdout"] = StreamType.DEVNULL
        exec_kwargs["stderr"] = StreamType.DEVNULL
    if secrets is not None:
        secrets = [modal.Secret.from_name(secret) for secret in secrets]
        exec_kwargs["secrets"] = secrets
    if env is not None:
        exec_kwargs["env"] = env

    return exec_kwargs


def exec(
    sandbox_id: str,
    command: str,
    command_timeout: int,
    pty: bool = False,
    secrets: list[str] | None = None,
    env: dict[str, str] | None = None,
    workdir: str = DEFAULT_WORKDIR,
    pipe_to_devnull: bool = False,
):
    sandbox = modal.Sandbox.from_id(sandbox_id)
    exec_kwargs = _build_exec_kwargs(
        command_timeout, pty, secrets, env, workdir, pipe_to_devnull
    )
    p = sandbox.exec(*shlex.split(command), **exec_kwargs)

    stdout = p.stdout.read()
    stderr: str | None = None
    if not pty:
        stderr = p.stderr.read()

    p.wait()

    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": p.returncode,
    }


def stream(
    sandbox_id: str,
    command: str,
    command_timeout: int,
    pty: bool = False,
    secrets: list[str] | None = None,
    env: dict[str, str] | None = None,
    workdir: str = DEFAULT_WORKDIR,
    pipe_to_devnull: bool = False,
):
    sandbox = modal.Sandbox.from_id(sandbox_id)
    exec_kwargs = _build_exec_kwargs(
        command_timeout, pty, secrets, env, workdir, pipe_to_devnull
    )
    p = sandbox.exec(*shlex.split(command), **exec_kwargs)

    for line in p.stdout:
        yield line

    p.wait()

    if p.returncode != 0:
        raise Exception(
            f"Command failed with return code {p.returncode}: {p.stderr.read() or p.stdout.read()}"
        )
    return
