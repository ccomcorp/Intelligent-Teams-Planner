# MCP Tool Capabilities Database

## Tool Categories and Server Mapping

### File Operations
**Natural Language**: "read file", "write file", "list files", "create directory", "file operations"
**Server**: `filesystem-toolkit`
**Tools**: 
- `read_file` - Read file contents
- `write_file` - Write file contents  
- `list_directory` - List directory contents
- `create_directory` - Create new directory

**Usage Examples**:
- "read package.json" → filesystem-toolkit read_file
- "list source files" → filesystem-toolkit list_directory
- "create docs folder" → filesystem-toolkit create_directory

### Search Operations
**Natural Language**: "search web", "google search", "find information", "search for", "look up"
**Servers**: `brave-search`, `serper-search`
**Tools**:

**Brave Search (`brave-search`)**:
- `search_web` - Web search via Brave API
- `search_images` - Image search
- `search_news` - News search  
- `search_videos` - Video search

**Serper Search (`serper-search`)**:
- `google_search` - Google search via Serper API
- `scrape_webpage` - Webpage content extraction

**Usage Examples**:
- "search for React tutorials" → brave-search search_web
- "find news about AI" → brave-search search_news  
- "google search Python documentation" → serper-search google_search

### Git Operations  
**Natural Language**: "git status", "git commit", "git history", "repository", "version control"
**Server**: `git-toolkit`
**Tools**:
- `git_status` - Show repository status
- `git_log` - Show commit history
- `git_diff` - Show changes
- `git_add` - Stage changes
- `git_commit` - Create commit
- `git_push` - Push changes
- `git_clone` - Clone repository
- `git_branch` - Branch operations

**Usage Examples**:
- "check git status" → git-toolkit git_status
- "show recent commits" → git-toolkit git_log
- "commit changes" → git-toolkit git_commit

### Docker Operations
**Natural Language**: "docker", "container", "image", "docker ps", "docker management"
**Server**: `docker-toolkit`
**Tools**:
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

**Usage Examples**:
- "list containers" → docker-toolkit docker_ps
- "build image" → docker-toolkit docker_build
- "show container logs" → docker-toolkit docker_logs

### Desktop Operations
**Natural Language**: "screenshot", "desktop", "clipboard", "notification", "OS info", "system"
**Server**: `desktop-commander`
**Tools**:
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

**Usage Examples**:
- "take screenshot" → desktop-commander take_screenshot
- "copy to clipboard" → desktop-commander copy_to_clipboard  
- "show running processes" → desktop-commander list_running_processes

### IDE/Code Operations
**Natural Language**: "analyze code", "build project", "format code", "refactor", "IDE", "development"
**Server**: `jetbrains`
**Tools**:
- `create_workspace` - Create new workspace
- `open_workspace` - Open existing workspace  
- `get_project_structure` - Get project structure
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

**Usage Examples**:
- "analyze this code" → jetbrains analyze_code
- "build the project" → jetbrains build_project
- "format code" → jetbrains format_code
- "find TODO comments" → jetbrains find_in_files

### Search Operations
**Natural Language**: "search web", "find online", "web search", "lookup"
**Server**: `web-search`
**Tools**:
- `search_web` - Web search via DuckDuckGo
- `get_search_results` - Get formatted search results

**Usage Examples**:
- "search for Docker tutorials" → web-search search_web
- "find information about React hooks" → web-search search_web

### Video/Content Operations
**Natural Language**: "youtube", "transcript", "video", "transcription"
**Server**: `youtube-transcript`
**Tools**:
- `get_transcription` - Get video transcription
- `list_transcripts` - List available transcripts
- `search_transcripts` - Search transcripts

**Usage Examples**:
- "get youtube transcript" → youtube-transcript get_transcription
- "search video transcripts" → youtube-transcript search_transcripts

### Context/Project Analysis
**Natural Language**: "project context", "analyze project", "understand codebase", "search context"
**Server**: `context7`
**Tools**:
- `submit_search` - Submit search queries
- `expand_project_context` - Expand project context
- `context_search` - Context-aware search

**Usage Examples**:
- "understand project structure" → context7 expand_project_context
- "search in project context" → context7 submit_search

### Intelligence Layer Operations
**Natural Language**: "intelligence", "routing", "pattern analysis", "cost analysis", "optimize llm", "smart routing", "complexity analysis", "semantic analysis", "workflow optimization"
**Servers**: `ai-clios-intelligence` (via CLI MCP Server)

**Core Intelligence Tools**:
- `analyze_task_complexity` - Analyze task complexity using AI intelligence engine with recommendations
- `route_to_optimal_model` - Route request to optimal LLM model using tiered intelligence routing
- `analyze_code_semantics` - Analyze code semantics, patterns, and provide improvement suggestions
- `get_cost_analytics` - Get cost analytics and optimization suggestions for AI model usage
- `execute_intelligent_workflow` - Execute complex workflows with intelligence optimization and routing
- `get_intelligence_status` - Get status and health of intelligence services

**Intelligence Workflow Tools**:
- `run_complexity_analysis_workflow` - Complete workflow for task complexity analysis with actionable insights
- `run_cost_optimization_workflow` - Comprehensive cost analysis and optimization workflow with savings projections
- `run_pattern_recognition_workflow` - Comprehensive code pattern analysis and optimization workflow
- `run_integrated_intelligence_workflow` - Master workflow combining complexity analysis, cost optimization, and pattern recognition

**Legacy Intelligence Servers** (Direct MCP integration):
**Intelligence Router (`intelligence-router`)**:
- `route_request` - Route request to optimal LLM
- `get_routing_analytics` - Get routing performance data
- `optimize_routing_rules` - Update routing rules
- `get_health_status` - Check service health
- `analyze_request_patterns` - Analyze usage patterns
- `get_quality_metrics` - Get quality scores
- `forecast_costs` - Project future costs

**Pattern Analyzer (`pattern-analyzer`)**:
- `analyze_code` - Analyze code for patterns
- `detect_design_patterns` - Find design patterns
- `detect_anti_patterns` - Identify anti-patterns
- `analyze_intent` - Understand code intent
- `calculate_complexity` - Measure code complexity
- `assess_quality` - Evaluate code quality
- `recommend_patterns` - Suggest pattern improvements
- `suggest_refactoring` - Provide refactoring advice
- `analyze_architecture` - Review architectural patterns

**Cost Tracker (`cost-tracker`)**:
- `get_current_costs` - Get current spending
- `get_cost_breakdown` - Detailed cost analysis
- `analyze_request_patterns` - Usage pattern analysis
- `get_model_costs` - Model-specific costs
- `calculate_efficiency_metrics` - Cost efficiency data
- `analyze_budget_utilization` - Budget performance
- `identify_cost_drivers` - Find cost sources
- `optimize_budget_allocation` - Budget optimization
- `generate_cost_optimization_plan` - Cost reduction strategies

**Usage Examples**:
- "analyze complexity of this task" → ai-clios-intelligence analyze_task_complexity
- "route to best LLM for coding" → ai-clios-intelligence route_to_optimal_model
- "analyze code patterns in this file" → ai-clios-intelligence analyze_code_semantics
- "get current AI costs and optimization tips" → ai-clios-intelligence get_cost_analytics
- "run complete complexity analysis" → ai-clios-intelligence run_complexity_analysis_workflow
- "optimize AI costs with full analysis" → ai-clios-intelligence run_cost_optimization_workflow
- "analyze code patterns comprehensively" → ai-clios-intelligence run_pattern_recognition_workflow
- "run integrated intelligence workflow" → ai-clios-intelligence run_integrated_intelligence_workflow
- "check intelligence services status" → ai-clios-intelligence get_intelligence_status

## Intent Resolution Patterns

### Common Intent Patterns:
1. **File-related**: read, write, list, create, delete → `filesystem-toolkit`
2. **Git-related**: status, commit, push, history, branch → `git-toolkit`  
3. **Docker-related**: container, image, build, run, logs → `docker-toolkit`
4. **System-related**: screenshot, clipboard, process, desktop → `desktop-commander`
5. **Code-related**: analyze, build, format, refactor, inspect → `jetbrains`
6. **Search-related**: find, search, lookup, web → `web-search`
7. **Video-related**: youtube, transcript, video → `youtube-transcript`
8. **Context-related**: project, analyze, understand → `context7`
9. **Intelligence-related**: route, optimize, pattern, cost, smart, complexity, semantic, workflow → `ai-clios-intelligence`
10. **Legacy Intelligence**: specific intelligence tools → `intelligence-router`, `pattern-analyzer`, `cost-tracker`

### Ambiguity Resolution:
- If multiple servers could handle request, prefer most specific:
  - Code analysis: `ai-clios-intelligence` > `pattern-analyzer` > `jetbrains` > `context7`
  - File operations: `filesystem-toolkit` > `jetbrains`
  - Git operations: `git-toolkit` > `jetbrains`
  - Search: `context7` (project) > `web-search` (general)
  - Intelligence operations: `ai-clios-intelligence` > `intelligence-router` > `pattern-analyzer` > `cost-tracker`
  - Cost analysis: `ai-clios-intelligence` (cost_analytics) > `cost-tracker` > `intelligence-router`
  - Pattern analysis: `ai-clios-intelligence` (semantic_analysis) > `pattern-analyzer` > `jetbrains`
  - Complexity analysis: `ai-clios-intelligence` (task_complexity) > `pattern-analyzer`
  - Workflow optimization: `ai-clios-intelligence` (workflow tools) > individual intelligence servers

### Context Clues:
- Current directory with `.git` → Prefer `git-toolkit` for version control
- Current directory with `package.json` → Prefer `jetbrains` for Node.js projects  
- Current directory with `Dockerfile` → Prefer `docker-toolkit` for containerization
- File extensions (.ts, .js, .py) → Prefer `ai-clios-intelligence` or `jetbrains` for code operations
- URLs mentioned → Prefer `web-search` or `youtube-transcript`
- Intelligence/AI context → Prefer `ai-clios-intelligence` for comprehensive analysis
- Cost/budget keywords → Prefer `ai-clios-intelligence` (cost_analytics) or `cost-tracker`
- Pattern/design keywords → Prefer `ai-clios-intelligence` (semantic_analysis) or `pattern-analyzer`
- Routing/optimization keywords → Prefer `ai-clios-intelligence` (routing) or `intelligence-router`
- Complexity/analysis keywords → Prefer `ai-clios-intelligence` (task_complexity)
- Workflow/comprehensive keywords → Prefer `ai-clios-intelligence` (workflow tools)
- Development/story context → Prefer `ai-clios-intelligence` for intelligent development workflows