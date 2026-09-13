import re
from types import SimpleNamespace

import pytest

from paper2doc.translator import Translator, TranslatorConfig, load_local_environment


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["model"] == "test-model"
        assert kwargs["temperature"] == 0
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" 中文译文 "))]
        )


class FakeClient:
    chat = SimpleNamespace(completions=FakeCompletions())


class BatchCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        markers = re.findall(r"^\[\[PAPER2DOC:([^\]]+)\]\]$", kwargs["messages"][-1]["content"], re.MULTILINE)
        content = "\n\n".join(f"[[PAPER2DOC:{marker}]]\n中文 {marker}" for marker in markers)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class BatchFakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=BatchCompletions())


def test_translator_uses_config_and_chat_completions():
    translator = Translator(
        TranslatorConfig("key", "test-model", "http://localhost/v1"),
        client=FakeClient(),
    )
    assert translator.translate("English paragraph") == "中文译文"


def test_translator_preserves_batch_markers():
    client = BatchFakeClient()
    translator = Translator(
        TranslatorConfig("key", "test-model", "http://localhost/v1"),
        client=client,
    )

    translations = translator.translate_batch(
        [("paragraph:1", "First paragraph"), ("paragraph:2", "Second paragraph")]
    )

    assert translations == {
        "paragraph:1": "中文 paragraph:1",
        "paragraph:2": "中文 paragraph:2",
    }
    assert len(client.chat.completions.calls) == 1


def test_env_overrides_existing_environment(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=file-key\nOPENAI_MODEL=file-model\nOPENAI_BASE_URL=http://file/v1\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://environment/v1")
    load_local_environment()
    config = TranslatorConfig.from_env()
    assert config.api_key == "file-key"
    assert config.model == "file-model"
    assert config.base_url == "http://file/v1"


def test_environment_fills_values_missing_from_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=file-key\nOPENAI_MODEL=file-model\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://environment/v1")
    config = TranslatorConfig.from_env()
    assert config.api_key == "file-key"
    assert config.model == "file-model"
    assert config.base_url == "http://environment/v1"


def test_env_local_template_is_not_loaded(tmp_path, monkeypatch):
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=template-key\nOPENAI_MODEL=template-model\n"
    )
    monkeypatch.chdir(tmp_path)
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="create \\.env"):
        TranslatorConfig.from_env()
