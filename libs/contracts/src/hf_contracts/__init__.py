"""Общие контракты «Фабрики гипотез»: формы данных, которыми обмениваются сервисы."""
from .models import (
    Evidence,
    ExpectedEffect,
    Finding,
    Hypothesis,
    PlantResult,
    Scores,
    Summary,
)

__all__ = [
    "Evidence",
    "ExpectedEffect",
    "Finding",
    "Hypothesis",
    "PlantResult",
    "Scores",
    "Summary",
]
