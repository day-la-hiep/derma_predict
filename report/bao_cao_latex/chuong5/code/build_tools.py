def build_tools() -> list[Any]:
    tools: list[Any] = [hybrid_retrieval, semantic_search,
                        keyword_search, knowledge_graph_query,
                        query_document_graph]
    if settings.AGENT_FINALIZE_REPORT_SEARCH_ENABLED:
        tools.append(search_finalize_report)
    return tools
