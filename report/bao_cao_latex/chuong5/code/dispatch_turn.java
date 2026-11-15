dispatch(new AiClient.TurnRequest("turn", conversationId,
        turn.assistant().id, turn.user().id, input.clientMessageId(),
        input.content(), imagesForAi(attachments)));
