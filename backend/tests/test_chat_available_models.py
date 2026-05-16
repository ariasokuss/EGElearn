from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.chat.router import get_available_models
from src.config import get_settings


@pytest.mark.asyncio
async def test_available_models_hides_default_reasoning_level():
    get_settings.cache_clear()
    container = SimpleNamespace(settings=get_settings())

    response = await get_available_models(container)

    assert response == {"models": ["YandexGPT"], "reasoning_levels": []}


def test_backend_served_chat_ui_only_submits_yandex_model():
    html = Path("src/chat/assets/index.html").read_text()
    legacy_chatgpt = 'value="Chat' + 'GPT 5.4"'
    legacy_sonnet = 'value="Clau' + 'de Son' + 'net 4.6"'
    legacy_opus = 'value="Clau' + 'de O' + 'pus 4.6"'

    assert 'value="YandexGPT"' in html
    assert legacy_chatgpt not in html
    assert legacy_sonnet not in html
    assert legacy_opus not in html
    assert 'localStorage.getItem("nc_model") || "YandexGPT"' in html
    assert 'localStorage.getItem("nc_reasoning") || ""' in html
    assert 'document.getElementById("modelSelect").value || "YandexGPT"' in html
