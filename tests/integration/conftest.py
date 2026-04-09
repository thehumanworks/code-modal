import pytest
from modal.config import config


@pytest.fixture(autouse=True)
def _require_modal_credentials():
    if not (config.get("token_id") and config.get("token_secret")):
        pytest.skip(
            "Modal credentials not configured. Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET "
            "or run `modal token set`."
        )
