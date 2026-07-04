"""Интерфейс LLM-провайдера.

Чтобы поменять нейронку, достаточно реализовать этот интерфейс и указать
провайдер/модель через env — остальные сервисы ничего не знают о бэкенде.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def enhance(self, context: dict) -> list[dict] | None:
        """context -> items по HYP_SCHEMA. None => усиление недоступно
        (нет ключа/сети/квоты), конвейер остаётся на rule-based."""

    def translate(self, texts: list[str], lang: str) -> list[str] | None:
        """Перевод на en/zh (мультиязычность из ТЗ). None => недоступно."""
        return None


class NullProvider(LLMProvider):
    """LLM отключён (локальный контур без внешних вызовов)."""
    name = "none"

    def enhance(self, context: dict) -> list[dict] | None:
        return None
