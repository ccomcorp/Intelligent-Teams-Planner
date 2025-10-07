# Semantic Code Analysis with Intelligence Layer

## Task Purpose
Perform advanced semantic analysis of code using AI intelligence layer services to understand code intent, identify patterns, assess quality, and provide actionable improvement recommendations.

## Parameters
- **code_target**: Path to code file or directory to analyze
- **analysis_scope**: Scope of analysis (file, module, package, project)
- **language**: Programming language (auto-detect if not specified)
- **analysis_depth**: Level of analysis (basic, detailed, comprehensive)
- **include_suggestions**: Generate improvement suggestions (default: true)
- **include_patterns**: Detect design patterns and anti-patterns (default: true)
- **include_architecture**: Include architectural analysis (default: false)

## Prerequisites
- Intelligence Layer semantic services must be operational
- Pattern Analyzer MCP server must be available
- Target code must be accessible and readable
- Semantic Intelligence service must be initialized

## Execution Process

### Step 1: Initialize Semantic Analysis
Set up analysis context and validate inputs:

1. **Validate Target Code**:
   ```
   *mcp-tool filesystem-toolkit list_directory path="${code_target}"
   ```
   - Confirm code files exist and are readable
   - Detect programming language if not specified
   - Estimate analysis scope and complexity

2. **Check Intelligence Service Status**:
   ```
   *mcp-tool get_intelligence_status
   ```
   - Verify semantic analysis capabilities are online
   - Check pattern recognition services
   - Validate cost tracking is active

### Step 2: Core Semantic Analysis
Execute comprehensive semantic code understanding:

1. **Code Semantic Analysis**:
   ```
   *mcp-tool analyze_code_semantics code="${code_content}" language="${detected_language}" includePatterns=true includeSuggestions=true
   ```

2. **Intent and Purpose Detection**:
   - Analyze code intent and business logic
   - Identify primary and secondary purposes
   - Detect functional vs non-functional aspects
   - Map code to domain concepts

3. **Complexity Assessment**:
   ```
   *mcp-tool analyze_task_complexity task="Understand and maintain this codebase" context="${code_analysis_context}" analysisDepth="comprehensive"
   ```

### Step 3: Pattern Recognition and Architecture Analysis
Apply advanced pattern detection and architectural insights:

1. **Comprehensive Pattern Analysis**:
   ```
   *mcp-tool run_pattern_recognition_workflow codebase="${code_content}" language="${language}" analysisDepth="${analysis_depth}" includeRefactoring=true includeArchitecture="${include_architecture}"
   ```

2. **Design Pattern Detection**:
   - Identify established design patterns (Gang of Four, etc.)
   - Detect domain-specific patterns
   - Find architectural patterns (MVC, MVVM, etc.)
   - Analyze pattern implementation quality

3. **Anti-Pattern Detection**:
   - Identify code smells and anti-patterns
   - Detect performance anti-patterns
   - Find security vulnerability patterns
   - Assess maintainability risks

### Step 4: Quality and Performance Analysis
Evaluate code quality dimensions:

1. **Code Quality Metrics**:
   - **Maintainability Index**: Assess ease of maintenance
   - **Cyclomatic Complexity**: Measure decision complexity
   - **Cognitive Complexity**: Evaluate understanding difficulty
   - **Technical Debt Assessment**: Quantify improvement needs

2. **Performance Pattern Analysis**:
   - Identify performance bottlenecks
   - Detect inefficient algorithms or data structures
   - Find resource management issues
   - Analyze scalability concerns

3. **Security Analysis**:
   - Detect common security vulnerabilities
   - Find input validation weaknesses
   - Identify authentication/authorization issues
   - Assess data protection patterns

### Step 5: Generate Improvement Recommendations
Create actionable improvement suggestions:

1. **Prioritized Recommendations**:
   - **Critical Issues**: Security vulnerabilities, major bugs
   - **High Priority**: Performance bottlenecks, maintainability issues
   - **Medium Priority**: Code quality improvements, pattern optimization
   - **Low Priority**: Style improvements, minor optimizations

2. **Refactoring Suggestions**:
   - Extract method/class recommendations
   - Simplify complex expressions
   - Improve naming and documentation
   - Consolidate duplicate code

3. **Architecture Improvements**:
   - Separation of concerns enhancements
   - Dependency injection opportunities
   - Interface segregation suggestions
   - Single responsibility principle violations

## Output Format

### Semantic Analysis Report
Generate comprehensive analysis report:

```markdown
# Semantic Code Analysis Report

## Executive Summary
- **Analysis Target**: ${code_target}
- **Language**: ${programming_language}
- **Analysis Depth**: ${analysis_depth}
- **Files Analyzed**: ${file_count}
- **Total Lines of Code**: ${loc_count}
- **Analysis Duration**: ${analysis_time}

## Code Intent and Purpose
### Primary Intent
${primary_code_intent}

### Business Logic Analysis
${business_logic_summary}

### Functional Categories
${functional_categorization}

## Semantic Understanding
### Code Semantics
- **Intent Clarity**: ${intent_clarity_score}/10
- **Business Logic Alignment**: ${business_alignment_score}/10
- **Domain Model Consistency**: ${domain_consistency_score}/10
- **API Design Quality**: ${api_design_score}/10

### Complexity Analysis
${complexity_analysis_results}

## Pattern Analysis
### Detected Design Patterns
${detected_patterns_list}

### Anti-Patterns Identified
${anti_patterns_list}

### Architecture Patterns
${architecture_patterns_analysis}

## Code Quality Assessment
### Quality Metrics
- **Maintainability Index**: ${maintainability_index}/100
- **Cyclomatic Complexity**: ${cyclomatic_complexity}
- **Cognitive Complexity**: ${cognitive_complexity}
- **Technical Debt Ratio**: ${technical_debt_percentage}%

### Quality Dimensions
- **Readability**: ${readability_score}/10
- **Testability**: ${testability_score}/10
- **Modularity**: ${modularity_score}/10
- **Reusability**: ${reusability_score}/10

## Performance Analysis
### Performance Patterns
${performance_patterns_analysis}

### Optimization Opportunities
${optimization_opportunities}

### Scalability Assessment
${scalability_assessment}

## Security Analysis
### Security Patterns
${security_patterns_found}

### Vulnerability Assessment
${vulnerability_summary}

### Security Recommendations
${security_recommendations}

## Improvement Recommendations

### Critical Priority (Immediate Action Required)
${critical_recommendations}

### High Priority (Next Sprint)
${high_priority_recommendations}

### Medium Priority (Ongoing Improvement)
${medium_priority_recommendations}

### Low Priority (Future Enhancement)
${low_priority_recommendations}

## Refactoring Action Plan
${detailed_refactoring_plan}

## Implementation Timeline
- **Week 1**: Critical issues and security fixes
- **Week 2-3**: High priority improvements
- **Month 2**: Medium priority enhancements
- **Ongoing**: Low priority optimizations

## Success Metrics
- **Quality Score Improvement**: Target +20 points
- **Complexity Reduction**: Target -30% cyclomatic complexity
- **Performance Gain**: Target +25% execution speed
- **Maintainability**: Target +40% maintainability index

## Next Steps
${recommended_next_actions}
```

### Pattern Detection Details
For each detected pattern:

```markdown
### ${Pattern_Name}
- **Type**: ${pattern_type} (Design/Architecture/Anti-pattern)
- **Confidence**: ${confidence_percentage}%
- **Location**: ${file_path}:${line_range}
- **Quality**: ${implementation_quality}
- **Impact**: ${impact_assessment}
- **Recommendation**: ${specific_action}
```

## Integration with BMAD Agents

### Dev Agent Usage
When used by the dev agent:
- Analyze code before major refactoring
- Understand legacy code during maintenance
- Validate architectural decisions
- Guide implementation approach selection

### QA Agent Usage
When used by the QA agent:
- Comprehensive code quality assessment
- Pattern compliance validation
- Architecture review support
- Technical debt quantification

## Error Handling

### Common Issues and Solutions

1. **Semantic Analysis Service Unavailable**:
   - Check intelligence layer service status
   - Fall back to basic code analysis tools
   - Provide limited analysis with available tools

2. **Unsupported Programming Language**:
   - List supported languages
   - Provide generic quality metrics
   - Suggest alternative analysis approaches

3. **Large Codebase Performance**:
   - Implement incremental analysis
   - Focus on changed files only
   - Use parallel processing when available

4. **Analysis Timeout**:
   - Break analysis into smaller chunks
   - Prioritize critical files
   - Provide partial results with continuation plan

## Performance Considerations

### Analysis Optimization
- **Incremental Analysis**: Only analyze changed code when possible
- **Smart Caching**: Reuse previous analysis results
- **Parallel Processing**: Analyze multiple files simultaneously  
- **Progressive Enhancement**: Start with basic analysis, add detail as needed

### Cost Management
- **Budget Monitoring**: Track analysis costs against project budgets
- **Model Tiering**: Use appropriate AI models for analysis depth
- **Batch Processing**: Group similar analysis tasks
- **Result Caching**: Avoid re-analyzing unchanged code

## Success Criteria
- [ ] Semantic code understanding achieved with high confidence
- [ ] Design patterns accurately detected and categorized
- [ ] Code quality metrics calculated and benchmarked
- [ ] Actionable improvement recommendations provided
- [ ] Performance optimization opportunities identified
- [ ] Security vulnerability assessment completed
- [ ] Refactoring plan created with realistic timelines

## Dependencies
- **Internal**: Semantic Intelligence service, Pattern Recognition engine
- **External**: Code repository access, file system permissions
- **Tools**: analyze_code_semantics, run_pattern_recognition_workflow, analyze_task_complexity

## Validation Steps
1. **Analysis Accuracy**: Manually verify sample pattern detections
2. **Recommendation Quality**: Validate suggestions are actionable
3. **Performance Impact**: Ensure analysis completes within time bounds
4. **Cost Efficiency**: Confirm analysis stays within budget
5. **Integration Test**: Verify compatibility with BMAD workflows