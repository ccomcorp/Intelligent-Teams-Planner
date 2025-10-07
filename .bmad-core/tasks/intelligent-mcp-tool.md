# Intelligent MCP Tool Execution

## Task Purpose
Execute MCP tools intelligently based on natural language descriptions, automatically selecting the appropriate server and tool based on intent, context, and current project state.

## Parameters
- **request**: Natural language description of what you want to accomplish
- **context** (optional): Additional context about the current task or project state
- **server_preference** (optional): Preferred server if multiple options are available

## Execution Process

### Step 1: Intent Analysis
Analyze the natural language request to determine:
1. **Primary Intent**: What is the user trying to accomplish?
2. **Tool Category**: Which category of tools is most appropriate?
3. **Context Clues**: Are there project-specific or environment-specific hints?

### Step 2: Server Selection Logic
Based on intent analysis, select the appropriate MCP server:

**File Operations** ("read", "write", "list", "create", "file"):
- → `filesystem-toolkit`

**Git Operations** ("git", "commit", "status", "history", "repository", "version control"):
- → `git-toolkit`

**Docker Operations** ("docker", "container", "image", "build", "containerize"):
- → `docker-toolkit`

**Desktop Operations** ("screenshot", "desktop", "clipboard", "system", "notification"):
- → `desktop-commander`

**Code/IDE Operations** ("analyze", "build", "format", "refactor", "code", "project", "IDE"):
- → `jetbrains`

**Web Search** ("search", "find online", "web", "lookup"):
- → `web-search`

**Video/Transcript** ("youtube", "transcript", "video"):
- → `youtube-transcript`

**Project Context** ("understand project", "project analysis", "codebase"):
- → `context7`

### Step 3: Context Enhancement
Enhance the selection based on current context:
- **Current Directory**: Check for `.git`, `package.json`, `Dockerfile`, etc.
- **File Extensions**: In current context (.ts/.js → jetbrains, .md → filesystem)
- **Recent Commands**: Previous tool usage patterns
- **Task Context**: What the agent is currently working on

### Step 4: Tool Execution
1. **Construct Command**: Build the appropriate `*mcp-tool` command
2. **Execute**: Run the command with proper parameters
3. **Format Results**: Present results in context-appropriate format
4. **Error Handling**: Provide helpful guidance if execution fails

## Smart Routing Examples

### Example 1: File Operations
**Request**: "read the package.json file"
**Analysis**: File operation → filesystem-toolkit
**Command**: `*mcp-tool filesystem-toolkit read_file path="package.json"`

### Example 2: Git Operations  
**Request**: "check repository status"
**Analysis**: Git operation → git-toolkit
**Command**: `*mcp-tool git-toolkit git_status`

### Example 3: Code Analysis
**Request**: "analyze the code quality"
**Analysis**: Code operation + project context → jetbrains
**Command**: `*mcp-tool jetbrains analyze_code`

### Example 4: System Operations
**Request**: "take a screenshot of the desktop"
**Analysis**: Desktop operation → desktop-commander
**Command**: `*mcp-tool desktop-commander take_screenshot filename="desktop-$(date +%Y%m%d-%H%M%S).png"`

### Example 5: Ambiguous Request Resolution
**Request**: "find TODO comments in the project"
**Analysis**: Could be search or code operation
**Context**: Project directory with source files → jetbrains (more specific)
**Command**: `*mcp-tool jetbrains find_in_files pattern="TODO" scope="project"`

## Context-Aware Enhancements

### Project Type Detection
- **Node.js Project** (package.json present): Prefer jetbrains for builds, npm operations
- **Docker Project** (Dockerfile present): Prefer docker-toolkit for container operations
- **Git Repository** (.git present): Enable git-toolkit operations
- **Documentation Project** (mostly .md files): Prefer filesystem-toolkit

### Current Task Context
- **Story Implementation**: Prefer code analysis (jetbrains) and git operations
- **System Administration**: Prefer desktop-commander and docker-toolkit
- **Research Tasks**: Prefer web-search and context7
- **Documentation**: Prefer filesystem-toolkit and web-search

### Error Recovery
If selected tool/server fails:
1. **Try Alternative Server**: If jetbrains fails, try filesystem-toolkit for file ops
2. **Suggest Manual Command**: Provide exact `*mcp-tool` command for user
3. **Context Explanation**: Explain why this server was selected

## Usage in BMAD Agents

Add this capability to agent commands:
```yaml
commands:
  - mcp-tool: Execute MCP tools intelligently with natural language. Usage: *mcp-tool <description>
    Examples: 
    - *mcp-tool read package.json
    - *mcp-tool check git status  
    - *mcp-tool analyze code quality
    - *mcp-tool take screenshot
    - *mcp-tool build the project
```

## Implementation Notes

### Dependencies
- Load: `.bmad-core/data/mcp-tool-capabilities.md` for capability mapping
- Current project context (directory listing, file types)
- Available MCP servers from configuration

### Success Criteria
- Natural language requests correctly map to appropriate servers
- Context awareness improves tool selection accuracy
- Error handling provides helpful guidance
- Execution results are properly formatted

### Fallback Behavior
If intelligent routing fails:
1. Display available servers and their capabilities
2. Ask user to specify server manually
3. Provide example commands for common operations
4. Log the failed request for system improvement