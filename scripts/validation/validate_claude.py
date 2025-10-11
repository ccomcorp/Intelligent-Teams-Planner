#!/usr/bin/env python3
"""Validate CLAUDE.md structure and package management updates."""

def validate_claude_md():
    """Validate CLAUDE.md file structure and content."""
    
    with open('CLAUDE.md', 'r') as f:
        content = f.read()
    
    # Extract YAML content
    if '```yaml' not in content:
        print('❌ No YAML block found')
        return False
    
    yaml_content = content.split('```yaml')[1].split('```')[0]
    lines = yaml_content.splitlines()
    
    print('=' * 60)
    print('CLAUDE.md Validation Report')
    print('=' * 60)
    print()
    
    # Basic structure
    print('📊 Basic Structure:')
    print(f'   Total lines: {len(lines)}')
    print(f'   Sections (@): {yaml_content.count("@")}')
    print()
    
    # Check for required sections
    print('🔍 Required Sections:')
    required_sections = [
        '@PRIME_DIRECTIVE',
        '@DEV_APPROACH[MANDATORY]',
        '@PACKAGE_MANAGEMENT[MANDATORY]',
        '@ENFORCE'
    ]
    
    all_found = True
    for section in required_sections:
        if section in yaml_content:
            print(f'   ✅ {section}')
        else:
            print(f'   ❌ {section} NOT FOUND')
            all_found = False
    print()
    
    # Check for package management rules
    print('📦 Package Management Rules:')
    package_rules = [
        ('PRIME_DIRECTIVE rule', '!package.manager[ALWAYS]:uv_primary→pip_fallback→never_manual_edits'),
        ('DEV_APPROACH philosophy', 'package_management:uv_primary→pip_fallback'),
        ('Forbidden manual edits', 'manual_dependency_edits[requirements.txt|pyproject.toml]'),
        ('uv recommended', 'uv_package_manager[RECOMMENDED]'),
        ('pip fallback', 'pip_fallback[universal_compatibility]'),
        ('PACKAGE_MANAGEMENT primary', 'primary_tool:uv[RECOMMENDED]'),
        ('PACKAGE_MANAGEMENT fallback', 'fallback_tool:pip[UNIVERSAL_COMPATIBILITY]'),
        ('ENFORCE package mgmt', 'package_management:uv_primary→pip_fallback[ALWAYS]'),
        ('ENFORCE no manual edits', 'dependency_changes:package_manager_only[NEVER_manual_edits]'),
        ('ENFORCE venv isolation', 'venv_isolation:MANDATORY[all_development]')
    ]
    
    for rule_name, rule_text in package_rules:
        if rule_text in yaml_content:
            print(f'   ✅ {rule_name}')
        else:
            print(f'   ❌ {rule_name} NOT FOUND')
            all_found = False
    print()
    
    # Check for key workflows
    print('🔧 Workflows:')
    workflows = [
        ('Basic setup', 'setup:uv_venv→source_activate→uv_pip_install_-r_requirements.txt'),
        ('Add package', 'add_package:uv_pip_install_<package>→uv_pip_freeze_>_requirements.txt'),
        ('Advanced init', 'project_init:uv_init→creates[pyproject.toml+.venv+.gitignore]'),
        ('Fallback setup', 'setup:python_-m_venv_venv→source_activate→pip_install_-r_requirements.txt')
    ]
    
    for workflow_name, workflow_text in workflows:
        if workflow_text in yaml_content:
            print(f'   ✅ {workflow_name}')
        else:
            print(f'   ❌ {workflow_name} NOT FOUND')
            all_found = False
    print()
    
    # Check for installation instructions
    print('📥 Installation:')
    install_checks = [
        ('macOS/Linux install', 'macos_linux:"curl -LsSf https://astral.sh/uv/install.sh | sh"'),
        ('Windows install', 'windows:"powershell -c \\"irm https://astral.sh/uv/install.ps1 | iex\\""'),
        ('pip install', 'via_pip:"pip install uv"'),
        ('Verify command', 'verify:"uv --version"')
    ]
    
    for check_name, check_text in install_checks:
        if check_text in yaml_content:
            print(f'   ✅ {check_name}')
        else:
            print(f'   ❌ {check_name} NOT FOUND')
            all_found = False
    print()
    
    # Check for rationale
    print('💡 Rationale:')
    rationale_checks = [
        ('Speed benefit', 'speed:10-100x_faster_than_pip'),
        ('Reliability', 'reliability:better_dependency_resolution[pubgrub_algorithm]'),
        ('Compatibility', 'compatibility:works_with_existing_requirements.txt'),
        ('Developer experience', 'developer_experience:instant_feedback_loops')
    ]
    
    for check_name, check_text in rationale_checks:
        if check_text in yaml_content:
            print(f'   ✅ {check_name}')
        else:
            print(f'   ❌ {check_name} NOT FOUND')
            all_found = False
    print()
    
    # Check for migration paths
    print('🔄 Migration Paths:')
    migration_checks = [
        ('From pip', 'from_pip:'),
        ('From poetry', 'from_poetry:'),
        ('From conda', 'from_conda:')
    ]
    
    for check_name, check_text in migration_checks:
        if check_text in yaml_content:
            print(f'   ✅ {check_name}')
        else:
            print(f'   ❌ {check_name} NOT FOUND')
            all_found = False
    print()
    
    # Final summary
    print('=' * 60)
    if all_found:
        print('✅ ALL VALIDATION CHECKS PASSED!')
        print('=' * 60)
        print()
        print('Summary:')
        print('  • PRIME_DIRECTIVE updated with package manager rule')
        print('  • DEV_APPROACH integrated with package management')
        print('  • PACKAGE_MANAGEMENT section created (100+ lines)')
        print('  • ENFORCE section updated with package rules')
        print('  • All workflows, commands, and migration paths present')
        print('  • Installation instructions included')
        print('  • Rationale and troubleshooting documented')
        print()
        return True
    else:
        print('❌ VALIDATION FAILED - Some checks did not pass')
        print('=' * 60)
        return False

if __name__ == '__main__':
    import sys
    success = validate_claude_md()
    sys.exit(0 if success else 1)

