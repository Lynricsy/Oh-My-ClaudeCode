# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oh-My-ClaudeCode (OMCC) is a unified MCP server that enables multi-agent collaboration between Claude (Opus) as the architect and specialized agents (Coder, Reviewer, Advisor, Frontend, Chore, Librarian, Looker) for code execution, review, and expert consultation.

**Core Architecture**: Claude orchestrates specialized agents through a FastMCP-based server, with session persistence (SESSION_ID) for multi-turn collaboration and structured error handling for automated retry decisions.

## Development Commands

### Setup & Installation
```bash
# Development setup
uv sync

# Run MCP server directly
uv run omcc-mcp

# Install as MCP server (user scope)
claude mcp add omcc -s user --transport stdio -- \
  uvx --refresh --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp

# Update installation (skip interactive config)
./setup.sh --update

# Uninstall
claude mcp remove omcc -s user
```

### Testing
```bash
# Currently no formal test suite exists
# Manual testing via Claude Code CLI with test prompts is the primary validation method
```

## Architecture

### Three-Layer Configuration System

| Layer | Purpose | Priority |
|-------|---------|----------|
| **MCP Tools** | Type-safe tool implementations with error handling, retry logic | Required |
| **Skills** | Workflow guidance (when/how to use tools) via `/skill` commands | Recommended |
| **Global Prompt** | Enforces collaboration protocol rules | Recommended |

### Tool System (7 Specialized Agents)

| Tool | Backend | Sandbox | Retry | Purpose |
|------|---------|---------|-------|---------|
| `coder` | Claude CLI + Configurable | workspace-write | 0 | Code generation/modification |
| `reviewer` | Codex CLI (OpenAI) | read-only | 1 | Independent code review |
| `advisor` | OpenCode CLI | workspace-write | 1 | Architecture/second opinion |
| `frontend` | OpenCode CLI | workspace-write | 1 | UI/UX development |
| `chore` | OpenCode CLI | workspace-write | 0 | Batch operations |
| `librarian` | OpenCode CLI | read-only | 1 | Web research (docs/search/GitHub) |
| `looker` | Gemini API | read-only | 1 | Multimodal analysis (PDF/images/video/audio) |

**Key Implementation Details**:
- Tools are implemented in `src/omcc_mcp/tools/` (each ~800-1000 LOC)
- All tools support `SESSION_ID` for context persistence across multiple calls
- Structured error responses include `error_kind` (8+ types like `idle_timeout`, `upstream_error`) and `error_detail` with last output lines
- `return_metrics` flag provides observability (duration, prompt size)

### Configuration

Config file: `~/.omcc-mcp/config.toml`

**Coder (Required)**:
```toml
[coder]
api_token = "your-token"
base_url = "https://open.bigmodel.cn/api/anthropic"  # Must support Claude Code API
model = "glm-4.7"
extended_context = false  # Add [1m] suffix for 1M context window

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
```

**OpenCode Agents** (model format: `provider/model`):
```toml
[advisor]
model = "google/advisor-3-pro-preview"

[frontend]
model = "google/advisor-3-pro-preview"

[librarian]
model = "google/advisor-3-flash-preview"

[looker]
api_key = "your-gemini-api-key"  # Required for Looker
base_url = "https://generativelanguage.googleapis.com"  # Optional
model = "gemini-3-flash-preview"  # Optional

[chore]
model = "anthropic/claude-sonnet-4-20250514"
```

Environment variables (Coder only): `CODER_API_TOKEN`, `CODER_BASE_URL`, `CODER_MODEL`

### Skills Installation

Skills provide workflow guidance and must be installed separately:
```bash
# macOS/Linux
mkdir -p ~/.claude/skills
cp -r skills/* ~/.claude/skills/

# Windows (PowerShell)
xcopy /E /I "skills\*" "$env:USERPROFILE\.claude\skills\"
```

Skills available:
- `/omcc-workflow` - Coder/Reviewer collaboration best practices
- `/advisor-collaboration` - Advisor usage guidance
- `/frontend` - UI/UX development patterns
- `/chore` - Batch task execution
- `/librarian` - Web research strategies
- `/looker` - Multimodal analysis workflows

## Code Structure

```
src/omcc_mcp/
├── server.py (557 lines)      # FastMCP server, tool registration
├── config.py (184 lines)      # TOML config + env var loading
├── cli.py (13 lines)          # Entry point
└── tools/                     # Tool implementations (6,109 lines total)
    ├── coder.py (943 lines)   # Subprocess spawn with env injection
    ├── reviewer.py (994 lines) # Codex CLI wrapper
    ├── advisor.py (780 lines) # OpenCode CLI wrapper
    ├── frontend.py (863 lines)
    ├── chore.py (766 lines)
    ├── librarian.py (939 lines)
    └── looker.py (813 lines)
```

**Implementation Patterns**:
- All tools use async subprocess (`asyncio.create_subprocess_exec`)
- Timeout enforcement via `asyncio.wait_for` with idle detection
- Structured logging to stderr (JSONL format when `log_metrics=True`)
- Cross-platform env injection (no shell scripts needed)

## Key Technical Decisions

1. **Session Persistence**: SESSION_ID must be stored and reused per role - IDs are role-specific and returned by MCP responses
2. **Retry Strategy**: Only read-only tools retry by default (Coder/Chore don't due to write side effects)
3. **Subprocess Approach**: Direct `subprocess.Popen(env=custom_env)` instead of shell scripts for cross-platform compatibility
4. **Command Line Strategy**:
   - System prompts via `--append-system-prompt` CLI arg
   - User prompts via stdin (supports newlines, no length limit)
   - `--setting-sources "project"` for project-only config

## Development Guidelines

### Adding a New Tool

1. Create `src/omcc_mcp/tools/new_tool.py` following the pattern:
   ```python
   async def new_tool_handler(...) -> Dict[str, Any]:
       # Subprocess spawn
       # Timeout enforcement
       # Error handling with structured response
       return {"success": bool, "SESSION_ID": str, ...}
   ```

2. Register in `server.py`:
   ```python
   from omcc_mcp.tools.new_tool import new_tool_handler

   @mcp.tool(name="new_tool", description="...")
   async def new_tool(...):
       return await new_tool_handler(...)
   ```

3. Add config section to `config.example.toml`

4. Create skill guide in `skills/new-tool/skill.md`

### Code Quality Requirements

- Type annotations required (Pydantic models for complex types)
- Async/await for all IO operations
- Structured error returns (never raise exceptions to MCP layer)
- Cross-platform path handling (use `pathlib.Path`)

## Common Workflows

### Testing MCP Tools
```bash
# 1. Start MCP server in dev mode
uv run omcc-mcp

# 2. Test via Claude Code with test prompts
# Example: "Use coder to add a hello world function"
```

### Debugging Configuration Issues
```bash
# Check config file exists and is valid TOML
cat ~/.omcc-mcp/config.toml

# Verify MCP connection
claude mcp list
# Should show: omcc: ... - ✓ Connected

# Check stderr logs for error details (when log_metrics=True)
```

### Updating Documentation
- `README.md` (Chinese) - User-facing documentation
- `README_EN.md` - English translation
- `CLAUDE.md` (this file) - Developer guidance
- `templates/omcc-global-prompt.md` - Global prompt template for users

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp[cli]` | ≥1.20.0 | FastMCP framework |
| `pydantic` | ≥2.0 | Data validation |
| Python | ≥3.12 | Runtime requirement |

External CLI tools (installed separately):
- Claude Code CLI (`claude`) - For Coder tool
- Codex CLI (`codex`) - For Reviewer tool
- OpenCode CLI (`opencode`) - For Advisor/Frontend/Chore/Librarian

## Project History

- 2026-01-01: Project created
- 2026-01-03: Renamed to OMCC
- 2026-01-16: Renamed to Oh-My-ClaudeCode
- Current: M5 milestone complete (production-ready)
