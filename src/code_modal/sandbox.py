import os
import modal
from modal.exception import (
    NotFoundError,
    SandboxFilesystemError,
    SandboxFilesystemIsADirectoryError,
    SandboxFilesystemNotADirectoryError,
    SandboxFilesystemNotFoundError,
    SandboxFilesystemPermissionError,
)
from .constants import (
    DEFAULT_SANDBOX_TIMEOUT,
    DEFAULT_SANDBOX_IDLE_TIMEOUT,
    DEFAULT_ENCRYPTED_PORTS,
    DEFAULT_UNENCRYPTED_PORTS,
    DEFAULT_WORKDIR,
)
from .image import build_or_get_image
from .shared import get_app


def _resolve_ports(ports: str):
    return [int(port.strip()) for port in ports.split(",") if port.strip()]


def create_sandbox(
    sandbox_name: str | None = None,
    image_id: str | None = None,
    volumes: dict[str, str] | None = None,
    timeout: int = DEFAULT_SANDBOX_TIMEOUT,
    idle_timeout: int = DEFAULT_SANDBOX_IDLE_TIMEOUT,
    encrypted_ports: str = DEFAULT_ENCRYPTED_PORTS,
    unencrypted_ports: str = DEFAULT_UNENCRYPTED_PORTS,
    env: dict[str, str | None] | None = None,
    secrets: list[str] | None = None,
    workdir: str = DEFAULT_WORKDIR,
):
    app = get_app()
    if secrets is not None:
        secrets = [modal.Secret.from_name(secret) for secret in secrets]

    if volumes is None:
        volume_mounts = {}
    else:
        volume_mounts = {
            path: modal.Volume.from_name(volume_name, create_if_missing=True, version=2)
            for path, volume_name in volumes.items()
        }

    if image_id is not None:
        image = modal.Image.from_id(image_id)
    else:
        image = build_or_get_image(app)

    sandbox = modal.Sandbox.create(
        app=app,
        image=image,
        timeout=timeout,
        idle_timeout=idle_timeout,
        encrypted_ports=_resolve_ports(encrypted_ports),
        unencrypted_ports=_resolve_ports(unencrypted_ports),
        secrets=secrets,
        workdir=workdir,
        volumes=volume_mounts,
        name=sandbox_name,
        env=env,
    )
    return {"sandbox_id": sandbox.object_id}


def terminate_sandboxes(sandbox_ids: list[str] | None = None, all: bool = False):
    if all:
        sandbox_ids = [sandbox.object_id for sandbox in modal.Sandbox.list()]

    terminated = []
    not_found = []
    for sandbox_id in sandbox_ids:
        try:
            sandbox = modal.Sandbox.from_id(sandbox_id)
            sandbox.terminate()
            sandbox.detach()
            terminated.append(sandbox_id)
        except NotFoundError:
            not_found.append(sandbox_id)
            continue

    return {
        "terminated": terminated if len(terminated) > 0 else None,
        "not_found": not_found if len(not_found) > 0 else None,
    }


def list_sandboxes():
    return [
        {"sandbox_id": sandbox.object_id, "tags": sandbox.get_tags()}
        for sandbox in modal.Sandbox.list()
    ]


def snapshot_sandbox(sandbox_id: str, remote_path: str | None = None):
    sandbox = modal.Sandbox.from_id(sandbox_id)
    if remote_path is not None:
        image = sandbox.snapshot_directory(remote_path)
    else:
        image = sandbox.snapshot_filesystem(timeout=90)
    return {"image_id": image.object_id}


def copy_file_to_sandbox(sandbox_id: str, local_path: str, remote_path: str):
    if not modal.is_local():
        return {
            "is_error": True,
            "result": "Cannot copy file to sandbox from remote. You must be in a local environment.",
        }

    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        sandbox.mkdir(os.path.dirname(remote_path), parents=True)
        sandbox.filesystem.copy_from_local(
            local_path,
            remote_path,
        )
        return {
            "is_error": False,
            "sandbox_id": sandbox_id,
            "remote_path": remote_path,
            "result": "File copied to sandbox successfully",
        }
    except NotFoundError:
        return {
            "is_error": True,
            "result": "The Sandbox was not found.",
        }
    except SandboxFilesystemNotADirectoryError:
        return {
            "is_error": True,
            "result": "A parent path component of the remote path is not a directory.",
        }
    except SandboxFilesystemIsADirectoryError:
        return {
            "is_error": True,
            "result": "The remote path points to a directory.",
        }
    except SandboxFilesystemPermissionError:
        return {
            "is_error": True,
            "result": "Write permission is denied in the Sandbox.",
        }
    except SandboxFilesystemError:
        return {
            "is_error": True,
            "result": "The command failed for any other reason.",
        }
    except FileNotFoundError:
        return {
            "is_error": True,
            "result": "The local path does not exist.",
        }
    except IsADirectoryError:
        return {
            "is_error": True,
            "result": "The local path is a directory.",
        }
    except PermissionError:
        return {
            "is_error": True,
            "result": "Reading the local path is not permitted.",
        }


def copy_file_from_sandbox(sandbox_id: str, remote_path: str, local_path: str):
    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        sandbox.filesystem.copy_to_local(
            remote_path,
            local_path,
        )
        return {
            "is_error": False,
            "result": "File copied from sandbox to local successfully",
        }
    except NotFoundError:
        return {
            "is_error": True,
            "result": "The Sandbox was not found.",
        }
    except SandboxFilesystemNotFoundError:
        return {
            "is_error": True,
            "result": "The remote path does not exist.",
        }
    except SandboxFilesystemIsADirectoryError:
        return {
            "is_error": True,
            "result": "The remote path points to a directory.",
        }
    except SandboxFilesystemPermissionError:
        return {
            "is_error": True,
            "result": "Read permission is denied in the Sandbox.",
        }
    except SandboxFilesystemError:
        return {
            "is_error": True,
            "result": "The command failed for any other reason.",
        }
    except IsADirectoryError:
        return {
            "is_error": True,
            "result": "The local path points to a directory.",
        }
    except NotADirectoryError:
        return {
            "is_error": True,
            "result": "A component of the local path parent is not a directory.",
        }
    except PermissionError:
        return {
            "is_error": True,
            "result": "Writing the local path is not permitted.",
        }


def write_to_sandbox(
    sandbox_id: str,
    remote_path: str,
    content: str | bytes | bytearray | memoryview,
):
    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        if isinstance(content, str):
            sandbox.filesystem.write_text(content, remote_path)
        else:
            sandbox.filesystem.write_bytes(content, remote_path)
        return {
            "is_error": False,
            "sandbox_id": sandbox_id,
            "remote_path": remote_path,
            "result": "Content written to sandbox successfully",
        }
    except NotFoundError:
        return {
            "is_error": True,
            "result": "The Sandbox was not found.",
        }
    except SandboxFilesystemNotADirectoryError:
        return {
            "is_error": True,
            "result": "A parent path component of the remote path is not a directory.",
        }
    except SandboxFilesystemIsADirectoryError:
        return {
            "is_error": True,
            "result": "The remote path points to a directory.",
        }
    except SandboxFilesystemPermissionError:
        return {
            "is_error": True,
            "result": "Write permission is denied in the Sandbox.",
        }
    except SandboxFilesystemError:
        return {
            "is_error": True,
            "result": "The command failed for any other reason.",
        }
