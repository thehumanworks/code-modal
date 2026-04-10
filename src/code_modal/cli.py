import argparse
import json
import shlex
import sys
from typing import Any

from .constants import (
    DEFAULT_ENCRYPTED_PORTS,
    DEFAULT_EXEC_TIMEOUT,
    DEFAULT_SANDBOX_IDLE_TIMEOUT,
    DEFAULT_SANDBOX_TIMEOUT,
    DEFAULT_UNENCRYPTED_PORTS,
    DEFAULT_WORKDIR,
)
from .execution import exec as exec_command
from .execution import stream as stream_command
from .sandbox import (
    copy_file_from_sandbox,
    copy_file_to_sandbox,
    create_sandbox,
    list_sandboxes,
    snapshot_sandbox,
    terminate_sandboxes,
    write_to_sandbox,
)
from .volume import copy_to_volume, download_from_volume


class CLIError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str):
        raise CLIError(message, exit_code=2)


def spawn(*args, **kwargs):
    from .remote import spawn as remote_spawn

    return remote_spawn(*args, **kwargs)


def poll(*args, **kwargs):
    from .remote import poll as remote_poll

    return remote_poll(*args, **kwargs)


def _json_safe(value: Any):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _emit_json(value: Any, pretty: bool = False, stream=None):
    if stream is None:
        stream = sys.stdout
    json.dump(
        _json_safe(value),
        stream,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=pretty,
    )
    stream.write("\n")


def _parse_assignments(
    items: list[str] | None,
    *,
    flag: str,
    separator: str = "=",
) -> dict[str, str] | None:
    if not items:
        return None

    assignments: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition(separator)
        if not sep or not key or not value:
            raise CLIError(f"{flag} entries must look like KEY{separator}VALUE")
        assignments[key] = value
    return assignments


def _build_ports_csv(values: list[int] | None, default: str) -> str:
    if values is None:
        return default
    return ",".join(str(value) for value in values)


def _parse_path_pair(
    items: list[str],
    *,
    flag: str,
    separator: str = ":",
) -> tuple[str, str]:
    if len(items) == 2:
        return items[0], items[1]
    if len(items) == 1:
        left, sep, right = items[0].partition(separator)
        if sep and left and right:
            return left, right
    raise CLIError(f"{flag} expects LOCAL{separator}REMOTE or LOCAL REMOTE")


def _command_text(command_parts: list[str]) -> str:
    if command_parts and command_parts[0] == "--":
        command_parts = command_parts[1:]
    if not command_parts:
        raise CLIError("command is required after '--'")
    if len(command_parts) == 1:
        return command_parts[0]
    return shlex.join(command_parts)


def _shell_command(command_parts: list[str]) -> str:
    return f"bash -lc {shlex.quote(_command_text(command_parts))}"


def _write_stream(chunk: Any):
    if isinstance(chunk, bytes):
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        return

    sys.stdout.write(chunk)
    sys.stdout.flush()


def _normalize_poll_result(result: Any, function_call_id: str):
    payload = _json_safe(result)
    if isinstance(payload, dict):
        payload.setdefault("function_call_id", function_call_id)
        text = payload.get("result")
        if isinstance(text, str) and text.startswith("pending:"):
            return {"status": "pending", **payload}
        if payload.get("is_error") or (
            isinstance(text, str) and text.startswith("error:")
        ):
            return {"status": "error", **payload}
        return {"status": "completed", **payload}

    return {
        "status": "completed",
        "function_call_id": function_call_id,
        "result": payload,
    }


def _snapshot_if_requested(result: dict[str, Any], *, sandbox_id: str, enabled: bool):
    if enabled and result.get("returncode") == 0:
        result = {
            **result,
            "snapshot": snapshot_sandbox(sandbox_id),
        }
    return result


def _exec_kwargs(args):
    return {
        "sandbox_id": args.sandbox,
        "command_timeout": args.timeout,
        "pty": getattr(args, "pty", False),
        "secrets": args.secret,
        "env": _parse_assignments(args.env, flag="--env"),
        "workdir": args.workdir,
        "pipe_to_devnull": getattr(args, "pipe_to_devnull", False),
    }


def _result_exit_code(result: Any, default: int = 0):
    if isinstance(result, dict):
        if result.get("is_error"):
            return 1
        if isinstance(result.get("returncode"), int):
            return result["returncode"]
    return default


def handle_sandbox_create(args):
    result = create_sandbox(
        sandbox_name=args.name,
        image_id=args.image,
        volumes=_parse_assignments(args.volume, flag="--volume"),
        timeout=args.timeout,
        idle_timeout=args.idle_timeout,
        encrypted_ports=_build_ports_csv(
            args.encrypted_port, DEFAULT_ENCRYPTED_PORTS
        ),
        unencrypted_ports=_build_ports_csv(
            args.unencrypted_port, DEFAULT_UNENCRYPTED_PORTS
        ),
        env=_parse_assignments(args.env, flag="--env"),
        secrets=args.secret,
        workdir=args.workdir,
    )
    _emit_json(result, pretty=args.pretty)
    return 0


def handle_sandbox_list(args):
    result = list_sandboxes()
    _emit_json(result, pretty=args.pretty)
    return 0


def handle_sandbox_terminate(args):
    result = terminate_sandboxes(sandbox_ids=args.sandbox, all=args.all)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_sandbox_snapshot(args):
    result = snapshot_sandbox(args.sandbox, remote_path=args.path)
    _emit_json(result, pretty=args.pretty)
    return 0


def handle_run(args):
    command = _shell_command(args.command)
    kwargs = _exec_kwargs(args)

    if args.detach:
        if args.snapshot:
            raise CLIError("--snapshot is not supported with --detach")
        result = spawn(command=command, **kwargs)
        _emit_json(result, pretty=args.pretty)
        return 0

    result = exec_command(command=command, **kwargs)
    result = _snapshot_if_requested(result, sandbox_id=args.sandbox, enabled=args.snapshot)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_stream(args):
    command = _shell_command(args.command)
    kwargs = _exec_kwargs(args)
    try:
        for chunk in stream_command(command=command, **kwargs):
            _write_stream(chunk)
    except Exception as exc:
        raise CLIError(str(exc), exit_code=1) from exc
    return 0


def handle_job_poll(args):
    result = _normalize_poll_result(poll(args.call), args.call)
    _emit_json(result, pretty=args.pretty)
    if result["status"] == "error":
        return 1
    return 0


def _install_command(kind: str, packages: list[str], *, global_install: bool = False):
    quoted_packages = shlex.join(packages)
    if kind == "apt":
        return (
            "apt-get update && "
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y -- {quoted_packages}"
        )
    if kind == "pip":
        return f"python -m pip install {quoted_packages}"
    if kind == "npm":
        prefix = "npm install -g" if global_install else "npm install"
        return f"{prefix} {quoted_packages}"
    raise CLIError(f"unsupported install command: {kind}")


def _handle_install(args, kind: str):
    result = exec_command(
        command=f"bash -lc {shlex.quote(_install_command(kind, args.packages, global_install=getattr(args, 'global_install', False)))}",
        **_exec_kwargs(args),
    )
    result = _snapshot_if_requested(result, sandbox_id=args.sandbox, enabled=args.snapshot)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_install_apt(args):
    return _handle_install(args, "apt")


def handle_install_pip(args):
    return _handle_install(args, "pip")


def handle_install_npm(args):
    return _handle_install(args, "npm")


def handle_file_push(args):
    result = copy_file_to_sandbox(args.sandbox, args.local_path, args.remote_path)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_file_pull(args):
    result = copy_file_from_sandbox(args.sandbox, args.remote_path, args.local_path)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_file_write(args):
    content = sys.stdin.read() if args.stdin else args.text
    result = write_to_sandbox(args.sandbox, args.remote_path, content)
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_volume_push(args):
    local_path, remote_path = _parse_path_pair(args.paths, flag="volume push")
    result = copy_to_volume(
        args.volume_name,
        local_path,
        remote_path,
        recursive=args.recursive,
        force_overwrite=args.force,
    )
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def handle_volume_pull(args):
    result = download_from_volume(
        args.volume_name,
        args.remote_path,
        local_path=args.local_path,
    )
    _emit_json(result, pretty=args.pretty)
    return _result_exit_code(result)


def build_parser():
    parser = ArgumentParser(prog="code-modal")

    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--pretty", action="store_true")

    exec_parent = argparse.ArgumentParser(add_help=False)
    exec_parent.add_argument("--sandbox", required=True)
    exec_parent.add_argument("--timeout", type=int, default=int(DEFAULT_EXEC_TIMEOUT))
    exec_parent.add_argument("--pty", action="store_true")
    exec_parent.add_argument("--env", action="append")
    exec_parent.add_argument("--secret", action="append")
    exec_parent.add_argument("--workdir", default=DEFAULT_WORKDIR)
    exec_parent.add_argument("--pipe-to-devnull", action="store_true")

    install_parent = argparse.ArgumentParser(add_help=False)
    install_parent.add_argument("--sandbox", required=True)
    install_parent.add_argument("--timeout", type=int, default=int(DEFAULT_EXEC_TIMEOUT))
    install_parent.add_argument("--env", action="append")
    install_parent.add_argument("--secret", action="append")
    install_parent.add_argument("--workdir", default=DEFAULT_WORKDIR)
    install_parent.add_argument("--snapshot", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    sandbox_parser = subparsers.add_parser("sandbox")
    sandbox_subparsers = sandbox_parser.add_subparsers(dest="sandbox_command", required=True)

    sandbox_create = sandbox_subparsers.add_parser(
        "create",
        parents=[json_parent],
    )
    sandbox_create.add_argument("--name")
    sandbox_create.add_argument("--image")
    sandbox_create.add_argument("--volume", action="append")
    sandbox_create.add_argument(
        "--timeout",
        type=int,
        default=int(DEFAULT_SANDBOX_TIMEOUT),
    )
    sandbox_create.add_argument(
        "--idle-timeout",
        type=int,
        default=int(DEFAULT_SANDBOX_IDLE_TIMEOUT),
    )
    sandbox_create.add_argument("--encrypted-port", action="append", type=int)
    sandbox_create.add_argument("--unencrypted-port", action="append", type=int)
    sandbox_create.add_argument("--env", action="append")
    sandbox_create.add_argument("--secret", action="append")
    sandbox_create.add_argument("--workdir", default=DEFAULT_WORKDIR)
    sandbox_create.set_defaults(handler=handle_sandbox_create)

    sandbox_list = sandbox_subparsers.add_parser("list", parents=[json_parent])
    sandbox_list.set_defaults(handler=handle_sandbox_list)

    sandbox_terminate = sandbox_subparsers.add_parser(
        "terminate",
        parents=[json_parent],
    )
    terminate_target = sandbox_terminate.add_mutually_exclusive_group(required=True)
    terminate_target.add_argument("--sandbox", action="append")
    terminate_target.add_argument("--all", action="store_true")
    sandbox_terminate.set_defaults(handler=handle_sandbox_terminate)

    sandbox_snapshot = sandbox_subparsers.add_parser(
        "snapshot",
        parents=[json_parent],
    )
    sandbox_snapshot.add_argument("--sandbox", required=True)
    sandbox_snapshot.add_argument("--path")
    sandbox_snapshot.set_defaults(handler=handle_sandbox_snapshot)

    run_parser = subparsers.add_parser("run", parents=[json_parent, exec_parent])
    run_parser.add_argument("--detach", action="store_true")
    run_parser.add_argument("--snapshot", action="store_true")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=handle_run)

    stream_parser = subparsers.add_parser("stream", parents=[exec_parent])
    stream_parser.add_argument("command", nargs=argparse.REMAINDER)
    stream_parser.set_defaults(handler=handle_stream)

    job_parser = subparsers.add_parser("job")
    job_subparsers = job_parser.add_subparsers(dest="job_command", required=True)

    job_poll = job_subparsers.add_parser("poll", parents=[json_parent])
    job_poll.add_argument("--call", required=True)
    job_poll.set_defaults(handler=handle_job_poll)

    install_parser = subparsers.add_parser("install")
    install_subparsers = install_parser.add_subparsers(dest="install_command", required=True)

    install_apt = install_subparsers.add_parser("apt", parents=[json_parent, install_parent])
    install_apt.add_argument("packages", nargs="+")
    install_apt.set_defaults(handler=handle_install_apt)

    install_pip = install_subparsers.add_parser("pip", parents=[json_parent, install_parent])
    install_pip.add_argument("packages", nargs="+")
    install_pip.set_defaults(handler=handle_install_pip)

    install_npm = install_subparsers.add_parser("npm", parents=[json_parent, install_parent])
    install_npm.add_argument("--global", dest="global_install", action="store_true")
    install_npm.add_argument("packages", nargs="+")
    install_npm.set_defaults(handler=handle_install_npm)

    file_parser = subparsers.add_parser("file")
    file_subparsers = file_parser.add_subparsers(dest="file_command", required=True)

    file_push = file_subparsers.add_parser("push", parents=[json_parent])
    file_push.add_argument("--sandbox", required=True)
    file_push.add_argument("local_path")
    file_push.add_argument("remote_path")
    file_push.set_defaults(handler=handle_file_push)

    file_pull = file_subparsers.add_parser("pull", parents=[json_parent])
    file_pull.add_argument("--sandbox", required=True)
    file_pull.add_argument("remote_path")
    file_pull.add_argument("local_path")
    file_pull.set_defaults(handler=handle_file_pull)

    file_write = file_subparsers.add_parser("write", parents=[json_parent])
    file_write.add_argument("--sandbox", required=True)
    file_write.add_argument("remote_path")
    write_content = file_write.add_mutually_exclusive_group(required=True)
    write_content.add_argument("--text")
    write_content.add_argument("--stdin", action="store_true")
    file_write.set_defaults(handler=handle_file_write)

    volume_parser = subparsers.add_parser("volume")
    volume_subparsers = volume_parser.add_subparsers(dest="volume_command", required=True)

    volume_push = volume_subparsers.add_parser("push", parents=[json_parent])
    volume_push.add_argument("volume_name")
    volume_push.add_argument("paths", nargs="+")
    volume_push.add_argument("--recursive", action="store_true")
    volume_push.add_argument("--force", action="store_true")
    volume_push.set_defaults(handler=handle_volume_push)

    volume_pull = volume_subparsers.add_parser("pull", parents=[json_parent])
    volume_pull.add_argument("volume_name")
    volume_pull.add_argument("remote_path")
    volume_pull.add_argument("local_path")
    volume_pull.set_defaults(handler=handle_volume_pull)

    return parser


def main(argv: list[str] | None = None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.handler(args)
    except CLIError as exc:
        _emit_json({"is_error": True, "error": str(exc)}, stream=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        _emit_json({"is_error": True, "error": "interrupted"}, stream=sys.stderr)
        return 130
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 1
    except Exception as exc:
        _emit_json({"is_error": True, "error": str(exc)}, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
