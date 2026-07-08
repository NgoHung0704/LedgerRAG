"""model_present matching used by the Ollama health check."""

import pytest

from tablerag.models.ollama import model_present

INSTALLED = ["qwen2.5vl:32b", "bge-m3:latest", "qwen2.5:7b", "mistral:latest"]


@pytest.mark.parametrize("model,expected", [
    ("qwen2.5vl:32b", True),          # exact tag
    ("bge-m3", True),                 # no tag -> matches bge-m3:latest
    ("qwen2.5:7b", True),
    ("qwen2.5vl:7b", False),          # right family, wrong tag not installed
    ("qwen3-vl:8b-instruct", False),  # not installed at all
    ("mistral", True),                # no tag -> matches mistral:latest
    ("", True),                       # unset model is not a health failure
])
def test_model_present(model, expected):
    assert model_present(model, INSTALLED) is expected
