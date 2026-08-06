import asyncio
import json

from dq_core.store.sqlite_store import ResultStore
from services.api.sse import make_progress_callback, sse_generator


def test_operation_streams_progress_and_terminal_payload(tmp_path):
    db = tmp_path / "shared.db"
    worker = ResultStore(db)
    consumer = ResultStore(db)

    assert worker.begin_operation("op-1", "connection_test", created_by="user-1") is True
    emit = make_progress_callback("op-1", worker)
    emit("Verbinde mit Environment \"prod\" ...")
    emit("Schema \"CORE\" pruefen ...")
    worker.finish_operation(
        "op-1",
        "finished",
        result_json=json.dumps({"ok": True, "schema_visible": True}),
    )

    async def drain() -> list[dict]:
        events = []
        async for chunk in sse_generator(consumer, "op-1"):
            if chunk.startswith("data: "):
                events.append(json.loads(chunk[len("data: "):].strip()))
        return events

    events = asyncio.run(asyncio.wait_for(drain(), timeout=5))
    assert [e["line"] for e in events if e["type"] == "progress"] == [
        "Verbinde mit Environment \"prod\" ...",
        "Schema \"CORE\" pruefen ...",
    ]
    finished = [e for e in events if e["type"] == "finished"]
    assert finished
    assert finished[0]["op_id"] == "op-1"
    assert finished[0]["result"]["ok"] is True


def test_operation_polling_data_visible_across_store_instances(tmp_path):
    db = tmp_path / "shared.db"
    worker = ResultStore(db)
    consumer = ResultStore(db)

    assert worker.begin_operation("op-1", "connection_test", created_by="user-1") is True
    assert worker.begin_operation("op-1", "connection_test", created_by="user-1") is False
    first_id = worker.append_progress("op-1", "first")
    worker.append_progress("op-1", "second")
    worker.finish_operation("op-1", "finished", result_json=json.dumps({"ok": False}))

    operation = consumer.get_operation("op-1")
    assert operation["state"] == "finished"
    assert json.loads(operation["result_json"]) == {"ok": False}
    assert [row["line"] for row in consumer.get_progress("op-1")] == ["first", "second"]
    assert [row["line"] for row in consumer.get_progress("op-1", after_id=first_id)] == ["second"]
