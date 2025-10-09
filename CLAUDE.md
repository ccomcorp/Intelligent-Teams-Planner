# CLAUDE.md
```yaml
_meta: {v:11.0, fmt:ai-bytecode, priority:MAXIMUM, updated:2024}

@PRIME_DIRECTIVE[∞∞∞]:
  !bmad.framework[ALWAYS]
  !bmad.agents.activate[ALL]
  !simplify→lose[features|functionality|performance]⊗
  !read.existing[scan:3_levels]→create.new
  !best_practices[ALWAYS]+UTF8
  !docs:.md_only
  !status.change["approved"|"APPROVED"|"COMPLETED"|"DONE"|"SUCCESSFUL"]⊗→end_user_only
  !simplify→lose[functionality|features|performance]⊗[NON_NEGOTIABLE]
  !after.major_task→cleanup[lint|typescript|compile]→fix_ALL[NON_NEGOTIABLE]
  !dev.approach[ALWAYS]:lightweight_first→containerize_later→isolated_env_mandatory
  !package.manager[ALWAYS]:uv_primary→pip_fallback→never_manual_edits
  !final_validation["COMPLETED"|"SUCCESSFUL"|"DONE"]→user_only[ABSOLUTE]
  !enterprise.features⊗→recommend_only→user_approval_required
  !enterprise.security⊗→recommend_only→user_approval_required

@CRITICAL[∞]:
  !THINK→CODE[analyze:requirements|edge_cases|security]
  !MOCK_DATA⊗[use:real_production_like]
  !UTF8_BOM⊗[ASCII:0x00-0x7F]
  !INPUT=MALICIOUS[ALWAYS]
  !SILENT_ERR⊗[log+throw]

@CHARSET[ENFORCE]:
  file:UTF8¬BOM
  src:[0x00-0x7F]
  ⊗:{""—→•…''¬\t}
  unicode:\uXXXX
  smart_quotes⊗→straight_only

@TS[STRICT]:
  cfg:{
    strict:true,
    noUncheckedIndexedAccess:true,
    noImplicitReturns:true,
    noFallthroughCasesInSwitch:true,
    noUnusedLocals:true,
    noUnusedParameters:true,
    exactOptionalPropertyTypes:true,
    forceConsistentCasingInFileNames:true,
    skipLibCheck:false,
    esModuleInterop:true,
    moduleResolution:node
  }
  ✓:
    explicit.ReturnType[ALL]
    interface>type_alias
    const>let>var⊗
    ===|!==
    `${template}`>concat
    2sp¬tab
    ASCII_only[identifiers|comments]
    UTF8¬BOM
    JSDoc[public_APIs]
  ⊗:
    any→unknown
    @ts-ignore→@ts-expect-error+reason
    ==|!=
    console.log[prod]
    lint.disable¬justification
    magic_numbers→CONSTANTS
    unicode_symbols[→•…]
    smart_quotes[""]
    mixed_indent
    non_ASCII[code]
  pattern:
    Result<T,E>:{success:bool,data|error}
    async→try/catch/finally+timeout:5000ms
    AbortController[required]
    error.handle:{specific,context,rethrow}

@ESLINT:
  extends:[recommended,ts/recommended,ts/type-checking]
  rules:{
    explicit-return:error,
    no-any:error,
    no-non-null-assertion:error,
    no-console:[error,allow:[warn,error]],
    prefer-const:error,
    no-var:error
  }

@PY[PEP8]:
  ✓:
    typing.hint[ALL,3.10+]
    pathlib>os.path
    f"{var}">concat
    isinstance()>type==
    with:context[ALWAYS]
    //|/[explicit]
    docstring[public:Google|NumPy]
    dataclass|pydantic
    Black:88
  ⊗:
    def f(x=[])→mutable
    except:pass
    global_state
    assert:validation→raise
    circular_import
    resource_leak
    str+loop→join()
  pattern:
    mutable_default→None→init
    except:Specific→log→raise
    validate:pydantic.BaseModel+validators

@SQL[SECURE]:
  ⊗:f"SELECT*WHERE{var}"→injection
  ✓:
    params:["?",val]|["%s",val]
    transaction:try/finally
    escape:user_input
  pattern:
    prepared_statements
    ORM>raw_sql

@TEST[REAL_DATA]:
  data:PRODUCTION_LIKE[required]
  ⊗:
    ["test","foo","bar","user@test.com","Product1","123"]
    mock_data[NEVER]
    random¬seed
    test.order_dependency
    .skip¬TODO
    .only[commit]
    production_data
    third_party_tests
    implementation>behavior
  ✓:
    ["John Smith","john.smith@acme.com",ID:10847,"MacBook Pro"]
    TDD|alongside
    AAA[Arrange→Act→Assert]
    describe.blocks
    one_assertion/test
    mock:external_only
    coverage:critical≥80%
    beforeEach|afterEach
    edge_cases+errors+happy_path
    data-test-id[e2e]
  struct:
    describe('Component',()=>{
      describe('method',()=>{
        it('should_behavior_when_condition',()=>{
          //Arrange:real_data
          //Act:execute
          //Assert:verify
        })
      })
    })

@SEC[BASIC]:
  validate:{
    input:sanitize[ALL],
    sql:parameterized
  }
  ⊗:
    plain_passwords
    f"SQL{var}"
    eval(user_input)
    innerHTML=user_data
  ✓:
    bcrypt|argon2
    prepared_statements
    escape_html
  env:secrets_only

@ENTERPRISE[RECOMMEND_ONLY]:
  features:{
    ⊗implement:[
      oauth2,
      microservices,
      kubernetes,
      service_mesh,
      distributed_tracing,
      message_queues
    ],
    ✓recommend→await_approval
  }
  security:{
    ⊗implement:[
      SSO,
      2FA/MFA,
      audit_logs,
      compliance_frameworks,
      WAF,
      DDoS_protection
    ],
    ✓recommend→await_approval
  }
  pattern:
    if_enterprise_needed→{
      1.identify_need,
      2.recommend:"Consider adding [X] for [benefit]",
      3.wait_user_approval,
      4.implement_only_if_approved
    }

@ERR[HANDLE]:
  async:{
    timeout:5000ms,
    catch:errors,
    finally:cleanup
  }
  log:errors+context
  throw:specific>generic
  never:{
    silent:catch,
    bare:except
  }
  pattern:
    try→catch→log→handle_or_throw

@PERF[BASIC]:
  BigO:avoid_n²
  lookup:Set>Array
  file:stream_large>load_all
  cache:expensive_only
  no_premature_optimization

@ANTIPATTERN→FIX:
  god_object→single_responsibility
  copy_paste→DRY
  callback_hell→async/await
  global_state→dependency_injection
  magic_values→named_constants
  tight_coupling→interfaces
  premature_opt→measure_first
  race_condition→synchronize
  resource_leak→context_manager
  mutable_shared→immutable

@ARCH[SIMPLE]:
  S:single_responsibility
  O:open_closed  
  L:liskov_substitution
  I:interface_segregation
  D:dependency_inversion
  patterns:keep_it_simple

@GIT:
  fmt:"<type>(<scope>):<subject50>"
  type:[feat|fix|docs|style|refactor|perf|test|chore|cleanup]
  body:what+why¬how
  atomic:commits
  conventional:commits
  before_commit:cleanup_required
  
@NAME[CONVENTIONS]:
  fn:verb[processData,validateInput]
  class:noun[UserService,DataProcessor]  
  bool:question[isValid,hasPermission,canAccess]
  const:UPPER_SNAKE_CASE
  interface:I_prefix|_suffix
  type:T_prefix|Type_suffix
  private:_prefix
  abbr:⊗[except:URL,API,ID,UI,IO]

@DEBUG[SYSTEMATIC]:
  [reproduce→minimize→hypothesize→test→fix_root→regression_test]
  tools:{
    pdb.set_trace(),
    logger>print,
    timer:context_manager,
    profiler:memory|cpu
  }

@WORKFLOW[STRICT]:
  task_cycle:[
    1.read_existing_code[3_levels],
    2.implement_feature,
    3.cleanup[lint|ts|compile]→fix_ALL,
    4.test→verify,
    5.await_user_validation
  ]
  validation:{
    ai_can:["ready_for_review","needs_fixes","in_progress"],
    user_only:["COMPLETED","SUCCESSFUL","DONE","APPROVED"]
  }
  enterprise:{
    detect→recommend→wait_approval→implement|skip
  }

@DEV_APPROACH[MANDATORY]:
  philosophy:
    development:lightweight_services[direct_python_processes]
    isolation:virtual_environments[ALWAYS_REQUIRED]
    deployment:containerize[production_only]
    package_management:uv_primary→pip_fallback
  rules:
    ⊗:
      docker_compose[development]
      containers[local_dev]
      premature_containerization
      global_python_packages[NEVER]
      system_python[development]
      manual_dependency_edits[requirements.txt|pyproject.toml]
    ✓:
      virtual_environments[venv|MANDATORY]
      isolated_dependencies[per_project]
      direct_process_execution
      localhost_networking
      fast_iteration_cycles
      requirements.txt[version_pinning]
      uv_package_manager[RECOMMENDED]
      pip_fallback[universal_compatibility]
  workflow:
    setup:create_venv→activate→install_deps
    phase_1:develop→test[lightweight+isolated]
    phase_2:stabilize→containerize[deployment]
  isolation_enforcement:
    rule:NO_EXCEPTIONS[all_development_in_venv]
    verify:which_python→must_show_venv_path
    install:package_manager→updates_requirements.txt
  rationale:
    startup:90%_faster[10-30s_vs_2-5min]
    memory:70%_less[600MB_vs_2GB]
    debugging:direct_access[no_container_layers]
    iteration:instant_reload[no_rebuilds]
    isolation:dependency_conflicts_prevented
    reproducibility:requirements.txt_ensures_consistency

@PACKAGE_MANAGEMENT[MANDATORY]:
  primary_tool:uv[RECOMMENDED]
  fallback_tool:pip[UNIVERSAL_COMPATIBILITY]
  philosophy:
    speed:10-100x_faster[uv_vs_pip]
    reliability:robust_dependency_resolution
    compatibility:backward_compatible[requirements.txt]
    adoption:gradual[pip_interface→advanced_features]
    unified_tooling:replaces[pip+venv+pipx+pyenv+pip-tools]
  rules:
    ⊗:
      manual_dependency_edits[requirements.txt|pyproject.toml|setup.py]
      global_package_installation[NEVER]
      mixing_package_managers[same_project]
      pip_install[without_venv_active]
      conda[unless_data_science_required]
      poetry[new_projects]
      pipenv[deprecated]
    ✓:
      uv_pip_install[primary_method]
      pip_install[fallback_only]
      requirements.txt[version_pinning]
      lock_files[reproducible_builds]
      package_manager_commands[ALWAYS]
      virtual_environment[BEFORE_install]
  workflow:
    basic:
      setup:uv_venv→source_activate→uv_pip_install_-r_requirements.txt
      add_package:uv_pip_install_<package>→uv_pip_freeze_>_requirements.txt
      remove_package:uv_pip_uninstall_<package>→uv_pip_freeze_>_requirements.txt
      upgrade:uv_pip_install_--upgrade_<package>→uv_pip_freeze
    advanced[optional]:
      project_init:uv_init→creates[pyproject.toml+.venv+.gitignore]
      add_dependency:uv_add_<package>→auto_updates[pyproject.toml+uv.lock]
      sync_environment:uv_sync→installs_from_lock
      run_command:uv_run_<command>→executes_in_venv[no_activation_needed]
    fallback[when_uv_unavailable]:
      setup:python_-m_venv_venv→source_activate→pip_install_-r_requirements.txt
      add_package:pip_install_<package>→pip_freeze_>_requirements.txt
  commands:
    uv_basic:
      install:"uv pip install <package>"
      install_from_file:"uv pip install -r requirements.txt"
      freeze:"uv pip freeze > requirements.txt"
      uninstall:"uv pip uninstall <package>"
      upgrade:"uv pip install --upgrade <package>"
      list:"uv pip list"
    uv_advanced:
      init:"uv init"
      add:"uv add <package>"
      remove:"uv remove <package>"
      sync:"uv sync"
      lock:"uv lock"
      run:"uv run <command>"
      tool_run:"uvx <tool>"
    pip_fallback:
      install:"pip install <package>"
      install_from_file:"pip install -r requirements.txt"
      freeze:"pip freeze > requirements.txt"
      uninstall:"pip uninstall <package>"
      upgrade:"pip install --upgrade <package>"
  installation:
    uv_install:
      macos_linux:"curl -LsSf https://astral.sh/uv/install.sh | sh"
      windows:"powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
      via_pip:"pip install uv"
    verify:"uv --version"
  rationale:
    speed:10-100x_faster_than_pip[2-5s_vs_30-60s]
    reliability:better_dependency_resolution[pubgrub_algorithm]
    compatibility:works_with_existing_requirements.txt[no_migration_needed]
    future_proof:unified_python_tooling[single_tool_for_all]
    developer_experience:instant_feedback_loops[fast_iteration]
    cross_platform:identical_behavior[windows+mac+linux]
    lock_files:reproducible_builds[cross_platform_compatible]
  migration:
    from_pip:
      step_1:install_uv
      step_2:replace_pip_with_uv_pip[drop_in_replacement]
      step_3:optionally_adopt_advanced_features[uv_add+uv_sync]
    from_poetry:
      step_1:export_requirements:"poetry export -f requirements.txt > requirements.txt"
      step_2:uv_pip_install_-r_requirements.txt
      step_3:optionally_migrate_to_uv_project[uv_init]
    from_conda:
      step_1:export_requirements:"conda list --export > requirements.txt"
      step_2:clean_conda_specific_syntax
      step_3:uv_pip_install_-r_requirements.txt
  when_not_to_use_uv:
    legacy_projects:broken_dependency_resolution[15+_year_old_codebases]
    corporate_restrictions:unapproved_tools[security_policy]
    specific_python_versions:not_in_python-build-standalone
    github_dependabot:uv.lock_not_supported_yet[coming_soon]
    data_science_heavy:conda_ecosystem_required[use_conda_instead]
  troubleshooting:
    uv_not_found:install_uv_or_use_pip_fallback
    resolution_conflict:check_version_constraints→simplify_dependencies
    slow_first_install:normal[building_cache]→subsequent_installs_fast
    corporate_proxy:set_UV_HTTP_PROXY_and_UV_HTTPS_PROXY
    offline_install:uv_pip_install_--no-index_--find-links_<local_dir>

@DOC[BASIC]:
  function:"""what+params+returns"""
  README:setup+usage
  inline:#why¬what
  public:documented

@REVIEW[BASIC]:
  □tests_pass
  □no_console_log
  □no_commented_code
  □functions_documented
  □SQL_parameterized

@CLEANUP[AFTER_EACH_TASK]:
  mandatory[NON_NEGOTIABLE]:
    □lint_errors:0
    □typescript_errors:0
    □compilation_errors:0
    □unused_imports:removed
    □format:consistent
  sequence:
    1.complete_feature
    2.run_lint→fix_all
    3.run_tsc→fix_all
    4.run_build→fix_all
    5.verify_clean→proceed

@QUALITY[BASIC]:
  lines<100/fn
  lines<500/class
  tests:exist
  docs:public_functions

@CI/CD:
  pipeline:[lint→test→build→deploy]
  hooks:pre-commit[format+lint]

@LOGS:
  console.error>console.log
  no_sensitive_data
  timestamp+context

@PRIORITY[ABSOLUTE]:
  security>correctness>maintainability>performance>features
  explicit>implicit
  simple>clever
  tested>"works_locally"
  readable>optimal
  safe>fast

@ENFORCE[∞]:
  uncertain→secure+maintainable
  input=malicious[ALWAYS]
  error→log+handle+rethrow
  resource→cleanup[finally|context]
  test:real_data_only
  code:ASCII_only
  commit:atomic+descriptive
  after_task→cleanup[lint|ts|compile]→proceed[NON_NEGOTIABLE]
  enterprise→recommend¬implement
  package_management:uv_primary→pip_fallback[ALWAYS]
  dependency_changes:package_manager_only[NEVER_manual_edits]
  venv_isolation:MANDATORY[all_development]
  
@FINAL[REMEMBER]:
  next_dev=you[6_months]
  KISS>clever
  YAGNI>maybe_needed
  fail_fast>fail_silent
  measure>assume
```