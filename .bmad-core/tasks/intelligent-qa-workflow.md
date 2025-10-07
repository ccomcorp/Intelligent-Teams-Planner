# Intelligent QA Agent Workflow

## Task Purpose
Execute intelligent quality assurance workflows with automated pattern recognition, code analysis, and cost-aware testing strategies for comprehensive story review.

## Parameters
- **story**: Story file path for QA review
- **code_paths**: Array of file paths for code analysis
- **analysis_depth**: Level of analysis (basic|detailed|comprehensive) (default: detailed)
- **cost_budget**: Maximum cost budget for AI-powered analysis (default: $3.00)
- **quality_threshold**: Minimum quality score required (default: 85)
- **enable_refactoring**: Allow AI-guided refactoring suggestions (default: true)

## Execution Process

### Phase 1: Pre-Review Intelligence Gathering

#### Step 1: Story Context Analysis
Analyze story requirements and implementation scope:

1. **Load Story and Implementation**:
   - Read story file and extract acceptance criteria
   - Analyze completed tasks and subtasks
   - Gather implementation file paths from Dev Agent Record
   - Extract test requirements and coverage expectations

2. **Implementation Complexity Assessment**:
   ```
   *mcp-tool ai-clios-intelligence analyze_task_complexity \
     task="QA Review: [story_title]" \
     context="Review implementation of [story_requirements]" \
     includeRecommendations=true \
     analysisDepth="detailed"
   ```

3. **Quality Analysis Scope Definition**:
   - **Basic Review**: Code syntax, basic patterns, test execution
   - **Detailed Review**: Pattern analysis, architecture compliance, performance
   - **Comprehensive Review**: Full security scan, optimization analysis, maintainability

#### Step 2: Smart Testing Strategy
Configure intelligent testing approach based on complexity:

1. **Test Strategy Selection**:
   ```
   *mcp-tool ai-clios-intelligence route_to_optimal_model \
     prompt="QA analysis for [implementation_summary]" \
     taskType="analysis" \
     complexity="[story_complexity]" \
     maxCost="[allocated_budget]"
   ```

2. **Pattern-Based Test Planning**:
   - Identify code patterns requiring specific test coverage
   - Generate test scenarios based on complexity analysis
   - Prioritize testing focus areas

### Phase 2: Intelligent Code Review

#### Step 3: Comprehensive Pattern Analysis
Execute multi-layered code analysis:

1. **Primary Pattern Recognition**:
   ```
   *mcp-tool ai-clios-intelligence run_pattern_recognition_workflow \
     codebase="[implementation_code]" \
     language="typescript" \
     analysisDepth="[configured_depth]" \
     includeRefactoring=true \
     includeArchitecture=true
   ```

2. **Semantic Code Analysis**:
   For each significant file:
   ```
   *mcp-tool ai-clios-intelligence analyze_code_semantics \
     code="[file_content]" \
     language="[file_language]" \
     includePatterns=true \
     includeSuggestions=true
   ```

3. **Cross-File Pattern Consistency**:
   - Validate consistent pattern usage across implementation
   - Check for architectural pattern compliance
   - Identify pattern violations and inconsistencies

#### Step 4: Quality Gate Analysis
Execute intelligent quality gates:

1. **Code Quality Metrics**:
   - Cyclomatic complexity analysis
   - Maintainability index calculation
   - Technical debt assessment
   - Code duplication detection

2. **Performance Pattern Analysis**:
   - Identify performance anti-patterns
   - Analyze resource usage patterns
   - Check for scalability concerns
   - Memory leak detection

3. **Security Pattern Review**:
   - Input validation patterns
   - Authentication/authorization patterns
   - Data sanitization compliance
   - Vulnerability pattern detection

### Phase 3: Intelligent Testing and Validation

#### Step 5: AI-Powered Test Execution
Execute tests with intelligent analysis:

1. **Test Coverage Analysis**:
   ```bash
   # Run tests and gather coverage data
   npm test -- --coverage
   
   # Analyze coverage with AI insights
   *mcp-tool ai-clios-intelligence analyze_code_semantics \
     code="[test_files]" \
     language="typescript" \
     includePatterns=true \
     includeSuggestions=true
   ```

2. **Test Pattern Validation**:
   - Verify test patterns match code patterns
   - Check for missing edge case coverage
   - Validate mock and stub usage patterns
   - Ensure integration test completeness

3. **Performance Testing Intelligence**:
   - Identify performance-critical code paths
   - Generate performance test scenarios
   - Analyze performance test results
   - Compare against performance benchmarks

#### Step 6: Cost-Aware Quality Optimization
Optimize quality processes based on cost constraints:

1. **Cost Tracking and Optimization**:
   ```
   *mcp-tool ai-clios-intelligence get_cost_analytics \
     timeRange="hour" \
     includeOptimizations=true \
     groupBy="task_type"
   ```

2. **Quality ROI Analysis**:
   - Calculate cost per quality improvement
   - Prioritize high-impact, low-cost fixes
   - Balance quality gains vs. analysis cost

### Phase 4: Intelligent Refactoring and Recommendations

#### Step 7: AI-Guided Refactoring
Generate intelligent refactoring recommendations:

1. **Refactoring Priority Analysis**:
   - High-impact code quality issues
   - Performance optimization opportunities  
   - Maintainability improvements
   - Technical debt reduction

2. **Pattern-Based Refactoring**:
   - Suggest consistent pattern application
   - Recommend architectural improvements
   - Provide implementation guidance
   - Estimate refactoring effort and ROI

3. **Safe Refactoring Validation**:
   - Verify refactoring maintains functionality
   - Check test coverage after changes
   - Validate performance impact
   - Ensure backward compatibility

#### Step 8: Comprehensive Quality Report
Generate intelligent quality assessment:

1. **Quality Score Calculation**:
   ```
   Quality Score = (Pattern_Compliance * 0.3) + 
                  (Code_Quality * 0.25) + 
                  (Test_Coverage * 0.2) + 
                  (Performance * 0.15) + 
                  (Security * 0.1)
   ```

2. **Intelligence-Enhanced Findings**:
   - AI-detected code issues with severity ranking
   - Pattern compliance analysis
   - Refactoring recommendations with effort estimates
   - Cost-benefit analysis of improvements

### Phase 5: Story Completion with Intelligence Metrics

#### Step 9: Enhanced Story Documentation
Update story file with comprehensive QA results:

```markdown
## QA Results - Intelligence Enhanced

### Overall Assessment  
- **Quality Score**: [calculated_score]/100
- **Pattern Compliance**: [pattern_score]% 
- **Test Coverage**: [coverage_percentage]%
- **Performance Grade**: [performance_grade]
- **Security Score**: [security_score]/100

### Intelligence Analysis
- **Analysis Cost**: $[total_analysis_cost]
- **Model Efficiency**: [optimized_requests]/[total_requests] requests optimized
- **Time Saved**: [estimated_time_saved] hours through AI assistance
- **Quality ROI**: [improvement_value] / [analysis_cost] = [roi_ratio]

### Pattern Analysis Results
[AI-generated pattern analysis summary]

### Refactoring Recommendations
[AI-prioritized refactoring suggestions with effort estimates]

### Performance Insights
[AI-detected performance patterns and optimization opportunities]

### Next Steps
[AI-generated priority action items for development team]
```

## Integration with QA Agent Commands

### Enhanced `*review` Command  
Modify the QA agent's review command to use intelligence workflows:

```yaml
review:
  intelligent-execution:
    - STEP 1: Story context and complexity analysis
    - STEP 2: Smart testing strategy configuration
    - STEP 3: Comprehensive pattern recognition
    - STEP 4: AI-powered quality gate analysis
    - STEP 5: Intelligent test execution and validation
    - STEP 6: Cost-aware optimization recommendations
    - STEP 7: AI-guided refactoring suggestions
    - STEP 8: Enhanced quality report generation
```

### New Intelligence Commands
Add specialized QA intelligence commands:

```yaml
commands:
  - analyze-patterns: Run comprehensive pattern analysis on implementation
  - quality-score: Calculate AI-enhanced quality score
  - refactor-recommendations: Generate AI-powered refactoring suggestions
  - security-scan: Run AI-powered security pattern analysis  
  - performance-analysis: Analyze performance patterns and optimizations
  - cost-optimize-qa: Optimize QA process for cost efficiency
```

## Advanced QA Intelligence Features

### Predictive Quality Analysis
Use AI to predict quality issues before they occur:

1. **Code Change Impact Prediction**:
   - Analyze code changes for potential breaking effects
   - Predict test failures before running tests
   - Estimate maintenance burden of changes

2. **Pattern Drift Detection**:
   - Monitor for architectural pattern violations
   - Detect gradual code quality degradation
   - Alert on pattern consistency issues

### Automated Quality Learning
Learn from previous reviews to improve analysis:

1. **Pattern Learning**:
   - Build project-specific pattern libraries
   - Learn from past code review feedback  
   - Adapt quality standards to project context

2. **Review Efficiency Optimization**:
   - Focus analysis on historically problematic areas
   - Prioritize reviews based on risk patterns
   - Optimize cost allocation across quality activities

## Success Criteria

### Quality Effectiveness
- Detect 95% of critical code issues through AI analysis
- Achieve 90% pattern compliance across implementations
- Maintain quality scores above configured thresholds

### Cost Efficiency  
- Stay within QA cost budget 98% of the time
- Achieve 40% reduction in manual review time
- ROI of 200% from intelligent QA processes

### Review Accuracy
- 85% of AI-generated recommendations implemented
- 90% accuracy in complexity and risk assessment
- Zero false positive critical issues

## Error Handling and Fallbacks

### Intelligence Service Failures
1. **Pattern Analysis Unavailable**: Use static analysis tools
2. **Cost Budget Exceeded**: Switch to basic quality checks
3. **AI Model Failures**: Fall back to traditional review methods

### Quality Gate Failures
1. **Below Threshold**: Trigger enhanced analysis mode
2. **Critical Issues Detected**: Escalate to senior developers
3. **Pattern Violations**: Require architectural review

## Usage Examples

### Standard Story Review
```bash
# Comprehensive QA review with pattern analysis
*review story="user-feature-implementation.md" \
  analysis_depth="detailed" \
  cost_budget="$3.00" \
  quality_threshold="85" \
  enable_refactoring=true
```

### Security-Critical Feature
```bash
# Enhanced security analysis
*review story="payment-processing-feature.md" \
  analysis_depth="comprehensive" \
  cost_budget="$5.00" \
  quality_threshold="95" \
  enable_refactoring=true
```

### Legacy Code Review  
```bash
# Cost-optimized review for legacy code
*review story="legacy-refactoring-task.md" \
  analysis_depth="basic" \
  cost_budget="$2.00" \
  quality_threshold="75" \
  enable_refactoring=false
```

This intelligent QA workflow transforms traditional code review by adding AI-powered pattern recognition, cost-aware analysis, and predictive quality insights while maintaining the structured BMAD review process.