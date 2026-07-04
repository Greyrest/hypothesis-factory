from __future__ import annotations

import httpx
from fastapi import HTTPException


async def post_json(url: str, path: str, payload: dict, timeout: float = 180.0) -> dict:
    try:
        async with httpx.AsyncClient(base_url=url, timeout=timeout) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise RuntimeError(f"{path}: downstream returned {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{path}: downstream unavailable: {exc}") from exc


async def get_json(url: str, path: str, timeout: float = 30.0) -> dict | list:
    try:
        async with httpx.AsyncClient(base_url=url, timeout=timeout) as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"downstream unavailable: {exc}") from exc

