async def after_turn(store, profile_id, conversation_id, text, model=None):
    if not profile_id or not text.strip():
        return
    async with _profile_locks[profile_id]:
        now = _now()
        meta = await _load_meta(store, profile_id)
        if not meta:
            meta = {"last_batch_at": now.isoformat(),
                    "last_consolidated_at": now.isoformat(),
                    "changes_since_consolidate": 0}
            await _save_meta(store, profile_id, meta)
        await buffer_message(store, profile_id, conversation_id, text.strip())
        pending = len(await _pending(store, profile_id))
        if not _should_batch(pending, meta, now):
            return
        if not await run_batch(store, profile_id, model):
            return
        meta = await _load_meta(store, profile_id)
        if _should_consolidate(len(await list_memories(store, profile_id, limit=200)),
                               meta, _now()):
            await consolidate(store, profile_id, model)
