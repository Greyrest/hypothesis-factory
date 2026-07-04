"""hf_domains — доменные адаптеры «Фабрики гипотез» (ТЗ §6).

Вся предметная логика (парсинг форматов, диагностика, правила, шаблоны
гипотез, KPI-метрики, оценки эффекта) живёт в адаптерах. Ядро (backend)
обращается к домену только через интерфейс DomainAdapter.

Адаптер создаётся на один запуск конвейера и может держать внутреннее
состояние между вызовами protocol-методов (parse -> diagnose -> generate).
"""
from __future__ import annotations

from hf_domains.base.adapter import BaseDomainAdapter, DomainAdapter


def _builtin() -> dict[str, type]:
    from hf_domains.materials_science.adapter import MaterialsScienceAdapter
    from hf_domains.mining_flotation.adapter import MiningFlotationAdapter

    return {
        MaterialsScienceAdapter.domain_id: MaterialsScienceAdapter,
        MiningFlotationAdapter.domain_id: MiningFlotationAdapter,
    }


def list_domains() -> list[dict]:
    return [{"domain_id": cls.domain_id, "title": cls.title,
             "supported_formats": list(cls.supported_formats)}
            for cls in _builtin().values()]


def get_adapter(domain_id: str) -> DomainAdapter:
    """Новый экземпляр адаптера домена (на один запуск конвейера)."""
    cls = _builtin().get(domain_id)
    if cls is None:
        raise KeyError(f"неизвестный домен: {domain_id!r}; "
                       f"доступны: {sorted(_builtin())}")
    return cls()


__all__ = ["DomainAdapter", "BaseDomainAdapter", "get_adapter", "list_domains"]
