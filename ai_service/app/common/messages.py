from langchain.messages import AIMessage, AnyMessage, HumanMessage


def message_text(message: AnyMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def get_dialogue_history(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Chỉ lời người dùng và câu trả lời dạng chữ của các lượt trước; kết quả tool của lượt này đi vào prompt qua `evidence`."""
    return [
        m
        for m in messages
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and not m.tool_calls and m.text.strip())
    ]
