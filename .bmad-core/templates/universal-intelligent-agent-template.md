# Universal Intelligent Agent Template

## Template Purpose
This template serves as the foundation for creating new intelligent agents with the `*i-[agentname]` pattern. Each intelligent agent integrates the AI-CLIOS intelligence layer for enhanced performance, cost optimization, and smart routing.

## Template Structure

### Required Sections

#### 1. Agent Metadata
```yaml
agent:
  name: [Agent Name]              # e.g., "Quinn", "Sarah", "Alex"
  id: [agent-id]                  # e.g., "qa", "architect", "pm"
  title: [Professional Title]     # e.g., "Senior QA Architect", "System Architect"
  icon: [Emoji]                   # e.g., 🧪, 🏗️, 📋
  domain: [Specialization Area]   # e.g., "Quality Assurance", "System Architecture"
  whenToUse: [Usage Description]  # When to activate this agent
```

#### 2. Intelligence Integration
```yaml
intelligence:
  primary_tools:                  # Agent's main intelligence capabilities
    - tool_name: [Description]
    - tool_name: [Description]
  
  complexity_focus: [Domain]      # What complexity this agent analyzes
  cost_optimization: [Approach]   # How agent optimizes costs
  routing_strategy: [Strategy]    # Model selection approach
  
  default_budget: [Amount]        # Default cost budget (e.g., $5.00)
  optimize_for: [Priority]        # speed|cost|quality
```

#### 3. Agent Persona
```yaml
persona:
  role: [Professional Role Description]
  style: [Communication Style]     # e.g., "Methodical, detail-oriented, mentoring"
  identity: [Core Identity]        # Agent's professional identity
  focus: [Primary Focus Area]      # What agent concentrates on
  
  core_principles:
    - [Principle 1]
    - [Principle 2]
    - [Principle 3]
```

#### 4. Intelligent Commands
```yaml
commands:
  # Universal intelligent command
  - i-[agent-id]: Execute intelligent [domain] workflow with AI optimization
      usage: "*i-[agent-id] [target] [options]"
      parameters:
        - target: [Target object/file/scope]
        - complexity_threshold: low|medium|high (default: medium)
        - cost_budget: [dollar amount] (default: $5.00)
        - optimize_for: speed|cost|quality (default: quality)
        - enable_pattern_analysis: true|false (default: true)
        - parallel_tasks: [number] (default: 3)
      
  # Standard agent commands  
  - help: Show available commands
  - [domain-command-1]: [Description]
  - [domain-command-2]: [Description]
  - review: Execute automated code/work review with intelligence
  - validate: Run comprehensive validation with real infrastructure testing
  - parallel-dev: Enable parallel development with subagents
  - cost-status: Show intelligence layer cost usage and optimization
  - exit: Exit agent mode
```

#### 5. Parallel Development Configuration
```yaml
parallel_development:
  max_subagents: [Number]         # Maximum concurrent subagents (default: 3)
  task_isolation: true            # Ensure task independence
  conflict_resolution: automatic  # How to handle conflicts
  coordination_method: [Method]   # How subagents coordinate
  
  subagent_roles:
    - role: [Subagent Role 1]
      focus: [Specific Focus Area]
      tools: [List of tools]
    - role: [Subagent Role 2] 
      focus: [Specific Focus Area]
      tools: [List of tools]
```

#### 6. Quality Assurance Integration
```yaml
quality_assurance:
  review_criteria:
    - [Criterion 1]
    - [Criterion 2]
    - [Criterion 3]
  
  validation_steps:
    - step: TypeScript compilation
      command: "npm run build"
      required: true
    - step: ESLint validation
      command: "npm run lint"
      required: true
    - step: Real infrastructure testing
      command: "npm run test"
      required: true
    - step: [Domain-specific validation]
      command: [Validation command]
      required: true
  
  performance_benchmarks:
    response_time: [Target time]
    cost_efficiency: [Target ratio]
    quality_score: [Minimum score]
```

#### 7. Dependencies
```yaml
dependencies:
  tasks:
    - intelligent-[agent-id]-workflow.md
    - [domain-specific-task-1].md
    - [domain-specific-task-2].md
    - execute-checklist.md
    - validate-[domain].md
  
  checklists:
    - [domain]-quality-checklist.md
    - universal-intelligence-checklist.md
  
  data:
    - [domain]-patterns.md
    - intelligence-tool-mappings.md
    - mcp-tool-capabilities.md
```

## Implementation Guidelines

### Phase 1: Agent Definition
1. **Copy this template** to `.bmad-core/agents/[agent-id].md`
2. **Replace all bracketed placeholders** with agent-specific values
3. **Define agent domain expertise** and intelligence tool mapping
4. **Specify parallel development approach** for the agent's work

### Phase 2: Intelligence Workflow Creation
1. **Create intelligent workflow task** at `.bmad-core/tasks/intelligent-[agent-id]-workflow.md`
2. **Map intelligence tools** to agent's domain (analyze_complexity, pattern_recognize, etc.)
3. **Define cost optimization strategy** for the agent's typical operations
4. **Implement model routing logic** based on task complexity and requirements

### Phase 3: Parallel Development Setup
1. **Define subagent roles** for breaking down complex tasks
2. **Implement task isolation** to prevent conflicts
3. **Create coordination mechanisms** for subagent synchronization
4. **Set up resource scheduling** for intelligence tool usage

### Phase 4: Quality Assurance Implementation
1. **Implement *review command** with automated code/work review
2. **Implement *validate command** with real infrastructure testing
3. **Set up TypeScript compilation** validation after each task
4. **Configure ESLint integration** for code quality enforcement

### Phase 5: Testing & Validation
1. **Create comprehensive test suite** using real infrastructure only
2. **Implement performance benchmarking** for response time and cost tracking
3. **Validate cross-model compatibility** (OpenAI, Anthropic, Ollama, etc.)
4. **Test parallel development coordination** with multiple concurrent tasks

## Intelligence Tool Mappings by Domain

### Quality Assurance (QA)
- **Primary**: pattern_recognize, analyze_complexity, cost_optimize
- **Use Cases**: Code quality analysis, test strategy optimization, defect pattern recognition
- **Routing**: Analysis-focused models for code review, cost-effective models for routine checks

### System Architecture  
- **Primary**: analyze_complexity, semantic_search, cost_optimize
- **Use Cases**: Architecture complexity assessment, pattern analysis, infrastructure cost modeling
- **Routing**: High-performance models for complex architecture analysis, standard models for routine tasks

### Development
- **Primary**: analyze_complexity, route_optimal_llm, semantic_search, pattern_recognize
- **Use Cases**: Code generation, debugging assistance, pattern application, optimization
- **Routing**: Coding-optimized models for implementation, reasoning models for complex problem solving

### Product Management
- **Primary**: analyze_complexity, cost_optimize, route_optimal_llm  
- **Use Cases**: Feature complexity assessment, ROI optimization, strategic decision support
- **Routing**: Reasoning models for strategic analysis, cost-effective models for routine planning

### Scrum Master
- **Primary**: analyze_complexity, cost_optimize, cache_semantic
- **Use Cases**: Story complexity assessment, sprint optimization, team velocity prediction  
- **Routing**: Fast models for sprint planning, analytical models for complex estimation

## Universal Command Patterns

### Intelligent Workflow Execution
```bash
# Standard pattern for all intelligent agents
*i-[agentname] [target] complexity_threshold=medium cost_budget=5 optimize_for=quality

# Examples:
*i-qa packages/intelligence/src/ complexity_threshold=high cost_budget=8 optimize_for=quality
*i-architect system-overview.md complexity_threshold=high cost_budget=10 optimize_for=performance  
*i-sm sprint-backlog.md complexity_threshold=low cost_budget=3 optimize_for=speed
```

### Review and Validation
```bash
# Universal review command (works after any intelligent operation)
*review [scope] [criteria]

# Universal validation command (real infrastructure testing)
*validate [component] --full --performance

# Examples:
*review recent-changes code-quality
*validate intelligence-integration --full
```

### Parallel Development
```bash
# Enable parallel development for complex tasks
*parallel-dev enable max_agents=5 isolation=strict

# Coordinate subagents for large implementations
*i-dev story-complex-feature.md parallel_tasks=4 coordination=automatic
```

## Quality Gates

### Pre-Execution Validation
1. **Intelligence Service Health Check**: Verify all required intelligence tools are available
2. **Cost Budget Validation**: Ensure sufficient budget for planned operations  
3. **Resource Availability**: Check for concurrent usage conflicts
4. **Target Validation**: Verify target files/scope exist and are accessible

### Post-Execution Validation
1. **TypeScript Compilation**: `npm run build` must pass
2. **ESLint Validation**: `npm run lint` must pass with zero errors
3. **Real Infrastructure Testing**: `npm run test` with actual database/service connections
4. **Performance Benchmarks**: Response time and cost efficiency within targets
5. **Quality Metrics**: Agent-specific quality criteria met

### Continuous Monitoring
1. **Cost Tracking**: Real-time monitoring of intelligence layer usage
2. **Performance Metrics**: Response time and resource utilization
3. **Quality Scores**: Automated assessment of output quality
4. **Error Tracking**: Detection and handling of intelligence service failures

## Error Handling and Fallbacks

### Intelligence Service Failures
- **Service Unavailable**: Fall back to standard agent operation without intelligence
- **Cost Budget Exceeded**: Switch to lower-cost models or reduce analysis depth
- **Analysis Timeout**: Use cached results or simplified analysis approaches

### Parallel Development Issues
- **Subagent Conflicts**: Automatic conflict resolution with user notification
- **Resource Contention**: Queue management for intelligence tool access
- **Coordination Failures**: Fallback to sequential task execution

### Quality Assurance Failures  
- **Compilation Errors**: Automatic fix suggestions with intelligence assistance
- **Test Failures**: Detailed analysis and remediation recommendations
- **Performance Issues**: Optimization suggestions and alternative approaches

## Success Metrics

### Development Efficiency
- **40% reduction** in development time for complex tasks
- **90% accuracy** in complexity detection and routing decisions
- **95% success rate** for parallel development coordination

### Cost Effectiveness
- **Stay within budget** 98% of the time across all intelligent agents
- **50% cost optimization** through smart model routing and caching
- **300% ROI** from intelligence layer integration

### Quality Metrics
- **95%+ quality scores** for all intelligent agent outputs
- **85% pattern compliance** rate across different domains  
- **Zero performance regressions** from intelligence layer integration
- **>80% test coverage** for all intelligent agent implementations

## Usage Examples

### QA Intelligence Agent
```bash
# Comprehensive code quality analysis with parallel subagents
*i-qa packages/intelligence/src/ complexity_threshold=high cost_budget=8 optimize_for=quality parallel_tasks=4

# Quick review of recent changes
*i-qa git:last-commit complexity_threshold=low cost_budget=2 optimize_for=speed

# Full validation with performance testing
*validate intelligence-integration --full --performance --cost-analysis
```

### Architect Intelligence Agent
```bash
# System architecture analysis with cost modeling
*i-architect system-architecture.md complexity_threshold=high cost_budget=12 optimize_for=performance

# Infrastructure optimization review  
*i-architect docker-compose.yml complexity_threshold=medium cost_budget=5 optimize_for=cost

# Architecture pattern recognition
*review architecture-patterns system-wide
```

### Development Intelligence Agent
```bash
# Complex feature implementation with AI assistance
*i-dev story-tiered-llm-router.md complexity_threshold=high cost_budget=10 optimize_for=quality parallel_tasks=3

# Bug fix with pattern analysis
*i-dev bug-report-123.md complexity_threshold=low cost_budget=3 optimize_for=speed

# Code refactoring with optimization
*i-dev refactor-legacy-code.md complexity_threshold=medium cost_budget=6 optimize_for=quality
```

This universal template provides a robust foundation for creating intelligent agents that leverage the full power of the AI-CLIOS intelligence layer while maintaining consistency, quality, and cost-effectiveness across all implementations.