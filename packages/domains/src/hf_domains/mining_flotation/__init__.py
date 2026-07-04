"""Доменный адаптер «mining_flotation» (ТЗ §6.4).

Перенос прототипа хакатона: чтение отчётов «Хвосты *.xlsx», диагностика
сигналов потерь Ni/Cu, каталог практик и правила обогащения, rule-based
генерация с LLM-усилением, легаси-формула ранжирования, трассировка гипотезы
до ячеек отчёта. Это ОДИН доменный кейс платформы, а не логика ядра.
"""
from hf_domains.mining_flotation.adapter import MiningFlotationAdapter

__all__ = ["MiningFlotationAdapter"]
