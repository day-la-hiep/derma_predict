_QUERY_INSTRUCTION = "Given a Vietnamese or English dermatology question, retrieve relevant textbook passages that answer it"


def embed_query(text: str) -> list[float]:
    # câu hỏi thêm tiền tố chỉ dẫn; đoạn trong kho được mã hóa ở dạng nguyên bản
    return _embed([f"Instruct: {_QUERY_INSTRUCTION}\nQuery: {text}"])[0]


# QdrantVectorClient.search(): truy vấn vector gần nhất theo cosine
async def search(self, name: str, vector: list[float], *, limit: int, query_filter: Filter | None = None,
                 score_threshold: float | None = None) -> list[ScoredPoint]:
    result = await self.client.query_points(name, query=vector, query_filter=query_filter, limit=limit,
                                            score_threshold=score_threshold)
    return result.points
