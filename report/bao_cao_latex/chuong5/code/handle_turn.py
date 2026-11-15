async def handle_turn(req: TurnRequest) -> None:
    await _drive(req, {"messages": [HumanMessage(
        content=_human_message_content(req), id=req.user_message_id)]})

async def finish_turn(req, event, *, content, reasoning=None, context=None):
    await emit(req.conversation_id, event)
    await get_redis_client().add_stream_event(
        CONVERSATION_EVENTS_STREAM.format(conversation_id=req.conversation_id),
        STREAM_DONE_SENTINEL)
    if context is not None and (context.turn_facts or context.turn_hypotheses
            or context.turn_images):
        await _save_clinical_result(req, context)
    await get_consultation_client().post_turn_result(
        req.message_id, {"conversation_id": ..., "content": content,
                         "status": "done", "choice": None, "reasoning": ...})
