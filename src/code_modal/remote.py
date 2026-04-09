import shlex
import modal
from .shared import get_app
from .constants import DEFAULT_EXEC_TIMEOUT, DEFAULT_WORKDIR
from .execution import _build_exec_kwargs

app = get_app()


@app.function(timeout=DEFAULT_EXEC_TIMEOUT)
def spawn(
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

    return {"function_call_id": p.id}


def poll(function_call_id: str):
    try:
        fn_call = modal.FunctionCall.from_id(function_call_id=function_call_id)
        return fn_call.get(timeout=0)
    except TimeoutError:
        return {
            "result": "pending: try again later",
            "function_call_id": function_call_id,
        }
    except modal.exception.FunctionTimeoutError:
        return {
            "result": "error: function execution timed out",
            "function_call_id": function_call_id,
            "is_error": True,
        }
    except modal.exception.OutputExpiredError:
        return {
            "result": "error: output expired",
            "function_call_id": function_call_id,
            "is_error": True,
        }
    except modal.exception.NotFoundError:
        return {
            "result": f"error: task {function_call_id} not found",
            "function_call_id": function_call_id,
            "is_error": True,
        }
    except modal.exception.Error as e:
        return {
            "result": f"error: {e}",
            "function_call_id": function_call_id,
            "is_error": True,
        }
    except Exception as e:
        return {"result": f"error: {e}", "is_error": True}
