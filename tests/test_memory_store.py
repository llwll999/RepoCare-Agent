from repocare import memory_store


def test_run_checkpoint_survives_memory_reset(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(memory_store, "DATABASE_PATH", tmp_path / "memory.db")
    payload = {"run_id": "run-001", "state": "WAITING_FOR_APPROVAL"}

    memory_store.save_run_checkpoint("run-001", payload)

    assert memory_store.load_run_checkpoint("run-001") == payload


def test_verified_pattern_is_durable_and_bounded(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(memory_store, "DATABASE_PATH", tmp_path / "memory.db")
    memory_store.remember_verified_pattern(
        scenario="zongce",
        memory_key="duplicate-proof-v1",
        summary="同一网页条目提交必须幂等。",
        tags=["idempotency"],
    )

    recalled = memory_store.recall_verified_patterns("zongce", limit=3)

    assert len(recalled) == 1
    assert recalled[0]["summary"] == "同一网页条目提交必须幂等。"
