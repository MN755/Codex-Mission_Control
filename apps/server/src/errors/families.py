from __future__ import annotations


ERROR_FAMILY_DESCRIPTIONS: dict[str, str] = {
    "MC-BOOT": "Startup and bootstrap errors.",
    "MC-CONFIG": "Configuration and background-running config errors.",
    "MC-DAEMON": "Daemon lifecycle errors.",
    "MC-MCP": "MCP bridge, tool, resource, and prompt errors.",
    "MC-PLUGIN": "Codex plugin and skill package errors.",
    "MC-RUNNER": "Runner registry and runner invocation errors.",
    "MC-CODEX": "Codex CLI-specific errors.",
    "MC-OLLAMA": "Ollama-specific errors.",
    "MC-CLAUDE": "Claude CLI-specific errors.",
    "MC-API": "API-provider runner errors.",
    "MC-AUTH": "Authentication and credential configuration errors.",
    "MC-SECRET": "Secret detection and redaction errors.",
    "MC-WORKSPACE": "Workspace attach, import, and path errors.",
    "MC-SCAN": "Existing codebase scan and indexing errors.",
    "MC-ORCH": "Orchestration session lifecycle errors.",
    "MC-MANAGER": "Manager AI planning and decision errors.",
    "MC-AGENT": "Worker agent lifecycle and reporting errors.",
    "MC-SUBAGENT": "Codex subagent burst errors.",
    "MC-DECISION": "Pending decision, approval, and question errors.",
    "MC-BRIDGE": "Bridge formatting and chat summary errors.",
    "MC-HANDOFF": "Handoff and evidence errors.",
    "MC-VALIDATION": "Build, test, and validation errors.",
    "MC-SECURITY": "Security policy and permission errors.",
    "MC-DIAGNOSTIC": "Health check and diagnostic report errors.",
    "MC-STORAGE": "SQLite and runtime storage errors.",
    "MC-NETWORK": "Localhost, port, and connectivity errors.",
    "MC-DOCS": "Documentation, skill, and wiki validation errors.",
    "MC-UNKNOWN": "Fallback unknown errors.",
}


def is_known_family(family: str) -> bool:
    return family in ERROR_FAMILY_DESCRIPTIONS
