# Architecture

## System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GEN SDK TOOLING                                 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────────┐                                                   │
│  │ RST Docs        │  opentelekomcloud-docs repositories               │
│  │ (GitHub)        │                                                   │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │              RST PARSER (docutils/sphinx)                        │  │
│  │  - Extract sections: Function, URI, Request, Response            │  │
│  │  - Parse tables → structured data                                │  │
│  │  - Handle OpenStack API sections (ECS, EVS, VPC)                 │  │
│  └────────────────────┬────────────────────────────────────────────┘  │
│                       │                                                │
│                       ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │              MCP + RAG LAYER                                     │  │
│  │                                                                  │  │
│  │  MCP Server:                                                     │  │
│  │  - @tool parse_rst_endpoint()                                    │  │
│  │  - @tool clarify_type() ← LLM Sampling                           │  │
│  │  - Progress notifications via ctx.notify()                       │  │
│  │                                                                  │  │
│  │  RAG:                                                            │  │
│  │  - Vector index of existing otcextensions code                   │  │
│  │  - Semantic search for similar patterns                          │  │
│  └────────────────────┬────────────────────────────────────────────┘  │
│                       │                                                │
│                       ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │           INTERMEDIATE API MODEL (IR)                            │  │
│  │                                                                  │  │
│  │  ServiceModel → ResourceModel → PropertyModel                    │  │
│  │  + version (v1/v2/v3)                                            │  │
│  │  + source (otc/openstack)                                        │  │
│  │  + is_async (job polling)                                        │  │
│  └────────────────────┬────────────────────────────────────────────┘  │
│                       │                                                │
│                       ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │         CODE GENERATOR (Python + Jinja2)                         │  │
│  │                                                                  │  │
│  │  Templates:                                                      │  │
│  │  - resource.py.j2 → Resource classes                             │  │
│  │  - proxy.py.j2 → Proxy classes                                   │  │
│  │  - cli_command.py.j2 → CLI commands with --wait                  │  │
│  └────────────────────┬────────────────────────────────────────────┘  │
│                       │                                                │
│                       ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │           GENERATED SDK (otcextensions-compatible)               │  │
│  │                                                                  │  │
│  │  otcextensions/sdk/new_service/v1/                               │  │
│  │  ├── _proxy.py                                                   │  │
│  │  ├── resource1.py                                                │  │
│  │  └── resource2.py                                                │  │
│  │                                                                  │  │
│  │  otcextensions/osclient/new_service/v1/                          │  │
│  │  └── resource1.py  # CLI commands                                │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Tools | Notes |
|-------|-------|-------|
| MCP | modelcontextprotocol, FastMCP | Python SDK with decorators |
| GitHub | PyGithub, GitHub API | Service discovery and PR creation |
| Parsing | docutils, sphinx | RST → structured data |
| IR | pydantic, dataclasses | Intermediate model |
| Diff | custom engine, deepdiff | Version-aware diffing |
| RAG | FAISS/Qdrant + embeddings | Pattern matching |
| LLM | Llama 3.3 or Qwen2.5 | Only for ambiguities |
| Templates | Jinja2 | Python-native, powerful |

---

## Intermediate Representation (IR)

```python
@dataclass
class ServiceModel:
    name: str
    version: str  # v1, v2, v3
    source: str  # "otc" or "openstack"
    resources: List[ResourceModel]


@dataclass
class ResourceModel:
    name: str
    base_path: str
    resource_key: str
    resources_key: str
    properties: List[PropertyModel]
    allowed_operations: Set[str]  # create, fetch, delete, list, commit
    is_async: bool  # requires job polling


@dataclass
class PropertyModel:
    name: str
    json_path: str
    type: str
    mandatory: bool
    description: str
    sub_properties: List["PropertyModel"] = None  # Для вложенных структур
    is_list: bool = False
```

---

## Implementation Phases

| Phase | Components | Priority |
|-------|-----------|----------|
| 1     | RST Parser (docutils) with OpenStack section support | High |
| 2     | Intermediate Model (dataclasses) with version and source | High |
| 2.5   | IR Validation & Consistency Check | High |
| 3     | Jinja2 Code Generator | High |
| 4     | MCP Server integration with progress notifications | Medium |
| 5     | RAG for pattern matching | Medium |
| 6     | LLM Sampling for type inference | Medium |
| 7     | CLI generation with --wait support | Medium |

---

## Open Questions

1. **Storage:** Where to store IR snapshots?
   - Option: MCP Memory server pattern (knowledge graph / key-value)
   - Option: Git-based storage
   - **Answer:** Git-based storage (JSON/YAML) in a dedicated api-ir branch for versioning and auditing.

2. **Target SDK:** python-otcextensions or new SDK from scratch?
   - Most likely otcextensions — need to generate compatible code

3. **CLI generation:** Included in scope or deferred?
   - Research shows: need `--wait` support for async operations
   - Included in scope for Phase 7. Must support --wait for all resources where is_async: true.