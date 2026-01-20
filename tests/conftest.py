
import os
from typing import Generator
import pytest

@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Clear YNU_XK_ prefixed environment variables."""
    old_env = dict(os.environ)
    for key in list(os.environ.keys()):
        if key.startswith("YNU_XK_"):
            del os.environ[key]
    yield
    os.environ.clear()
    os.environ.update(old_env)
