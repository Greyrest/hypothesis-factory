"""Рекомендуемый универсальный словарь графа знаний (ТЗ §9.2–9.3).

Движок графа принимает произвольные строковые типы узлов и рёбер: доменные
адаптеры расширяют словарь своими типами (например, у флотации — stream,
size_class, loss_cell, finding). Ядро использует значения ниже для узлов,
которые создаёт само (цель, ограничения, гипотезы, источники).
"""
from __future__ import annotations

from enum import Enum


class CoreNodeType(str, Enum):
    PROJECT_GOAL = "project_goal"      # целевой KPI
    CONSTRAINT = "constraint"          # ограничение проекта
    ENTITY = "entity"                  # материал / процесс / параметр / свойство
    EXPERIMENT = "experiment"          # эксперимент (исторический или плановый)
    FACT = "fact"                      # извлечённый факт
    PROBLEM = "problem"                # проблема / разрыв / зона улучшения
    MECHANISM = "mechanism"            # физический механизм влияния
    HYPOTHESIS = "hypothesis"          # гипотеза
    SOURCE = "source"                  # статья / патент / отчёт / правило
    RISK = "risk"                      # риск
    VALIDATION_STEP = "validation_step"  # шаг плана проверки


class CoreEdgeType(str, Enum):
    AFFECTS = "affects"                  # фактор влияет на свойство
    IMPROVES = "improves"                # действие улучшает KPI
    WORSENS = "worsens"                  # действие ухудшает показатель
    SUPPORTED_BY = "supported_by"        # гипотеза подтверждается источником/фактом
    CONTRADICTED_BY = "contradicted_by"  # противоречащий источник
    TESTED_IN = "tested_in"              # связь с экспериментом
    REQUIRES = "requires"                # требует ресурс/оборудование/условие
    VIOLATES = "violates"                # нарушает ограничение
    ANALOGOUS_TO = "analogous_to"        # аналогия с известным решением
    VERIFIED_BY = "verified_by"          # проверяется шагом дорожной карты
    ADDRESSED_BY = "addressed_by"        # проблема адресуется гипотезой
    DERIVED_FROM = "derived_from"        # проблема/факт получены из данных
    TARGETS = "targets"                  # гипотеза/проблема относится к KPI
