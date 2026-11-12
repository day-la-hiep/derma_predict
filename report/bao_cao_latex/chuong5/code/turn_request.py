class TurnRequest(BaseModel):
    type: Literal["turn", "resume"]
    conversation_id: str
    message_id: str          # id tin tro ly cua turn
    user_message_id: str | None = None
    corr_id: str | None = None
    content: str | None = None
    attached_files: list[TurnAttachment] | None = None
