from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BATCH_MARKER_RE = re.compile(r"(?m)^\[\[PAPER2DOC:([^\]\r\n]+)\]\]\s*$")


def load_local_environment(start: str | Path | None = None) -> str | None:
    """Load the nearest .env, allowing file values to override the environment."""
    start_path = Path(start).expanduser() if start is not None else Path.cwd()
    directory = start_path if start_path.is_dir() else start_path.parent

    for parent in (directory, *directory.parents):
        candidate = parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=True)
            return str(candidate)
    return None


@dataclass(frozen=True)
class TranslatorConfig:
    api_key: str
    model: str
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> "TranslatorConfig":
        load_local_environment()
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured; create .env or set the environment variable")
        if not model:
            raise RuntimeError("OPENAI_MODEL is not configured; create .env or set the environment variable")
        return cls(api_key=api_key, model=model, base_url=os.getenv("OPENAI_BASE_URL") or None)


class Translator:
    def __init__(self, config: TranslatorConfig | None = None, client=None):
        self.config = config or TranslatorConfig.from_env()
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("The openai package is required for translation") from exc
            options = {"api_key": self.config.api_key}
            if self.config.base_url:
                options["base_url"] = self.config.base_url
            client = OpenAI(**options)
        self.client = client

    def translate(self, text: str) -> str:
        response = self._complete(
            [
                {
                    "role": "system",
                    "content": "你是学术论文翻译助手。将英文准确翻译为中文，保留公式、变量名、引用编号和专业术语。只返回中文译文，不添加解释。",
                },
                {"role": "user", "content": text},
            ]
        )
        return response

    def translate_batch(self, units: list[tuple[str, str]]) -> dict[str, str]:
        """Translate one marked batch and return translations keyed by unit ID."""
        if not units:
            return {}
        prompt = "\n\n".join(
            f"[[PAPER2DOC:{unit_id}]]\n{text}" for unit_id, text in units
        )
        response = self._complete(
            [
                {
                    "role": "system",
                    "content": (
                        "你是学术论文翻译助手。逐段将英文准确翻译为中文，保留公式、变量名、引用编号和专业术语。"
                        "必须原样保留每个 [[PAPER2DOC:id]] 标记，并为每个标记返回一段中文译文。"
                        "每个标记只能出现一次，不要合并、遗漏或新增标记，不添加解释。"
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        return self._parse_batch_response(response, {unit_id for unit_id, _text in units})

    def _complete(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            temperature=0,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("Translation API returned an empty response")
        return content.strip()

    @staticmethod
    def _parse_batch_response(content: str, expected_ids: set[str]) -> dict[str, str]:
        matches = list(BATCH_MARKER_RE.finditer(content))
        if not matches:
            raise RuntimeError("Batch translation response did not contain paragraph markers")
        translations: dict[str, str] = {}
        for index, match in enumerate(matches):
            unit_id = match.group(1)
            if unit_id not in expected_ids:
                raise RuntimeError(f"Batch translation returned an unknown paragraph marker: {unit_id}")
            if unit_id in translations:
                raise RuntimeError(f"Batch translation returned a duplicate paragraph marker: {unit_id}")
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            translation = content[match.end():end].strip()
            if not translation:
                raise RuntimeError(f"Batch translation returned empty text for paragraph marker: {unit_id}")
            translations[unit_id] = translation
        missing_ids = expected_ids - translations.keys()
        if missing_ids:
            missing = ", ".join(sorted(missing_ids))
            raise RuntimeError(f"Batch translation omitted paragraph markers: {missing}")
        return translations
