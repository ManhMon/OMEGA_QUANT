"""Audit script to identify true orphan/unimported python modules in the src/ directory, resolving relative imports."""
import os
import ast
import pathlib
import sys

def parse_file_imports(file_path, module_name, is_init=False):
    """Parse all absolute and relative imports from a file."""
    imports = set()
    try:
        content = file_path.read_text(encoding='utf-8-sig', errors='ignore')
        tree = ast.parse(content)
    except Exception:
        return imports

    module_parts = module_name.split('.') if module_name else []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imported_mod = node.module or ''
            if node.level > 0:
                # Relative import
                # For __init__.py, level 1 refers to sibling files (same directory).
                # For regular files, level 1 refers to parent directory.
                strip_level = node.level - 1 if is_init else node.level
                if strip_level > 0 and len(module_parts) >= strip_level:
                    base_parts = module_parts[:-strip_level]
                else:
                    base_parts = module_parts
                
                if imported_mod:
                    resolved_parts = base_parts + imported_mod.split('.')
                else:
                    resolved_parts = base_parts
                imports.add('.'.join(resolved_parts))
                for alias in node.names:
                    imports.add('.'.join(resolved_parts + [alias.name]))
            else:
                # Absolute import
                if imported_mod:
                    imports.add(imported_mod)
                    for alias in node.names:
                        imports.add(imported_mod + '.' + alias.name)
    return imports

def main():
    root = pathlib.Path('.').resolve()
    src_dir = root / 'src'
    apps_dir = root / 'apps'
    scripts_dir = root / 'scripts'

    if not src_dir.exists():
        print("ERROR: src/ directory not found.")
        sys.exit(1)

    # 1. Map all python files in src/ to their module names
    src_files = {}
    for p in src_dir.rglob('*.py'):
        if p.name == '__init__.py':
            continue
        rel = p.relative_to(src_dir)
        mod_parts = list(rel.parts)
        mod_parts[-1] = p.stem
        mod_name = '.'.join(mod_parts)
        src_files[mod_name] = p

    # 2. Collect all imports across src/, apps/, and scripts/
    all_imports = set()
    
    # First, collect from src/ with relative import resolution
    for p in src_dir.rglob('*.py'):
        rel = p.relative_to(src_dir)
        mod_parts = list(rel.parts)
        is_init = p.name == '__init__.py'
        if is_init:
            mod_parts = mod_parts[:-1]
        else:
            mod_parts[-1] = p.stem
        file_mod_name = '.'.join(mod_parts)
        all_imports.update(parse_file_imports(p, file_mod_name, is_init=is_init))
        
    # Then, collect from apps/ and scripts/ (always absolute imports)
    for directory in [apps_dir, scripts_dir]:
        if not directory.exists():
            continue
        for p in directory.rglob('*.py'):
            all_imports.update(parse_file_imports(p, ''))

    # 3. Find unimported modules in src/
    unimported = {}
    for mod_name, file_path in src_files.items():
        is_imported = False
        for imp in all_imports:
            if imp == mod_name or imp.startswith(mod_name + '.'):
                is_imported = True
                break
        
        if not is_imported:
            parts = list(file_path.relative_to(src_dir).parts)
            group = parts[0] if len(parts) > 1 else 'root'
            if group not in unimported:
                unimported[group] = []
            unimported[group].append((mod_name, str(file_path.relative_to(root))))

    # 4. Print report
    print("========================================================================")
    print("WIRING AUDIT (RESOLVED RELATIVE IMPORTS) - UNIMPORTED/ORPHAN MODULES IN src/")
    print("========================================================================")
    total = 0
    for group, modules in sorted(unimported.items()):
        print(f"\nPackage: src/{group} ({len(modules)} orphan files)")
        print("-" * 72)
        for mod, path in sorted(modules):
            print(f"  - {mod} -> {path}")
            total += 1
    print("\n========================================================================")
    print(f"Total unimported files in src/: {total}")
    print("========================================================================")

if __name__ == '__main__':
    main()
