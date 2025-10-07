# BMAD Agent MCP Tool Integration

## Overview

This document defines the `*mcp-tool` command integration for all BMAD agents, enabling them to use Docker Desktop MCP servers configured in Story 09.1.

## Command Definition

### `*mcp-tool` Command

**Syntax:** `*mcp-tool <server-name> <tool-name> [parameters]`

**Purpose:** Execute Docker Desktop MCP tools from within BMAD agent workflows

**Examples:**
```bash
# Individual Docker servers
*mcp-tool docker-mcp-filesystem read_file path="/project/README.md"
*mcp-tool docker-mcp-git git_status
*mcp-tool docker-mcp-docker docker_ps format="table"
*mcp-tool docker-mcp-puppeteer screenshot url="https://example.com" output="screenshot.png"

# Docker Desktop Gateway (recommended)
*mcp-tool docker-desktop-mcp-gateway read_file path="/project/README.md"
*mcp-tool docker-desktop-mcp-gateway take_screenshot filename="desktop.png"
*mcp-tool docker-desktop-mcp-gateway build_project
*mcp-tool docker-desktop-mcp-gateway get_transcription url="https://youtube.com/watch?v=example"
```

## Supported MCP Servers

### Docker Desktop Gateway Servers (via docker-desktop-mcp-gateway)

#### 1. context7
**Available Tools:**
- `submit_search` - Submit search queries
- `expand_project_context` - Expand project context

**Parameter Examples:**
```bash
*mcp-tool docker-desktop-mcp-gateway submit_search query="docker configuration"
*mcp-tool docker-desktop-mcp-gateway expand_project_context path="/workspace"
```

#### 2. desktop-commander
**Available Tools:**
- `get_desktop_information` - Get desktop information
- `send_desktop_notification` - Send desktop notification
- `take_screenshot` - Take desktop screenshot
- `get_os_information` - Get operating system info
- `get_active_windows` - Get active windows
- `list_applications` - List installed applications
- `list_running_processes` - List running processes
- `run_command` - Run system command
- `copy_to_clipboard` - Copy text to clipboard
- `get_clipboard_content` - Get clipboard content

**Parameter Examples:**
```bash
*mcp-tool docker-desktop-mcp-gateway get_desktop_information
*mcp-tool docker-desktop-mcp-gateway send_desktop_notification title="Build Complete" message="Your project build has finished"
*mcp-tool docker-desktop-mcp-gateway take_screenshot filename="current-desktop.png"
```

#### 3. filesystem (via gateway)
**Available Tools:** (11 tools total)
- Standard filesystem operations through Docker Desktop gateway

#### 4. jetbrains
**Available Tools:** (30 tools total)
- `create_workspace` - Create new workspace
- `open_workspace` - Open existing workspace  
- `close_workspace` - Close workspace
- `get_workspace_info` - Get workspace information
- `get_project_structure` - Get project structure
- `create_project` - Create new project
- `delete_project` - Delete project
- `run_configuration` - Run project configuration
- `debug_configuration` - Debug project configuration
- `build_project` - Build project
- `clean_project` - Clean project
- `find_in_files` - Find text in files
- `replace_in_files` - Replace text in files
- `format_code` - Format source code
- `optimize_imports` - Optimize imports
- `rename_symbol` - Rename symbol
- `extract_method` - Extract method
- `generate_code` - Generate code
- `analyze_code` - Analyze code
- `get_code_metrics` - Get code metrics
- `run_inspection` - Run code inspection
- `fix_inspection_issues` - Fix inspection issues
- `navigate_to_declaration` - Navigate to declaration
- `navigate_to_implementation` - Navigate to implementation
- `find_usages` - Find symbol usages
- `show_documentation` - Show documentation
- `get_version_control_status` - Get VCS status
- `commit_changes` - Commit changes
- `push_changes` - Push changes
- `pull_changes` - Pull changes
- `create_branch` - Create branch
- `merge_branch` - Merge branch

**Parameter Examples:**
```bash
*mcp-tool docker-desktop-mcp-gateway create_workspace name="MyProject" path="/workspace/myproject"
*mcp-tool docker-desktop-mcp-gateway build_project
*mcp-tool docker-desktop-mcp-gateway analyze_code file="src/main.ts"
*mcp-tool docker-desktop-mcp-gateway find_in_files pattern="TODO" scope="project"
```

#### 5. youtube_transcript
**Available Tools:**
- `get_transcription` - Get video transcription
- `list_transcripts` - List available transcripts
- `search_transcripts` - Search transcripts

**Parameter Examples:**
```bash
*mcp-tool docker-desktop-mcp-gateway get_transcription url="https://youtube.com/watch?v=example"
*mcp-tool docker-desktop-mcp-gateway search_transcripts query="docker tutorial"
```

### Individual Docker Hub Servers

#### 1. docker-mcp-filesystem
**Available Tools:**
- `read_file` - Read file contents
- `write_file` - Write file contents  
- `list_directory` - List directory contents
- `create_directory` - Create new directory

**Parameter Examples:**
```bash
*mcp-tool docker-mcp-filesystem read_file path="/workspace/package.json"
*mcp-tool docker-mcp-filesystem write_file path="/workspace/newfile.txt" content="Hello World"
*mcp-tool docker-mcp-filesystem list_directory path="/workspace"
*mcp-tool docker-mcp-filesystem create_directory path="/workspace/new-folder"
```

### 2. docker-mcp-git
**Available Tools:**
- `git_status` - Show repository status
- `git_log` - Show commit history
- `git_diff` - Show changes
- `git_add` - Stage changes
- `git_commit` - Create commit
- `git_push` - Push changes
- `git_clone` - Clone repository
- `git_branch` - Branch operations

**Parameter Examples:**
```bash
*mcp-tool docker-mcp-git git_status
*mcp-tool docker-mcp-git git_log limit="5"
*mcp-tool docker-mcp-git git_diff file="src/index.ts"
*mcp-tool docker-mcp-git git_add files="."
*mcp-tool docker-mcp-git git_commit message="Implement MCP integration"
```

### 3. docker-mcp-docker
**Available Tools:**
- `docker_ps` - List containers
- `docker_run` - Run container
- `docker_stop` - Stop container
- `docker_rm` - Remove container
- `docker_images` - List images
- `docker_pull` - Pull image
- `docker_build` - Build image
- `docker_exec` - Execute command in container
- `docker_logs` - Show container logs
- `docker_compose_up` - Start compose services
- `docker_compose_down` - Stop compose services

**Parameter Examples:**
```bash
*mcp-tool docker-mcp-docker docker_ps format="table"
*mcp-tool docker-mcp-docker docker_run image="nginx" ports="8080:80"
*mcp-tool docker-mcp-docker docker_logs container="myapp"
*mcp-tool docker-mcp-docker docker_compose_up file="docker-compose.yml"
```

### 4. docker-mcp-puppeteer
**Available Tools:**
- `screenshot` - Take webpage screenshot
- `navigate_to` - Navigate to URL
- `click_element` - Click element
- `type_text` - Type text into element
- `extract_text` - Extract text from page
- `evaluate_javascript` - Execute JavaScript
- `get_page_title` - Get page title
- `get_current_url` - Get current URL

**Parameter Examples:**
```bash
*mcp-tool docker-mcp-puppeteer screenshot url="https://example.com" output="page.png"
*mcp-tool docker-mcp-puppeteer navigate_to url="https://github.com"
*mcp-tool docker-mcp-puppeteer extract_text selector="h1"
*mcp-tool docker-mcp-puppeteer get_page_title
```

## Command Implementation

### Agent Command Integration

All BMAD agents should add the `*mcp-tool` command to their command registry:

```yaml
commands:
  - help: Show numbered list of commands
  - mcp-tool: Execute Docker MCP tools with syntax: *mcp-tool <server> <tool> [params]
  - exit: Exit agent mode
```

### Command Processing Logic

1. **Parse Command**: Extract server name, tool name, and parameters
2. **Validate Server**: Verify server exists in `.crush.json` configuration
3. **Route Request**: 
   - For `docker-desktop-mcp-gateway`: Send via SSE to Docker Desktop gateway
   - For individual servers: Run Docker container with specified tool
4. **Execute Tool**: Process request through appropriate transport mechanism
5. **Format Results**: Return structured output for agent workflow consumption
6. **Handle Errors**: Provide clear error messages with troubleshooting guidance

### Error Handling

**Common Error Scenarios:**
- Docker Desktop not running
- MCP server not configured
- Tool not found
- Invalid parameters
- Container execution failure

**Error Response Format:**
```json
{
  "success": false,
  "error": "Docker Desktop is not running",
  "troubleshooting": "Please start Docker Desktop and try again",
  "server": "docker-mcp-filesystem",
  "tool": "read_file"
}
```

## Agent Workflow Integration

### Usage in Agent Tasks

Agents can use MCP tools within their task execution:

```markdown
## Task: Analyze Project Structure

1. List project files: `*mcp-tool docker-mcp-filesystem list_directory path="/workspace"`
2. Check git status: `*mcp-tool docker-mcp-git git_status`
3. Review package.json: `*mcp-tool docker-mcp-filesystem read_file path="/workspace/package.json"`
4. Generate report based on findings
```

### Result Processing

MCP tool results should be formatted for agent consumption:

```json
{
  "success": true,
  "server": "docker-mcp-filesystem",
  "tool": "read_file",
  "result": {
    "path": "/workspace/README.md",
    "content": "# Project README\n\nThis project...",
    "size": 1024,
    "encoding": "utf-8"
  },
  "timestamp": "2025-09-05T12:00:00Z"
}
```

## Help Documentation

### Command Help Output

When agents execute `*help`, include MCP tool documentation:

```
Available Commands:
1. help - Show this help message
2. mcp-tool - Execute Docker MCP tools
   Usage: *mcp-tool <server> <tool> [parameters]
   Servers: docker-mcp-filesystem, docker-mcp-git, docker-mcp-docker, docker-mcp-puppeteer
   Example: *mcp-tool docker-mcp-git git_status
3. exit - Exit agent mode
```

### MCP Tool Help

Specific MCP tool help:

```bash
*mcp-tool help                              # Show all available servers and tools
*mcp-tool docker-mcp-filesystem help        # Show filesystem tools
*mcp-tool docker-mcp-git git_status help    # Show specific tool parameters
```

## Implementation Notes

### Configuration Dependency

- Requires Story 09.1 `.crush.json` configuration
- Uses Docker MCP servers defined in configuration
- Inherits permissions and validation from Crush configuration

### Security Considerations

- All MCP tools run in isolated Docker containers
- No persistent container state
- Workspace mounting limited to current project directory
- Docker socket access only for docker-mcp-docker server

### Performance Considerations

- Container startup overhead (~1-2 seconds per tool execution)
- Results cached within agent session where appropriate
- Batch operations recommended for multiple file operations

## Testing and Validation

### Unit Tests
- Command parsing and validation
- Parameter processing and formatting
- Error handling scenarios

### Integration Tests
- End-to-end agent MCP tool workflows
- Docker container execution validation
- Result formatting and error handling

### Acceptance Criteria
- All BMAD agents support `*mcp-tool` command
- All Docker Hub MCP tools accessible through command
- Proper error handling and user guidance
- Help documentation complete and accurate

---

**Implementation Status:** Ready for integration into BMAD agent system
**Dependencies:** Story 09.1 Docker MCP configuration complete
**Integration Point:** Add to all BMAD agent command definitions