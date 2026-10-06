from mcp.server import MCPServer

from repocare.rag_store import KnowledgeSearchInput
from repocare.rag_store import search_local_knowledge as retrieve_local_knowledge
from repocare.tools import SearchCodeInput, ToolResult, search_code

mcp = MCPServer(
    "repocare-tools",
    instructions=(
        "Only use read-only tools. "
        "Never modify files or mark a task resolved."
    ),
)


@mcp.tool()
def search_repo_code(
    query: str,
    relative_root: str = "demo_app",
) -> ToolResult:
    result = search_code(
        SearchCodeInput(
            query=query,
            relative_root=relative_root,
        )
    )
    return result


@mcp.tool()
def search_local_knowledge(query: str, top_k: int = 3) -> ToolResult:
    """Read only curated local Markdown and return source-labelled RAG evidence."""
    results = retrieve_local_knowledge(KnowledgeSearchInput(query=query, top_k=top_k))
    return ToolResult(
        ok=True,
        code="ok",
        message=f"retrieved {len(results)} local knowledge chunks",
        data={"results": [item.model_dump(mode="json") for item in results]},
        duration_ms=0,
    )


if __name__ == "__main__":
    mcp.run()
