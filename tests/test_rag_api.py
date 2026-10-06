from fastapi.testclient import TestClient

from repocare.multi_agent_demo import app


def test_local_knowledge_endpoint_returns_read_only_source_labelled_results() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/knowledge/search",
        json={"query": "同一网页条目重复提交", "top_k": 3},
    )

    assert response.status_code == 200
    results = response.json()
    assert results
    assert results[0]["source_path"].startswith("knowledge_base/")
    assert "content" in results[0]
