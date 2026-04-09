import modal
import pathlib


def copy_to_volume(
    volume_name: str,
    local_path: str,
    remote_path: str,
    recursive: bool = False,
    force_overwrite: bool = False,
):
    if not modal.is_local():
        return {
            "is_error": True,
            "result": "Cannot copy to volume from remote. You must be in a local environment.",
        }
    volume = modal.Volume.from_name(volume_name, create_if_missing=False, version=2)
    with volume.batch_upload(force=force_overwrite) as uploader:
        if pathlib.Path(local_path).is_file():
            uploader.put_file(local_path, remote_path)
        elif pathlib.Path(local_path).is_dir():
            uploader.put_directory(local_path, remote_path, recursive=recursive)
        else:
            raise ValueError(f"Invalid path: {local_path}")
    return {"volume_name": volume_name, "remote_path": remote_path}


def download_from_volume(
    volume_name: str, file_path: str, local_path: str | None = None
) -> bytes | dict[str, str | int]:
    volume = modal.Volume.from_name(volume_name, create_if_missing=False, version=2)
    bytes = b""
    for chunk in volume.read_file(file_path):
        bytes += chunk

    if local_path is not None and modal.is_local():
        with open(local_path, "wb") as f:
            f.write(bytes)
        return {"written_to": local_path, "bytes": len(bytes)}
    return bytes
