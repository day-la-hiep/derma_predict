import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from langgraph.store.memory import InMemoryStore

from agent.middleware.common.model import load_memory
from agent.tools import memory as mem
from agent.tools.memory import (
    ConsolidatedMemory,
    MemoryOp,
    MemoryOps,
    after_turn,
    apply_ops,
    buffer_message,
    consolidate,
    list_memories,
    run_batch,
)
from app.config.settings import settings


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeStructured:
    def __init__(self, results: list[Any]) -> None:
        self.results = results
        self.calls = 0
        self.last_human = ""

    async def ainvoke(self, messages: Any) -> Any:
        self.calls += 1
        self.last_human = str(messages[-1].content)
        result = self.results[min(self.calls - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


class FakeModel:
    def __init__(self, structured: FakeStructured) -> None:
        self.structured = structured

    def with_structured_output(self, *_args: Any, **_kwargs: Any) -> FakeStructured:
        return self.structured


def fake_llm(*results: Any) -> tuple[Any, FakeStructured]:
    structured = FakeStructured(list(results))
    return patch("agent.tools.memory.get_model", return_value=FakeModel(structured)), structured


async def seed(store: InMemoryStore, profile: str, *contents: str) -> None:
    for i, c in enumerate(contents):
        await store.aput((profile, mem.MEMORY), f"k{i}", {"content": c})
        await asyncio.sleep(0.002)


class ReadTest(unittest.TestCase):
    def test_newest_first_capped_and_scoped_by_profile(self):
        store = InMemoryStore()

        async def scenario() -> tuple[str, str, str]:
            await seed(store, "A", *[f"m{i}" for i in range(15)])
            await seed(store, "B", "của B")
            return await load_memory(store, "A"), await load_memory(store, "B"), await load_memory(store, "C")

        a, b, c = run(scenario())
        lines = a.split("\n")
        self.assertEqual(len(lines), mem.MAX_INJECTED)
        self.assertEqual(lines[0], "- m14")
        self.assertEqual(b, "- của B")
        self.assertEqual(c, "")

    def test_store_error_gives_empty(self):
        class Broken(InMemoryStore):
            async def asearch(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("down")

        self.assertEqual(run(load_memory(Broken(), "A")), "")


class ApplyOpsTest(unittest.TestCase):
    def test_add_update_skip_and_unknown_label(self):
        store = InMemoryStore()

        async def scenario() -> tuple[int, list[str]]:
            await seed(store, "A", "đang mang thai", "dị ứng penicillin")
            existing = await list_memories(store, "A")  # mới nhất trước: M1 = dị ứng, M2 = mang thai
            n = await apply_ops(
                store,
                "A",
                existing,
                [
                    MemoryOp(action="update", target_key="m2", content="đã sinh"),
                    MemoryOp(action="add", content="hen suyễn"),
                    MemoryOp(action="skip", content="không ghi"),
                    MemoryOp(action="update", target_key="M9", content="thuốc X"),
                    MemoryOp(action="add", content="   "),
                ],
            )
            return n, [c for _, c in await list_memories(store, "A")]

        n, contents = run(scenario())
        self.assertEqual(n, 3)
        self.assertNotIn("đang mang thai", contents)
        self.assertEqual(sorted(contents), sorted(["đã sinh", "dị ứng penicillin", "hen suyễn", "thuốc X"]))


class BatchTest(unittest.TestCase):
    def test_batch_reconciles_all_buffered_messages_in_one_call(self):
        store = InMemoryStore()
        patcher, structured = fake_llm(MemoryOps(ops=[MemoryOp(action="add", content="dị ứng penicillin")]))

        async def scenario() -> tuple[bool, list[str], int]:
            await buffer_message(store, "A", "c1", "tôi dị ứng penicillin")
            await buffer_message(store, "A", "c2", "ngứa 3 ngày nay")
            ok = await run_batch(store, "A")
            return ok, [c for _, c in await list_memories(store, "A")], len(await mem._pending(store, "A"))

        with patcher:
            ok, contents, pending = run(scenario())
        self.assertTrue(ok)
        self.assertEqual((contents, pending, structured.calls), (["dị ứng penicillin"], 0, 1))
        self.assertIn("tôi dị ứng penicillin", structured.last_human)
        self.assertIn("ngứa 3 ngày nay", structured.last_human)

    def test_llm_failure_keeps_buffer(self):
        store = InMemoryStore()
        patcher, structured = fake_llm(RuntimeError("down"))

        async def scenario() -> tuple[bool, int]:
            await buffer_message(store, "A", "c1", "tôi dị ứng penicillin")
            return await run_batch(store, "A"), len(await mem._pending(store, "A"))

        with patcher:
            ok, pending = run(scenario())
        self.assertEqual((ok, pending, structured.calls), (False, 1, 2))


class AfterTurnTest(unittest.TestCase):
    def _run(self, texts: list[str], *, interval: int, max_pending: int, llm: Any) -> tuple[InMemoryStore, FakeStructured]:
        store = InMemoryStore()
        patcher, structured = fake_llm(llm)

        async def scenario() -> None:
            for t in texts:
                await after_turn(store, "A", "c1", t)

        with patcher, patch.object(settings, "AGENT_MEMORY_BATCH_INTERVAL_MIN", interval), patch.object(settings, "AGENT_MEMORY_BATCH_MAX_PENDING", max_pending):
            run(scenario())
        return store, structured

    def test_buffers_without_llm_before_threshold(self):
        store, structured = self._run(["a", "b", "c"], interval=60, max_pending=20, llm=MemoryOps())
        self.assertEqual(structured.calls, 0)
        self.assertEqual(len(run(mem._pending(store, "A"))), 3)

    def test_batches_when_buffer_full(self):
        store, structured = self._run(["a", "b", "c"], interval=0, max_pending=3, llm=MemoryOps(ops=[MemoryOp(action="add", content="x")]))
        self.assertEqual(structured.calls, 1)
        self.assertEqual(len(run(mem._pending(store, "A"))), 0)
        self.assertEqual([c for _, c in run(list_memories(store, "A"))], ["x"])

    def test_batches_after_interval(self):
        store = InMemoryStore()
        patcher, structured = fake_llm(MemoryOps(ops=[MemoryOp(action="add", content="x")]))

        async def scenario() -> None:
            await after_turn(store, "A", "c1", "một")
            meta = await mem._load_meta(store, "A")
            meta["last_batch_at"] = (datetime.now(UTC) - timedelta(minutes=61)).isoformat()
            await mem._save_meta(store, "A", meta)
            await after_turn(store, "A", "c1", "hai")

        with patcher, patch.object(settings, "AGENT_MEMORY_BATCH_INTERVAL_MIN", 60), patch.object(settings, "AGENT_MEMORY_BATCH_MAX_PENDING", 20):
            run(scenario())
        self.assertEqual(structured.calls, 1)
        self.assertEqual(len(run(mem._pending(store, "A"))), 0)

    def test_ignores_empty_text_and_missing_profile(self):
        store = InMemoryStore()
        run(after_turn(store, "", "c1", "tôi dị ứng"))
        run(after_turn(store, "A", "c1", "   "))
        self.assertEqual(run(mem._pending(store, "A")), [])

    def test_store_error_is_logged_not_raised(self):
        class Broken(InMemoryStore):
            async def aget(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("down")

        with self.assertLogs("agent.tools.memory", level="ERROR"):
            run(after_turn(Broken(), "A", "c1", "tôi dị ứng"))


class ConsolidateTest(unittest.TestCase):
    def test_archives_old_then_replaces(self):
        store = InMemoryStore()
        patcher, _ = fake_llm(ConsolidatedMemory(items=["dị ứng penicillin", "đã sinh"]))

        async def scenario() -> tuple[bool, list[str], list[str]]:
            await seed(store, "A", "dị ứng penicillin", "không dùng được penicillin", "đang mang thai", "đã sinh")
            ok = await consolidate(store, "A")
            archived = await store.asearch(("A", mem.ARCHIVE), limit=50)
            return ok, [c for _, c in await list_memories(store, "A")], sorted(str(i.value["content"]) for i in archived)

        with patcher:
            ok, contents, archived = run(scenario())
        self.assertTrue(ok)
        self.assertEqual(sorted(contents), ["dị ứng penicillin", "đã sinh"])
        self.assertEqual(len(archived), 4)
        self.assertIn("đang mang thai", archived)

    def test_invalid_result_keeps_everything(self):
        for bad in (ConsolidatedMemory(items=[]), ConsolidatedMemory(items=["x"] * 11), RuntimeError("down")):
            store = InMemoryStore()
            patcher, _ = fake_llm(bad)

            async def scenario() -> tuple[bool, list[str], int]:
                await seed(store, "A", "một", "hai")
                ok = await consolidate(store, "A")
                return ok, sorted(c for _, c in await list_memories(store, "A")), len(await store.asearch(("A", mem.ARCHIVE), limit=50))

            with patcher:
                ok, contents, archived = run(scenario())
            self.assertEqual((ok, contents, archived), (False, ["hai", "một"], 0))

    def test_conditions(self):
        now = datetime.now(UTC)
        fresh = {"last_consolidated_at": now.isoformat(), "changes_since_consolidate": 0}
        old_few = {"last_consolidated_at": (now - timedelta(days=8)).isoformat(), "changes_since_consolidate": 2}
        old_many = {"last_consolidated_at": (now - timedelta(days=8)).isoformat(), "changes_since_consolidate": 6}
        with patch.object(settings, "AGENT_MEMORY_CONSOLIDATE_AT", 15), patch.object(settings, "AGENT_MEMORY_CONSOLIDATE_DAYS", 7):
            self.assertTrue(mem._should_consolidate(15, fresh, now))
            self.assertFalse(mem._should_consolidate(14, fresh, now))
            self.assertFalse(mem._should_consolidate(10, old_few, now))
            self.assertTrue(mem._should_consolidate(10, old_many, now))
            self.assertFalse(mem._should_consolidate(1, old_many, now))


if __name__ == "__main__":
    unittest.main()
