from __future__ import annotations

import httpx


async def test_list_models(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) >= 5

        first = data["models"][0]
        assert set(first.keys()) == {"id", "display_name", "provider"}

        ids = {m["id"] for m in data["models"]}
        assert "gpt-4o-mini" in ids
        assert "gemini-2.5-pro" in ids
        assert "claude-opus-4-5" in ids
