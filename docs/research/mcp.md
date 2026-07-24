# Research: MCP Server Patterns

Model Context Protocol (MCP) is an open standard for connecting AI models to external tools and data. The official Python SDK provides the **FastMCP** framework for creating servers with minimal boilerplate.

## Official Resources

| Resource | URL |
|----------|-----|
| Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| Documentation | https://modelcontextprotocol.github.io/python-sdk/ |
| Specification | https://modelcontextprotocol.io/specification/latest |
| Example Servers | https://github.com/modelcontextprotocol/servers |
| PyPI | `pip install "mcp[cli]"` |

---

## Tool Definitions

Tools are defined using the `@mcp.tool()` decorator. Input/output schemas are auto-generated from type hints:

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("SDK Generator")


class APIEndpoint(BaseModel):
    method: str = Field(description="HTTP method")
    path: str = Field(description="URL path")
    parameters: list[dict] = Field(description="Request parameters")


@mcp.tool()
def parse_rst_endpoint(rst_content: str) -> APIEndpoint:
    """Parse RST file and extract API endpoint."""
    return APIEndpoint(method="GET", path="/clusters", parameters=[])
```

The SDK automatically generates JSON Schema from type hints:

```json
{
    "name": "parse_rst_endpoint",
    "description": "Parse RST file and extract API endpoint.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "rst_content": {"type": "string"}
        },
        "required": ["rst_content"]
    }
}
```

---

## State Management

MCP uses **lifespan context** for application state management:

```python
from contextlib import asynccontextmanager
from dataclasses import dataclass
from mcp.server.fastmcp import Context, FastMCP


@dataclass
class GeneratorContext:
    """Generator context with cached data."""

    parsed_endpoints: dict
    rag_index: object  # Vector index for RAG


@asynccontextmanager
async def generator_lifespan(server: FastMCP):
    """Initialize resources on server start."""
    ctx = GeneratorContext(parsed_endpoints={}, rag_index=await load_rag_index())
    try:
        yield ctx
    finally:
        await cleanup_resources()


mcp = FastMCP("SDK Generator", lifespan=generator_lifespan)


@mcp.tool()
def generate_sdk(service_name: str, ctx: Context) -> str:
    """Use state for SDK generation."""
    lifespan_ctx = ctx.request_context.lifespan_context
    endpoints = lifespan_ctx.parsed_endpoints.get(service_name)
    return generate_code(endpoints)
```

---

## LLM Integration via Sampling

MCP allows the server to request LLM completions from the client to resolve ambiguities:

```python
from mcp.types import SamplingMessage, TextContent


@mcp.tool()
async def clarify_parameter_type(parameter_desc: str, ctx: Context) -> str:
    """Use LLM to determine parameter type."""
    prompt = f"Determine Python type for parameter: {parameter_desc}"

    result = await ctx.session.create_message(
        messages=[
            SamplingMessage(role="user", content=TextContent(type="text", text=prompt))
        ],
        max_tokens=50,
    )
    return result.content.text  # "str", "int", "List[dict]", etc.
```

---

## Progress Notifications

For long-running operations (e.g., `build_api_ir`, `ingest_api_docs`), the protocol supports progress notifications:

```python
@mcp.tool()
async def ingest_api_docs(ref: str, ctx: Context) -> dict:
    """Load documentation with progress reporting."""
    files = await list_rst_files(ref)
    total = len(files)

    for i, file in enumerate(files):
        await process_file(file)
        # Send progress to client
        await ctx.notify("progress", {"current": i + 1, "total": total, "file": file})

    return {"files_ingested": total, "commit": ref}
```

This allows LLM clients to show progress indicators to users.

---

## Memory Server Pattern

For storing IR snapshots, the reference **Memory server** from MCP provides a useful pattern:

> "Memory server uses a knowledge graph for persistent storage of facts added by tools and their subsequent retrieval"

This answers the storage question — we can implement a similar approach with knowledge graph or key-value storage.

**Reference:** https://github.com/modelcontextprotocol/servers (Memory section)

---

## Key Takeaways

- **Tool definitions** use decorators and type hints for automatic schema generation
- **State management** via lifespan context and session state
- **LLM integration** via Sampling for resolving ambiguities
- **Progress notifications** via `ctx.notify()` for long operations
- FastMCP significantly simplifies MCP server creation