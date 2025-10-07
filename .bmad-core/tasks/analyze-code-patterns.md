# Analyze Code Patterns with Intelligence Layer

## Task Purpose
Leverage the Intelligence Layer's Semantic Code Intelligence service to analyze code for design patterns, anti-patterns, and architectural insights. This task integrates with the pattern detection system and provides actionable recommendations for code improvement.

## Parameters
- **code_path**: Path to code file or directory to analyze
- **language**: Programming language (typescript, javascript, python, etc.)
- **analysis_depth**: Level of analysis (basic, standard, comprehensive)
- **pattern_focus**: Specific patterns to focus on (optional)
- **context**: Additional context about the code's purpose

## Prerequisites
- Intelligence Layer services must be running
- Pattern Analyzer MCP server must be available
- Code files must be accessible

## Execution Process

### Step 1: Initialize Analysis Context
Set up the analysis environment and validate inputs:

1. **Validate Input Parameters**:
   ```
   *mcp-tool filesystem-toolkit list_directory path="${code_path}"
   ```
   - Confirm code files exist
   - Detect programming language if not specified
   - Estimate analysis scope

2. **Check Intelligence Layer Status**:
   ```
   *mcp-tool intelligence-router get_health_status
   ```
   - Verify pattern analyzer is online
   - Check semantic analysis capabilities
   - Validate cost tracking is active

### Step 2: Code Pattern Detection
Execute comprehensive pattern analysis:

1. **Primary Pattern Analysis**:
   ```
   *mcp-tool pattern-analyzer analyze_code code="${code_content}" language="${language}" depth="${analysis_depth}"
   ```
   
2. **Design Pattern Recognition**:
   ```
   *mcp-tool pattern-analyzer detect_design_patterns code_path="${code_path}" focus="${pattern_focus}"
   ```
   
3. **Anti-Pattern Detection**:
   ```
   *mcp-tool pattern-analyzer detect_anti_patterns code_path="${code_path}" language="${language}"
   ```

### Step 3: Semantic Code Intelligence
Apply advanced code understanding:

1. **Code Intent Analysis**:
   ```
   *mcp-tool pattern-analyzer analyze_intent code="${code_content}" context="${context}"
   ```
   
2. **Complexity Assessment**:
   ```
   *mcp-tool pattern-analyzer calculate_complexity code_path="${code_path}"
   ```
   
3. **Quality Metrics**:
   ```
   *mcp-tool pattern-analyzer assess_quality code_path="${code_path}" language="${language}"
   ```

### Step 4: Generate Recommendations
Produce actionable insights:

1. **Pattern Recommendations**:
   ```
   *mcp-tool pattern-analyzer recommend_patterns context="${analysis_results}" language="${language}"
   ```
   
2. **Refactoring Suggestions**:
   ```
   *mcp-tool pattern-analyzer suggest_refactoring code="${code_content}" patterns="${detected_patterns}"
   ```
   
3. **Architecture Insights**:
   ```
   *mcp-tool pattern-analyzer analyze_architecture code_path="${code_path}" scope="project"
   ```

### Step 5: Cost and Performance Analysis
Evaluate analysis efficiency:

1. **Cost Tracking**:
   ```
   *mcp-tool cost-tracker get_analysis_cost task="pattern_analysis" timerange="last_hour"
   ```
   
2. **Performance Metrics**:
   ```
   *mcp-tool intelligence-router get_routing_metrics service="pattern_analyzer"
   ```

## Output Format

### Analysis Report Structure
Generate a comprehensive analysis report:

```markdown
# Code Pattern Analysis Report

## Executive Summary
- **Files Analyzed**: {file_count}
- **Primary Language**: {language}
- **Analysis Depth**: {analysis_depth}
- **Total Patterns Found**: {pattern_count}
- **Analysis Duration**: {duration}
- **Cost**: ${analysis_cost}

## Design Patterns Detected
{list_of_detected_patterns_with_confidence_scores}

## Anti-Patterns Identified
{list_of_anti_patterns_with_severity_levels}

## Code Quality Metrics
- **Complexity Score**: {complexity_score}/100
- **Maintainability Index**: {maintainability_score}/100
- **Technical Debt Ratio**: {debt_ratio}%
- **Test Coverage Impact**: {coverage_impact}

## Recommendations

### High Priority
{critical_refactoring_suggestions}

### Medium Priority  
{improvement_opportunities}

### Low Priority
{nice_to_have_enhancements}

## Architecture Insights
{architectural_observations_and_suggestions}

## Next Steps
{recommended_actions_with_priorities}
```

### Pattern Details Format
For each detected pattern:

```markdown
### {Pattern Name}
- **Type**: {Design Pattern | Anti-Pattern}
- **Confidence**: {confidence_percentage}%
- **Location**: {file_path}:{line_range}
- **Impact**: {High | Medium | Low}
- **Description**: {pattern_description}
- **Recommendation**: {specific_action_to_take}
```

## Error Handling

### Common Issues and Solutions

1. **Intelligence Layer Unavailable**:
   - Check service status with `*mcp-tool intelligence-router get_health_status`
   - Fall back to local pattern detection if available
   - Notify user of limited capabilities

2. **Unsupported Language**:
   - List supported languages from pattern analyzer
   - Suggest alternative analysis approaches
   - Provide generic code quality metrics

3. **Large Codebase Timeout**:
   - Break analysis into chunks
   - Focus on changed files only
   - Use parallel analysis if available

4. **Pattern Analysis Failure**:
   - Retry with basic analysis depth
   - Use alternative MCP servers (jetbrains for basic analysis)
   - Provide manual pattern detection guidance

## Integration Points

### BMAD Agent Usage
When used by BMAD agents:

```yaml
# Dev Agent Integration
- Use for code review before commits
- Integrate with story implementation tasks
- Apply recommendations during refactoring

# QA Agent Integration  
- Include in code review workflow
- Use for quality gate validation
- Generate pattern compliance reports
```

### Workflow Integration
- **Pre-commit Hook**: Analyze changed files automatically
- **CI/CD Pipeline**: Include pattern analysis in build process
- **Code Review**: Generate pattern reports for review discussions
- **Refactoring Planning**: Use insights for technical debt planning

## Performance Considerations

### Analysis Optimization
- **Incremental Analysis**: Only analyze changed files when possible
- **Caching**: Leverage pattern cache for repeated analysis
- **Parallel Processing**: Use multiple workers for large codebases
- **Smart Sampling**: Analyze representative files for large projects

### Cost Management
- **Budget Tracking**: Monitor analysis costs against project budgets
- **Model Selection**: Use appropriate LLM tier for analysis depth
- **Batch Processing**: Group similar analysis tasks
- **Result Caching**: Reuse analysis results when code hasn't changed

## Success Criteria
- [ ] Code patterns successfully detected and categorized
- [ ] Quality metrics calculated and presented clearly
- [ ] Actionable recommendations provided with priorities
- [ ] Analysis completed within cost and time budgets
- [ ] Results formatted for easy consumption by stakeholders
- [ ] Integration with existing development workflow successful

## Dependencies
- **Internal**: Intelligence Layer services, MCP servers
- **External**: Code repository access, file system permissions
- **Tools**: pattern-analyzer, cost-tracker, intelligence-router MCP servers

## Validation Steps
1. **Accuracy Check**: Manually verify a sample of detected patterns
2. **Performance Test**: Ensure analysis completes within reasonable time
3. **Cost Validation**: Confirm analysis stays within budget limits  
4. **Integration Test**: Verify compatibility with BMAD agent workflows
5. **Output Quality**: Review report clarity and actionability