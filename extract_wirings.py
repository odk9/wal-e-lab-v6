"""
extract_wirings.py — Extracteur AST de wirings (flux inter-modules) pour la KB Wal-e V6.

Analyse un repo Python cloné localement et extrait 3 types de wirings :
  1. import_graph   — qui importe quoi (AST pur, 100% déterministe)
  2. dependency_chain — injection de dépendances FastAPI (Depends), middleware, lifespan
  3. flow_pattern   — séquences d'opérations pour une feature (route → crud → model → response)

Usage:
    from extract_wirings import extract_all_wirings
    wirings = extract_all_wirings("/path/to/repo", package_name="src")

Chaque wiring retourné est un dict prêt à être inséré dans Qdrant (collection `wirings`).
"""

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ImportEdge:
    """Un import entre deux modules."""
    source_file: str          # fichier qui importe (ex: "routes.py")
    target_module: str        # module importé (ex: "crud", "models", "database")
    imported_names: list[str] # noms importés (ex: ["create_xxx", "get_xxx"])

@dataclass
class DependsCall:
    """Un appel Depends() dans une signature de route."""
    route_file: str           # fichier de la route
    function_name: str        # nom de la route (ex: "create_xxx")
    parameter_name: str       # nom du paramètre (ex: "db", "current_user")
    depends_on: str           # fonction injectée (ex: "get_db", "get_current_user")

@dataclass
class RouteDefinition:
    """Une route HTTP définie dans un fichier."""
    file: str
    function_name: str
    method: str               # "get", "post", "put", "patch", "delete"
    path: str                 # "/", "/{xxx_id}", etc.
    depends: list[DependsCall] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)  # fonctions appelées dans le body

@dataclass
class RouterInclude:
    """Un app.include_router() dans main.py."""
    file: str
    router_module: str        # module d'où vient le router
    prefix: str               # prefix ajouté (ex: "/api/v1")


# ---------------------------------------------------------------------------
# AST Visitors
# ---------------------------------------------------------------------------

class ImportVisitor(ast.NodeVisitor):
    """Extrait tous les imports locaux (from X import Y) d'un fichier."""

    def __init__(self, local_modules: set[str]) -> None:
        self.local_modules = local_modules
        self.edges: list[ImportEdge] = []
        self._current_file = ""

    def analyze(self, source_file: str, tree: ast.AST) -> list[ImportEdge]:
        self._current_file = source_file
        self.edges = []
        self.visit(tree)
        return self.edges

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            return
        # Résout les imports relatifs et locaux
        module_parts = node.module.replace(".", "/").split("/")
        base_module = module_parts[-1] if module_parts else node.module

        # Vérifie si c'est un module local du projet
        if base_module in self.local_modules or node.level > 0:
            names = [alias.name for alias in node.names if alias.name != "*"]
            if names:
                self.edges.append(ImportEdge(
                    source_file=self._current_file,
                    target_module=base_module,
                    imported_names=names,
                ))
        self.generic_visit(node)


class DependsVisitor(ast.NodeVisitor):
    """Extrait les Depends() des signatures de fonctions async."""

    def __init__(self) -> None:
        self.depends_calls: list[DependsCall] = []
        self.routes: list[RouteDefinition] = []
        self._current_file = ""

    def analyze(self, source_file: str, tree: ast.AST) -> None:
        self._current_file = source_file
        self.depends_calls = []
        self.routes = []
        self.visit(tree)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._extract_depends(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._extract_depends(node)
        self.generic_visit(node)

    def _extract_depends(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Extrait les Depends() de la signature + les appels dans le body."""
        depends_list: list[DependsCall] = []

        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation is None:
                continue
            # Cherche Depends(...) dans la default value
            # Pattern: param: Type = Depends(func)
            # On cherche dans les defaults

        # Chercher dans les defaults (args positionnels)
        defaults = node.args.defaults
        args_with_defaults = node.args.args[-len(defaults):] if defaults else []
        for arg_node, default in zip(args_with_defaults, defaults):
            dep = self._parse_depends_call(node.name, arg_node, default)
            if dep:
                depends_list.append(dep)

        # Chercher dans kw_defaults (keyword-only args)
        for arg_node, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if default is None:
                continue
            dep = self._parse_depends_call(node.name, arg_node, default)
            if dep:
                depends_list.append(dep)

        # Extraire les appels de fonctions dans le body
        calls = self._extract_calls(node)

        if depends_list or self._has_route_decorator(node):
            route_method, route_path = self._parse_route_decorator(node)
            self.routes.append(RouteDefinition(
                file=self._current_file,
                function_name=node.name,
                method=route_method,
                path=route_path,
                depends=depends_list,
                calls=calls,
            ))
        self.depends_calls.extend(depends_list)

    def _parse_depends_call(
        self,
        func_name: str,
        arg_node: ast.arg,
        default: ast.expr,
    ) -> DependsCall | None:
        """Parse un default value pour trouver Depends(xxx)."""
        if isinstance(default, ast.Call):
            func = default.func
            # Depends(get_db) ou fastapi.Depends(get_db)
            if isinstance(func, ast.Name) and func.id == "Depends":
                dep_name = self._get_call_arg_name(default)
                if dep_name:
                    return DependsCall(
                        route_file=self._current_file,
                        function_name=func_name,
                        parameter_name=arg_node.arg,
                        depends_on=dep_name,
                    )
            elif isinstance(func, ast.Attribute) and func.attr == "Depends":
                dep_name = self._get_call_arg_name(default)
                if dep_name:
                    return DependsCall(
                        route_file=self._current_file,
                        function_name=func_name,
                        parameter_name=arg_node.arg,
                        depends_on=dep_name,
                    )
        return None

    def _get_call_arg_name(self, call: ast.Call) -> str | None:
        """Extrait le nom de la fonction passée en argument à Depends()."""
        if call.args:
            arg = call.args[0]
            if isinstance(arg, ast.Name):
                return arg.id
            if isinstance(arg, ast.Attribute):
                return ast.unparse(arg)
        return None

    def _has_route_decorator(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Vérifie si la fonction a un décorateur @router.get/post/etc."""
        methods = {"get", "post", "put", "patch", "delete"}
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr in methods:
                    return True
        return False

    def _parse_route_decorator(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str]:
        """Extrait method et path du décorateur de route."""
        methods = {"get", "post", "put", "patch", "delete"}
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr in methods:
                    method = dec.func.attr
                    path = ""
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        path = str(dec.args[0].value)
                    return method, path
        return "unknown", ""

    def _extract_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extrait les noms de fonctions appelées dans le body (1 niveau)."""
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
                elif isinstance(child.func, ast.Await) and isinstance(child.func.value, ast.Call):
                    inner = child.func.value.func
                    if isinstance(inner, ast.Name):
                        calls.append(inner.id)
                    elif isinstance(inner, ast.Attribute):
                        calls.append(inner.attr)
        # Aussi gérer les await directs
        for child in ast.walk(node):
            if isinstance(child, ast.Await) and isinstance(child.value, ast.Call):
                func = child.value.func
                if isinstance(func, ast.Name) and func.id not in calls:
                    calls.append(func.id)
                elif isinstance(func, ast.Attribute) and func.attr not in calls:
                    calls.append(func.attr)
        return list(dict.fromkeys(calls))  # déduplique en préservant l'ordre


class LifespanVisitor(ast.NodeVisitor):
    """Extrait les lifespan events (startup/shutdown) depuis main.py."""

    def __init__(self) -> None:
        self.lifespan_calls: list[str] = []
        self.router_includes: list[RouterInclude] = []
        self._current_file = ""

    def analyze(self, source_file: str, tree: ast.AST) -> None:
        self._current_file = source_file
        self.lifespan_calls = []
        self.router_includes = []
        self.visit(tree)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Cherche les fonctions avec @asynccontextmanager ou nommées "lifespan"
        if node.name == "lifespan" or any(
            (isinstance(d, ast.Name) and d.id == "asynccontextmanager")
            or (isinstance(d, ast.Attribute) and d.attr == "asynccontextmanager")
            for d in node.decorator_list
        ):
            # Extraire les appels avant yield
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        self.lifespan_calls.append(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        self.lifespan_calls.append(ast.unparse(child.func))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Cherche app.include_router(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "include_router":
            router_name = ""
            prefix = ""
            if node.args and isinstance(node.args[0], ast.Name):
                router_name = node.args[0].id
            elif node.args and isinstance(node.args[0], ast.Attribute):
                router_name = ast.unparse(node.args[0])
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = str(kw.value.value)
            if router_name:
                self.router_includes.append(RouterInclude(
                    file=self._current_file,
                    router_module=router_name,
                    prefix=prefix,
                ))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Main extraction functions
# ---------------------------------------------------------------------------

def find_python_files(repo_path: str, exclude_dirs: set[str] | None = None) -> list[Path]:
    """Trouve tous les fichiers .py d'un repo, excluant venv/tests/migrations."""
    if exclude_dirs is None:
        exclude_dirs = {".venv", "venv", "__pycache__", ".git", "migrations", "alembic"}

    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return sorted(files)


def get_local_modules(repo_path: str, python_files: list[Path]) -> set[str]:
    """Identifie les noms de modules locaux du projet."""
    modules: set[str] = set()
    for f in python_files:
        stem = f.stem
        if stem != "__init__":
            modules.add(stem)
    return modules


def extract_import_graph(
    repo_path: str,
    python_files: list[Path],
    local_modules: set[str],
) -> list[ImportEdge]:
    """Extrait le graphe d'imports entre modules locaux."""
    all_edges: list[ImportEdge] = []

    for fpath in python_files:
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError:
            continue

        rel_path = str(fpath.relative_to(repo_path))
        visitor = ImportVisitor(local_modules)
        edges = visitor.analyze(rel_path, tree)
        all_edges.extend(edges)

    return all_edges


def extract_depends_chains(
    repo_path: str,
    python_files: list[Path],
) -> tuple[list[DependsCall], list[RouteDefinition]]:
    """Extrait les Depends() et routes de tous les fichiers."""
    all_depends: list[DependsCall] = []
    all_routes: list[RouteDefinition] = []

    for fpath in python_files:
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError:
            continue

        rel_path = str(fpath.relative_to(repo_path))
        visitor = DependsVisitor()
        visitor.analyze(rel_path, tree)
        all_depends.extend(visitor.depends_calls)
        all_routes.extend(visitor.routes)

    return all_depends, all_routes


def extract_lifespan_and_includes(
    repo_path: str,
    python_files: list[Path],
) -> tuple[list[str], list[RouterInclude]]:
    """Extrait lifespan calls et router includes depuis main.py / app.py."""
    all_lifespan: list[str] = []
    all_includes: list[RouterInclude] = []

    # Cherche main.py, app.py, ou tout fichier contenant FastAPI()
    main_files = [f for f in python_files if f.stem in ("main", "app", "__init__")]
    if not main_files:
        # Fallback: cherche les fichiers contenant "FastAPI("
        for f in python_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "FastAPI(" in content:
                    main_files.append(f)
            except Exception:
                continue

    for fpath in main_files:
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError:
            continue

        rel_path = str(fpath.relative_to(repo_path))
        visitor = LifespanVisitor()
        visitor.analyze(rel_path, tree)
        all_lifespan.extend(visitor.lifespan_calls)
        all_includes.extend(visitor.router_includes)

    return all_lifespan, all_includes


# ---------------------------------------------------------------------------
# Wiring builders — transforment les données brutes en dicts Qdrant-ready
# ---------------------------------------------------------------------------

def build_import_graph_wiring(
    edges: list[ImportEdge],
    language: str = "python",
    framework: str = "fastapi",
    stack: str = "fastapi+sqlalchemy+pydantic_v2",
    source_repo: str = "",
    pattern_scope: str = "crud_simple",
) -> dict[str, Any] | None:
    """Construit un wiring de type import_graph."""
    if not edges:
        return None

    # Modules impliqués
    modules = sorted({e.source_file for e in edges} | {e.target_module for e in edges})

    # Connexions sous forme lisible
    connections: list[str] = []
    for e in edges:
        names_str = ", ".join(e.imported_names[:5])
        if len(e.imported_names) > 5:
            names_str += f" (+{len(e.imported_names) - 5} more)"
        connections.append(f"{e.source_file} → {e.target_module} ({names_str})")

    # Code example : les imports reformatés
    code_lines: list[str] = []
    code_lines.append("# === Import Graph ===")
    for e in edges:
        code_lines.append(f"# {e.source_file}:")
        code_lines.append(f"from {e.target_module} import {', '.join(e.imported_names)}")
        code_lines.append("")

    description = (
        f"Import graph for {pattern_scope} project. "
        f"{len(modules)} modules, {len(edges)} import edges. "
        f"Shows which module imports what from where."
    )

    return {
        "wiring_type": "import_graph",
        "description": description,
        "modules": modules,
        "connections": connections,
        "code_example": "\n".join(code_lines),
        "pattern_scope": pattern_scope,
        "language": language,
        "framework": framework,
        "stack": stack,
        "source_repo": source_repo,
    }


def build_dependency_chain_wiring(
    depends: list[DependsCall],
    routes: list[RouteDefinition],
    language: str = "python",
    framework: str = "fastapi",
    stack: str = "fastapi+sqlalchemy+pydantic_v2",
    source_repo: str = "",
    pattern_scope: str = "crud_simple",
) -> dict[str, Any] | None:
    """Construit un wiring de type dependency_chain."""
    if not depends:
        return None

    modules = sorted({d.route_file for d in depends})

    # Connexions : chaque injection
    connections: list[str] = []
    for d in depends:
        connections.append(
            f"{d.function_name}({d.parameter_name}) ← Depends({d.depends_on})"
        )

    # Code example
    code_lines: list[str] = ["# === Dependency Injection Chain ==="]
    seen: set[str] = set()
    for d in depends:
        key = f"{d.function_name}_{d.depends_on}"
        if key in seen:
            continue
        seen.add(key)
        code_lines.append(
            f"async def {d.function_name}("
            f"{d.parameter_name} = Depends({d.depends_on})"
            f"):"
        )
        code_lines.append(f"    # {d.depends_on} injected as {d.parameter_name}")
        code_lines.append("")

    # Résumé des fonctions injectées
    injected_funcs = sorted({d.depends_on for d in depends})
    description = (
        f"Dependency injection chain for {pattern_scope}. "
        f"Injected functions: {', '.join(injected_funcs)}. "
        f"{len(depends)} injection points across {len(modules)} files."
    )

    return {
        "wiring_type": "dependency_chain",
        "description": description,
        "modules": modules,
        "connections": connections,
        "code_example": "\n".join(code_lines),
        "pattern_scope": pattern_scope,
        "language": language,
        "framework": framework,
        "stack": stack,
        "source_repo": source_repo,
    }


def build_flow_pattern_wiring(
    routes: list[RouteDefinition],
    edges: list[ImportEdge],
    language: str = "python",
    framework: str = "fastapi",
    stack: str = "fastapi+sqlalchemy+pydantic_v2",
    source_repo: str = "",
    pattern_scope: str = "crud_simple",
) -> list[dict[str, Any]]:
    """
    Construit des wirings de type flow_pattern — un par route.
    Chaque flow trace le chemin : request → validation → route → crud → model → response.
    """
    wirings: list[dict[str, Any]] = []

    # Index des imports par fichier pour résoudre les appels
    import_index: dict[str, dict[str, str]] = {}  # file → {name → module}
    for e in edges:
        if e.source_file not in import_index:
            import_index[e.source_file] = {}
        for name in e.imported_names:
            import_index[e.source_file][name] = e.target_module

    for route in routes:
        if route.method == "unknown":
            continue

        # Résoudre les appels vers les modules source
        flow_steps: list[str] = []
        flow_steps.append(f"{route.method.upper()} {route.path}")

        # Depends
        for dep in route.depends:
            flow_steps.append(f"→ Depends({dep.depends_on}) → {dep.parameter_name}")

        # Body calls → résolution vers les modules
        file_imports = import_index.get(route.file, {})
        for call_name in route.calls:
            source_module = file_imports.get(call_name, "?")
            if source_module != "?":
                flow_steps.append(f"→ {source_module}.{call_name}()")
            else:
                flow_steps.append(f"→ {call_name}()")

        # Seulement si le flow est intéressant (> 2 étapes)
        if len(flow_steps) < 2:
            continue

        connections = flow_steps
        modules = sorted({route.file} | {
            file_imports.get(c, "?") for c in route.calls if file_imports.get(c, "?") != "?"
        })

        description = (
            f"Flow pattern for {route.method.upper()} {route.path} in {pattern_scope}. "
            f"Traces: {' → '.join(flow_steps[:4])}{'...' if len(flow_steps) > 4 else ''}"
        )

        code_example = "\n".join([
            f"# === Flow: {route.method.upper()} {route.path} ===",
            f"# Handler: {route.function_name}",
            *[f"# {step}" for step in flow_steps],
        ])

        wirings.append({
            "wiring_type": "flow_pattern",
            "description": description,
            "modules": modules,
            "connections": connections,
            "code_example": code_example,
            "pattern_scope": pattern_scope,
            "language": language,
            "framework": framework,
            "stack": stack,
            "source_repo": source_repo,
        })

    return wirings


def build_lifespan_wiring(
    lifespan_calls: list[str],
    router_includes: list[RouterInclude],
    language: str = "python",
    framework: str = "fastapi",
    stack: str = "fastapi+sqlalchemy+pydantic_v2",
    source_repo: str = "",
    pattern_scope: str = "crud_simple",
) -> dict[str, Any] | None:
    """Construit un wiring pour le lifecycle de l'app (lifespan + router wiring)."""
    if not lifespan_calls and not router_includes:
        return None

    modules = ["main.py"] + sorted({ri.router_module for ri in router_includes})

    connections: list[str] = []
    if lifespan_calls:
        connections.append(f"lifespan → {', '.join(lifespan_calls)}")
    for ri in router_includes:
        connections.append(
            f"app.include_router({ri.router_module}, prefix=\"{ri.prefix}\")"
        )

    code_lines = ["# === App Lifecycle & Router Wiring ==="]
    if lifespan_calls:
        code_lines.append("@asynccontextmanager")
        code_lines.append("async def lifespan(_app: FastAPI):")
        for call in lifespan_calls:
            code_lines.append(f"    await {call}()")
        code_lines.append("    yield")
        code_lines.append("")
    code_lines.append("app = FastAPI(lifespan=lifespan)")
    for ri in router_includes:
        code_lines.append(f'app.include_router({ri.router_module}, prefix="{ri.prefix}")')

    description = (
        f"App lifecycle for {pattern_scope}. "
        f"Startup: {', '.join(lifespan_calls) if lifespan_calls else 'none'}. "
        f"Routers: {len(router_includes)} included."
    )

    return {
        "wiring_type": "dependency_chain",  # lifecycle = dependency chain spéciale
        "description": description,
        "modules": modules,
        "connections": connections,
        "code_example": "\n".join(code_lines),
        "pattern_scope": pattern_scope,
        "language": language,
        "framework": framework,
        "stack": stack,
        "source_repo": source_repo,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def extract_all_wirings(
    repo_path: str,
    *,
    language: str = "python",
    framework: str = "fastapi",
    stack: str = "fastapi+sqlalchemy+pydantic_v2",
    source_repo: str = "",
    pattern_scope: str = "crud_simple",
    exclude_tests: bool = True,
) -> list[dict[str, Any]]:
    """
    Extraction complète des wirings d'un repo Python.

    Returns:
        Liste de dicts prêts à être insérés dans Qdrant (collection `wirings`).
        Chaque dict contient tous les champs sauf `created_at`, `_tag`, et le vecteur.
    """
    exclude_dirs = {".venv", "venv", "__pycache__", ".git", "migrations", "alembic"}
    if exclude_tests:
        exclude_dirs.add("tests")
        exclude_dirs.add("test")

    python_files = find_python_files(repo_path, exclude_dirs)
    if not python_files:
        return []

    local_modules = get_local_modules(repo_path, python_files)

    # 1. Import graph
    edges = extract_import_graph(repo_path, python_files, local_modules)

    # 2. Depends chains & routes
    depends, routes = extract_depends_chains(repo_path, python_files)

    # 3. Lifespan & router includes
    lifespan_calls, router_includes = extract_lifespan_and_includes(repo_path, python_files)

    # Build wirings
    all_wirings: list[dict[str, Any]] = []

    common = dict(
        language=language,
        framework=framework,
        stack=stack,
        source_repo=source_repo,
        pattern_scope=pattern_scope,
    )

    # Import graph (1 wiring global)
    ig = build_import_graph_wiring(edges, **common)
    if ig:
        all_wirings.append(ig)

    # Dependency chains (1 wiring global)
    dc = build_dependency_chain_wiring(depends, routes, **common)
    if dc:
        all_wirings.append(dc)

    # Flow patterns (1 wiring par route)
    fps = build_flow_pattern_wiring(routes, edges, **common)
    all_wirings.extend(fps)

    # Lifespan wiring (1 wiring)
    lw = build_lifespan_wiring(lifespan_calls, router_includes, **common)
    if lw:
        all_wirings.append(lw)

    return all_wirings


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python extract_wirings.py /path/to/repo [pattern_scope]")
        sys.exit(1)

    repo = sys.argv[1]
    scope = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    wirings = extract_all_wirings(
        repo,
        pattern_scope=scope,
        source_repo=f"local:{repo}",
    )

    print(f"\n{'='*60}")
    print(f"  Extracted {len(wirings)} wirings from {repo}")
    print(f"{'='*60}")

    for i, w in enumerate(wirings):
        print(f"\n--- Wiring {i+1}: {w['wiring_type']} ---")
        print(f"  Description: {w['description'][:100]}...")
        print(f"  Modules: {w['modules']}")
        print(f"  Connections ({len(w['connections'])}):")
        for c in w["connections"][:5]:
            print(f"    {c}")
        if len(w["connections"]) > 5:
            print(f"    ... (+{len(w['connections'])-5} more)")
