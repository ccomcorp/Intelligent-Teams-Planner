# Intelligent Architect Agent Workflow

## Task Purpose
Execute intelligent architecture workflows with cost-aware decision making, pattern analysis, and scalability optimization for system design and architecture reviews.

## Parameters
- **architecture_scope**: Scope of architecture analysis (component|system|enterprise) (default: system)
- **cost_budget**: Maximum cost budget for AI-powered architecture analysis (default: $8.00)
- **optimization_goals**: Array of optimization priorities (performance|cost|scalability|maintainability) (default: ["scalability", "maintainability"])
- **analysis_depth**: Depth of architecture analysis (overview|detailed|comprehensive) (default: detailed)
- **include_patterns**: Enable architectural pattern analysis and recommendations (default: true)
- **generate_migration_plan**: Generate migration/refactoring plans (default: true)

## Execution Process

### Phase 1: Architecture Context Intelligence

#### Step 1: System Complexity Assessment
Analyze the architectural scope and complexity:

1. **Architecture Discovery**:
   - Scan codebase structure and dependencies
   - Identify architectural boundaries and components  
   - Map service interactions and data flows
   - Analyze technology stack and integration patterns

2. **Complexity Analysis of Architecture Scope**:
   ```
   *mcp-tool ai-clios-intelligence analyze_task_complexity \
     task="Architecture analysis: [architecture_scope]" \
     context="System: [system_description], Goals: [optimization_goals]" \
     includeRecommendations=true \
     analysisDepth="comprehensive"
   ```

3. **Cost-Benefit Architecture Planning**:
   - Estimate analysis costs vs. architectural improvements
   - Prioritize high-impact, cost-effective changes
   - Set cost allocation across architecture activities

#### Step 2: Intelligent Model Selection for Architecture
Configure optimal AI assistance for architectural decisions:

1. **Architecture-Specific Model Routing**:
   ```
   *mcp-tool ai-clios-intelligence route_to_optimal_model \
     prompt="Architecture analysis and design recommendations" \
     taskType="reasoning" \
     complexity="high" \
     maxCost="[allocated_architecture_budget]"
   ```

2. **Specialized Analysis Configuration**:
   - **System Design**: Use reasoning-optimized models
   - **Pattern Analysis**: Use code analysis models
   - **Documentation**: Use summarization models
   - **Cost Analysis**: Use analytical models

### Phase 2: Comprehensive Architecture Analysis

#### Step 3: Multi-Dimensional Architecture Pattern Recognition
Execute comprehensive architectural pattern analysis:

1. **Codebase Architecture Analysis**:
   ```
   *mcp-tool ai-clios-intelligence run_pattern_recognition_workflow \
     codebase="[full_system_codebase]" \
     language="typescript" \
     analysisDepth="comprehensive" \
     includeRefactoring=true \
     includeArchitecture=true
   ```

2. **Architectural Pattern Detection**:
   - **Structural Patterns**: Layered, Microservices, Event-Driven, etc.
   - **Integration Patterns**: API Gateway, Message Queue, Database patterns
   - **Deployment Patterns**: Container orchestration, Service mesh
   - **Security Patterns**: Authentication, authorization, data protection

3. **Cross-Service Pattern Analysis**:
   - Service communication patterns
   - Data consistency patterns  
   - Error handling and resilience patterns
   - Monitoring and observability patterns

#### Step 4: Cost-Aware Architecture Optimization
Analyze architecture with cost considerations:

1. **Infrastructure Cost Analysis**:
   ```
   *mcp-tool ai-clios-intelligence get_cost_analytics \
     timeRange="month" \
     includeOptimizations=true \
     groupBy="provider"
   ```

2. **Architecture Cost Modeling**:
   - Infrastructure scaling costs
   - Development team efficiency costs
   - Maintenance and technical debt costs
   - Migration and refactoring costs

3. **Cost-Performance Trade-off Analysis**:
   - Identify high-cost, low-value architectural components
   - Recommend cost-effective alternatives
   - Model ROI of architectural improvements

### Phase 3: Strategic Architecture Planning

#### Step 5: Intelligent Architecture Recommendations
Generate data-driven architecture recommendations:

1. **Scalability Analysis**:
   - Identify scalability bottlenecks
   - Recommend scaling strategies
   - Model performance under load
   - Suggest horizontal vs. vertical scaling approaches

2. **Maintainability Assessment**:
   - Technical debt quantification
   - Code coupling and cohesion analysis
   - Refactoring priority recommendations
   - Long-term maintenance cost projections

3. **Technology Stack Optimization**:
   - Identify outdated or problematic dependencies
   - Recommend modern alternatives
   - Analyze migration complexity and costs
   - Suggest technology consolidation opportunities

#### Step 6: Migration and Evolution Planning
Create intelligent migration strategies:

1. **Migration Complexity Assessment**:
   ```
   *mcp-tool ai-clios-intelligence analyze_task_complexity \
     task="System migration: [current_state] → [target_state]" \
     context="Architecture modernization with [constraints]" \
     includeRecommendations=true \
     analysisDepth="comprehensive"
   ```

2. **Phased Migration Strategy**:
   - Identify migration phases with minimal risk
   - Calculate cost and timeline for each phase
   - Design rollback strategies for each phase
   - Plan parallel system operation periods

### Phase 4: Architecture Decision Intelligence

#### Step 7: Cost-Aware Decision Framework
Apply intelligent decision making to architecture choices:

1. **Decision Matrix Generation**:
   ```
   Decision Score = (Technical_Fit * 0.3) + 
                   (Cost_Efficiency * 0.25) + 
                   (Scalability * 0.2) + 
                   (Maintainability * 0.15) + 
                   (Risk_Level * 0.1)
   ```

2. **Alternative Architecture Analysis**:
   - Generate multiple viable architecture options
   - Compare costs, benefits, and risks
   - Model long-term implications
   - Provide implementation guidance

3. **Risk Assessment and Mitigation**:
   - Identify architectural risks and failure modes
   - Calculate risk impact and probability
   - Suggest risk mitigation strategies
   - Estimate risk mitigation costs

#### Step 8: Implementation Roadmap Intelligence
Create intelligent implementation plans:

1. **Resource Allocation Optimization**:
   - Team skill requirements analysis
   - Timeline optimization based on complexity
   - Cost distribution across project phases
   - Resource constraint identification

2. **Integration Strategy**:
   - Identify integration points and challenges
   - Plan backward compatibility requirements
   - Design data migration strategies
   - Schedule integration testing phases

### Phase 5: Architecture Validation and Monitoring

#### Step 9: Architecture Quality Validation
Validate architecture decisions with intelligence:

1. **Architecture Pattern Compliance**:
   - Verify implementation follows recommended patterns
   - Check for pattern anti-patterns or violations
   - Validate architectural principles adherence
   - Monitor pattern evolution over time

2. **Performance Impact Analysis**:
   - Model performance characteristics
   - Identify potential performance bottlenecks
   - Recommend performance optimization strategies
   - Set performance monitoring and alerting

#### Step 10: Comprehensive Architecture Documentation
Generate intelligent architecture documentation:

```markdown
## Architecture Analysis Report - AI Enhanced

### Executive Summary
- **Architecture Scope**: [scope_analyzed]
- **Overall Health Score**: [calculated_score]/100
- **Cost Optimization Potential**: [savings_potential]
- **Recommended Investment**: $[investment_amount]
- **Expected ROI**: [roi_percentage]% over [timeframe]

### Intelligence Analysis Metrics
- **Analysis Cost**: $[total_analysis_cost]
- **Model Efficiency**: [optimized_decisions]/[total_decisions] decisions optimized
- **Time Saved**: [estimated_time_saved] hours through AI assistance
- **Decision Confidence**: [average_confidence_score]% average confidence

### Architecture Pattern Analysis
[AI-generated comprehensive pattern analysis]

### Cost-Benefit Analysis
[Detailed cost analysis with optimization recommendations]

### Migration Strategy
[Phased migration plan with timelines and costs]

### Risk Assessment
[Risk analysis with mitigation strategies and costs]

### Implementation Roadmap
[Detailed implementation plan with resource requirements]

### Monitoring and Success Metrics
[Key metrics to track architecture success]
```

## Integration with Architect Agent Commands

### Enhanced Architecture Commands
Integrate intelligence workflows with architect agent commands:

```yaml
commands:
  - analyze-architecture: Run comprehensive AI-powered architecture analysis
  - cost-model: Generate cost models for architecture decisions  
  - migration-plan: Create intelligent migration strategies
  - pattern-compliance: Validate architecture pattern compliance
  - scalability-analysis: Analyze system scalability with AI insights
  - risk-assessment: Generate AI-powered architecture risk analysis
  - optimize-costs: Find cost optimization opportunities in architecture
```

### Intelligence-Enhanced Design Process
```yaml
architecture-design-process:
  discovery:
    - System complexity assessment
    - Cost-benefit planning
    - Model selection optimization
  analysis:
    - Multi-dimensional pattern recognition
    - Cost-aware optimization analysis
    - Performance impact modeling
  planning:
    - Strategic recommendation generation
    - Migration complexity assessment
    - Decision framework application
  validation:
    - Architecture quality validation
    - Performance impact analysis
    - Documentation generation
```

## Advanced Architecture Intelligence Features

### Predictive Architecture Analysis
Use AI to predict architectural evolution needs:

1. **Growth Pattern Prediction**:
   - Analyze system growth trends
   - Predict scaling requirements
   - Recommend proactive architecture changes
   - Model future cost implications

2. **Technology Evolution Tracking**:
   - Monitor technology landscape changes
   - Predict obsolescence risks
   - Recommend technology updates
   - Plan modernization strategies

### Automated Architecture Monitoring
Continuous architecture health monitoring:

1. **Pattern Drift Detection**:
   - Monitor for architectural pattern violations
   - Detect gradual architecture degradation
   - Alert on architectural debt accumulation
   - Track pattern compliance metrics

2. **Performance Pattern Analysis**:
   - Monitor system performance patterns
   - Identify emerging bottlenecks
   - Recommend proactive optimizations
   - Track performance against architecture goals

## Success Criteria

### Architecture Effectiveness
- 90% accuracy in architecture pattern detection
- 85% of recommendations implemented successfully
- 40% reduction in architecture decision time

### Cost Optimization
- Stay within architecture analysis budget 95% of the time
- Achieve 30% cost optimization through intelligent recommendations
- ROI of 400% from architecture intelligence investments

### Quality Improvements  
- 95% architecture pattern compliance
- 50% reduction in architecture-related defects
- 60% improvement in system scalability metrics

## Error Handling and Fallbacks

### Intelligence Service Failures
1. **Pattern Analysis Unavailable**: Use traditional architecture review
2. **Cost Modeling Failure**: Use historical cost data
3. **AI Recommendations Unavailable**: Fall back to expert architect review

### Budget and Resource Constraints  
1. **Budget Exceeded**: Switch to basic analysis mode
2. **Time Constraints**: Prioritize critical architecture decisions
3. **Team Capacity**: Adjust recommendations to available resources

## Usage Examples

### New System Architecture Design
```bash
# Comprehensive architecture analysis for new system
*analyze-architecture scope="system" \
  cost_budget="$8.00" \
  optimization_goals=["scalability", "cost", "maintainability"] \
  analysis_depth="comprehensive" \
  include_patterns=true \
  generate_migration_plan=false
```

### Legacy System Modernization
```bash  
# Legacy modernization with migration planning
*analyze-architecture scope="enterprise" \
  cost_budget="$12.00" \
  optimization_goals=["maintainability", "performance"] \
  analysis_depth="comprehensive" \
  include_patterns=true \
  generate_migration_plan=true
```

### Component Architecture Review
```bash
# Focused component analysis
*analyze-architecture scope="component" \
  cost_budget="$4.00" \
  optimization_goals=["performance", "scalability"] \
  analysis_depth="detailed" \
  include_patterns=true \
  generate_migration_plan=false
```

This intelligent architect workflow transforms traditional architecture processes by adding AI-powered analysis, cost-aware decision making, and predictive insights while maintaining rigorous architectural principles and practices.