"""Ollama's mmap of model files faults the GPU on this AMD box.

Loading a model with mmap=true leaves its tensors in file-backed pages. amdgpu
cannot pin those for the GPU — `init_user_pages: Failed to get user pages: -1`,
dozens of times — and the GPU then reads memory that was never mapped:

    amdgpu [gfxhub] page fault ... PERMISSION_FAULTS: 0x3   in process ollama

Every model load did it, so it was not bad luck: 90 crashes, ~1 GB of core dump
each, 85 GB, a full disk, and from there HTTP 500 on /api/chat and a reranker
that could not load either. One flag under all of it.

Measured on the box 2026-08-21: the same question that had returned 500 after
12m40s answered in seconds with `use_mmap: false`, and dmesg logged no new
fault.

Default stays True. mmap is the right choice on hardware where it works — it
loads lazily and shares page cache between processes — so this is the AMD
reference configuration's business (SPEC Appendix A), not a global downgrade.
"""

import pytest

from tablerag.core.config import EndpointConfig
from tablerag.models.base import Msg
from tablerag.models.ollama import OllamaProvider


def _provider(**kw) -> OllamaProvider:
    return OllamaProvider(EndpointConfig(
        base_url="http://x:11434", model_name="qwen2.5:14b", **kw))


class _Recorder:
    """Captures the payload instead of sending it."""

    def __init__(self):
        self.payload = None

    def stream(self, _method, _url, json=None):
        self.payload = json
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        return
        yield  # pragma: no cover — an empty async generator

    async def aclose(self):
        pass


@pytest.fixture
def sent(monkeypatch):
    rec = _Recorder()

    class _Client:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return rec

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr("tablerag.models.ollama.httpx.AsyncClient", _Client)
    return rec


async def _ask(provider):
    async for _ in provider.chat([Msg(role="user", content="hi")]):
        pass


@pytest.mark.asyncio
async def test_mmap_is_left_alone_by_default(sent):
    await _ask(_provider())
    assert "use_mmap" not in (sent.payload.get("options") or {})


@pytest.mark.asyncio
async def test_disabling_mmap_reaches_ollama_as_an_option(sent):
    await _ask(_provider(use_mmap=False))
    assert sent.payload["options"]["use_mmap"] is False


@pytest.mark.asyncio
async def test_the_caller_can_still_override_it(sent):
    # a per-request option wins: the provider states a default, not a policy
    await _ask(_provider(use_mmap=False))
    assert sent.payload["options"]["use_mmap"] is False


@pytest.mark.asyncio
async def test_disabling_mmap_does_not_disturb_the_other_options(sent):
    provider = _provider(use_mmap=False)
    async for _ in provider.chat([Msg(role="user", content="hi")],
                                 options={"num_ctx": 32768}):
        pass
    assert sent.payload["options"] == {"num_ctx": 32768, "use_mmap": False}
