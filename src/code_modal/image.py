import tempfile
from pathlib import Path

import modal

from .constants import (
    PYTHON_VERSION,
    NODE_VERSION,
    RUST_VERSION,
    GO_VERSION,
    BUN_VERSION,
    DEFAULT_WORKDIR,
)
from .shared import get_app

BASE_APT_PACKAGES = (
    "bash",
    "build-essential",
    "ca-certificates",
    "curl",
    "fd-find",
    "git",
    "gh",
    "gnupg",
    "jq",
    "libbz2-dev",
    "libffi-dev",
    "liblzma-dev",
    "libreadline-dev",
    "libsqlite3-dev",
    "libssl-dev",
    "npm",
    "openssh-server",
    "openssh-client",
    "pkg-config",
    "ripgrep",
    "tk-dev",
    "unzip",
    "uuid-dev",
    "xz-utils",
    "zip",
    "zlib1g-dev",
)

SETUP_MISE_COMMANDS = "echo 'eval \"$(mise activate bash)\"' >> /root/.bashrc && echo 'eval \"$(mise activate bash --shims)\"' >> /root/.bash_profile"


def build_or_get_image(app: modal.App, force_build: bool = False) -> modal.Image:
    with modal.enable_output():
        image = modal.Image.debian_slim(PYTHON_VERSION, force_build=force_build)
        image = image.apt_install(*BASE_APT_PACKAGES)
        image = image.env(
            {
                "LANG": "C.UTF-8",
                "HOME": "/root",
                "SHELL": "/bin/bash",
                "DEBIAN_FRONTEND": "noninteractive",
                "IS_SANDBOX": "1",
                "UV_NO_PROGRESS": "1",
                "UV_UNMANAGED_INSTALL": "/usr/local/bin",
                "COREPACK_DEFAULT_TO_LATEST": "0",
                "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                "COREPACK_ENABLE_AUTO_PIN": "0",
                "COREPACK_ENABLE_STRICT": "0",
                "PATH": "/root/.cargo/bin:/root/.local/bin:/root/.local/share/mise/shims:/usr/local/bin:$PATH",
            }
        )
        image = image.run_commands(
            "if command -v chsh >/dev/null 2>&1; then chsh -s /bin/bash root; elif command -v usermod >/dev/null 2>&1; then usermod -s /bin/bash root; fi",
        )
        image = image.run_commands(
            "npm install -g @jdxcode/mise",
            SETUP_MISE_COMMANDS,
        )
        image = image.run_commands(
            f"mise use -g node@{NODE_VERSION} rust@{RUST_VERSION} go@{GO_VERSION} bun@{BUN_VERSION}"
        )
        image = image.shell(shell_commands=["bash", "-lc"])
        image = image.workdir(DEFAULT_WORKDIR)
        image = image.build(app=app)

        return image


def build_image_from_dockerfile(
    dockerfile_path: str | None = None,
    dockerfile_content: str | None = None,
    force_build: bool = False,
    app: modal.App | None = None,
) -> dict:
    if (dockerfile_path is None) == (dockerfile_content is None):
        return {
            "is_error": True,
            "result": "provide exactly one of dockerfile_path or dockerfile_content",
        }

    if dockerfile_path is not None and not modal.is_local():
        return {
            "is_error": True,
            "result": "dockerfile_path requires a local environment; pass dockerfile_content instead.",
        }

    app = app or get_app()

    with modal.enable_output():
        if dockerfile_path is not None:
            image = modal.Image.from_dockerfile(dockerfile_path, force_build=force_build)
            image = image.build(app=app)
            return {"image_id": image.object_id}

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "Dockerfile"
            tmp_path.write_text(dockerfile_content)
            image = modal.Image.from_dockerfile(str(tmp_path), force_build=force_build)
            image = image.build(app=app)
            return {"image_id": image.object_id}
