# code-modal

Command-line interface for working with [Modal](https://modal.com/) sandboxes: create and manage sandboxes, run commands (blocking or detached), stream output, sync files and volumes, and install packages inside a sandbox.

## Requirements

- **Python** 3.14 or newer
- A **Modal** account and credentials configured for the Modal Python SDK (see [Modal setup](https://modal.com/docs/guide))

## Install

From PyPI (when published):

```bash
pip install code-modal
```

From a clone of this repository:

```bash
pip install .
# or, with uv:
uv pip install .
```

For local development (editable install + test tools):

```bash
uv sync --group dev
# or: pip install -e ".[dev]"
```

## Commands

The CLI is available under two names:

| Command       | Description        |
|---------------|--------------------|
| `code-modal`  | Full name          |
| `cm`          | Short alias        |

Both invoke the same program. Examples below use `cm`; substitute `code-modal` if you prefer.

```bash
cm --help
```

### Subcommands

| Group    | Subcommands | Purpose |
|----------|-------------|---------|
| `sandbox` | `create`, `list`, `terminate`, `snapshot` | Lifecycle and inspection of sandboxes |
| `run`     | — | Execute a shell command in a sandbox (optional `--detach`, `--snapshot`) |
| `stream`  | — | Stream command output to the terminal |
| `job`     | `poll` | Poll an async function call by ID |
| `install` | `apt`, `pip`, `npm` | Install packages inside a sandbox |
| `file`    | `push`, `pull`, `write` | Copy or write files to/from a sandbox |
| `volume`  | `push`, `pull` | Sync data with a Modal volume |

Most commands print **JSON** to stdout. Add `--pretty` where supported for readable formatting.

### Examples

Create a sandbox (output includes `sandbox_id`):

```bash
cm sandbox create --name my-agent --image <image-id>
```

Run a command in a sandbox (use `--` before the remote command):

```bash
cm run --sandbox sb-xxxxxxxx -- python --version
```

Stream output instead of JSON:

```bash
cm stream --sandbox sb-xxxxxxxx -- ls -la
```

Terminate sandboxes:

```bash
cm sandbox terminate --sandbox sb-one --sandbox sb-two
# or
cm sandbox terminate --all
```

Push a local file into the sandbox:

```bash
cm file push --sandbox sb-xxxxxxxx ./local.txt /code/remote.txt
```

## Development

Run the test suite:

```bash
pytest
```

Tests marked `integration` call Modal cloud APIs and need valid credentials; skip them unless you intend to run integration tests:

```bash
pytest -m "not integration"
```
