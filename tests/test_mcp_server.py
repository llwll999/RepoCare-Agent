import pytest
from mcp import Client

from repocare.mcp_server import mcp


@pytest.mark.anyio
async def test_mcp_search_returns_structured_result() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_repo_code",
            {"query": "superseded"},
        )

    assert result.structured_content["ok"] is True
    assert "demo_app/models.py" in (
        result.structured_content["data"]["matches"]
    )


@pytest.mark.anyio
async def test_mcp_local_knowledge_search_returns_source_labelled_evidence() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_local_knowledge",
            {"query": "同一网页条目重复提交", "top_k": 3},
        )

    assert result.structured_content["ok"] is True
    evidence = result.structured_content["data"]["results"]
    assert evidence
    assert evidence[0]["source_path"].startswith("knowledge_base/")
