"""Unit tests for OpenAI model routing without making network calls."""
from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from app import config
import app.llm as llm


class _Result(BaseModel):
    value: str


class _Responses:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def parse(self, **kwargs):
        self.calls.append(("parse", kwargs))
        return SimpleNamespace(output_parsed=_Result(value="structured"))

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return SimpleNamespace(output_text="  free form  ")


def _fake_client(monkeypatch) -> _Responses:
    responses = _Responses()
    monkeypatch.setattr(
        llm, "_openai_client", SimpleNamespace(responses=responses)
    )
    return responses


def test_high_effort_structured_work_uses_sol(monkeypatch):
    responses = _fake_client(monkeypatch)

    result = llm.generate_structured(
        "build a story", _Result, thinking=config.THINK_HIGH, system="system prompt"
    )

    kind, request = responses.calls[0]
    assert result == _Result(value="structured")
    assert kind == "parse"
    assert request["model"] == config.TEXT_MODEL_HARD
    assert request["reasoning"] == {"effort": config.THINK_HIGH}
    assert request["text_format"] is _Result
    assert request["store"] is False
    assert [message["role"] for message in request["input"]] == ["system", "user"]


def test_low_effort_text_work_uses_luna(monkeypatch):
    responses = _fake_client(monkeypatch)

    result = llm.generate_text("label this", thinking=config.THINK_LOW)

    kind, request = responses.calls[0]
    assert result == "free form"
    assert kind == "create"
    assert request["model"] == config.TEXT_MODEL_EASY
    assert request["reasoning"] == {"effort": config.THINK_LOW}
    assert request["store"] is False
    assert [message["role"] for message in request["input"]] == ["user"]
