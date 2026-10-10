"""TypeScript and JavaScript (with JSX), read with tree-sitter (see codemop.review.code)."""
import functools
import posixpath
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language as Grammar, Node, Parser, Query, QueryCursor

from codemop.review.code import Block, searchable

_TYPESCRIPT = Grammar(tree_sitter_typescript.language_typescript())
_TSX = Grammar(tree_sitter_typescript.language_tsx())
_JAVASCRIPT = Grammar(tree_sitter_javascript.language())  # with JSX
_GRAMMARS = {".ts": _TYPESCRIPT, ".mts": _TYPESCRIPT, ".cts": _TYPESCRIPT, ".tsx": _TSX,
             ".js": _JAVASCRIPT, ".jsx": _JAVASCRIPT, ".mjs": _JAVASCRIPT, ".cjs": _JAVASCRIPT}

# Declarations with a name of their own, and how they're described
_DECLARATIONS = {
    "function_declaration": "function", "generator_function_declaration": "function",
    "class_declaration": "class", "abstract_class_declaration": "class", "method_definition": "method",
    "interface_declaration": "interface", "type_alias_declaration": "type", "enum_declaration": "enum",
}
_FUNCTIONS = {"arrow_function", "function_expression", "function", "generator_function"}
_VARIABLES = {"lexical_declaration", "variable_declaration"}
_NAMES = {"identifier", "property_identifier", "shorthand_property_identifier",
          "shorthand_property_identifier_pattern", "type_identifier"}
_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
# Every name in a file, found by tree-sitter itself (walking the tree in Python is far slower)
_NAME_QUERIES = {grammar: Query(grammar, " ".join(f"({kind}) @name" for kind in sorted(_NAMES)
                                                   if kind != "type_identifier" or grammar is not _JAVASCRIPT))
                 for grammar in (_TYPESCRIPT, _TSX, _JAVASCRIPT)}


def _start(node: Node) -> int:
    return node.start_point[0] + 1


def _end(node: Node) -> int:
    return node.end_point[0] + 1


def _text(node: Node) -> str:
    return node.text.decode("utf-8", "replace")


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _in_import(node: Node) -> bool:
    while node is not None:
        if node.type == "import_statement":
            return True
        node = node.parent
    return False


def _named(node: Node) -> Optional[Block]:
    """The block a node is, if it's a named function, class or other declaration"""
    name = node.child_by_field_name("name")
    if node.type in _DECLARATIONS:
        return Block(_start(node), _end(node), _DECLARATIONS[node.type], _text(name)) if name else None
    value = node.child_by_field_name("value")
    if node.type == "variable_declarator" and value and value.type in _FUNCTIONS and name and name.type == "identifier":
        statement = node.parent  # const Thing = () => ..., including the `const`
        return Block(_start(statement), _end(statement), "function", _text(name))
    if node.type == "public_field_definition" and value and value.type in _FUNCTIONS and name:
        return Block(_start(node), _end(node), "method", _text(name))
    return None


def _declared(statement: Node) -> Optional[Node]:
    """The declaration a top-level statement makes (unwrapping `export`)"""
    if statement.type == "export_statement":
        return statement.child_by_field_name("declaration")
    return statement


def _declarators(declaration: Node) -> List[Tuple[str, Node]]:
    """The names a const/let/var declaration sets, each with its declarator"""
    return [(_text(d.child_by_field_name("name")), d) for d in declaration.children
            if d.type == "variable_declarator" and d.child_by_field_name("name") is not None
            and d.child_by_field_name("name").type == "identifier"]


def _module(source: str) -> str:
    """The last part of an import's path, as module_name gives it for the file it means"""
    parts = [p for p in source.split("?")[0].split("/") if p not in ("", ".", "..")]
    if not parts:
        return ""
    last = re.sub(r"\.(d\.)?[mc]?[jt]sx?$", "", parts[-1])
    return parts[-2] if last == "index" and len(parts) > 1 else last


class TypeScriptCode:
    def __init__(self, root: Node, grammar: Grammar):
        self.root, self.grammar = root, grammar

    @functools.cached_property
    def blocks(self) -> List[Block]:
        return [block for block in map(_named, _walk(self.root)) if block]

    def innermost(self, line: int) -> Optional[Block]:
        around = [b for b in self.blocks if b.start <= line <= b.end]
        return min(around, key=lambda b: b.end - b.start, default=None)

    def _owner(self, line: int) -> Optional[str]:
        """The name of the top-level declaration a line is in"""
        for statement in self.root.children:
            if _start(statement) <= line <= _end(statement):
                declared = _declared(statement)
                if declared is None:
                    return None
                name = declared.child_by_field_name("name")
                if name is not None:
                    return _text(name)
                names = _declarators(declared) if declared.type in _VARIABLES else []
                return names[0][0] if names else None
        return None

    def changed_definitions(self, changed: Set[int]) -> Dict[str, str]:
        def touched(node: Node) -> bool:
            return any(_start(node) <= line <= _end(node) for line in changed)

        names = {block.name: self._owner(block.start) or block.name
                 for block in (self.innermost(line) for line in sorted(changed)) if block}
        for statement in self.root.children:
            declared = _declared(statement)
            if declared is None:
                continue
            if declared.type in _VARIABLES:  # a constant, or a function held in one
                names.update((name, name) for name, d in _declarators(declared) if touched(d))
            # A class's fields, and an interface's or type's members: a renamed field's uses matter
            owner = declared.child_by_field_name("name")
            body = declared.child_by_field_name("body") or declared.child_by_field_name("value")
            if owner is not None and body is not None and touched(body):
                for member in body.children:
                    name = member.child_by_field_name("name")
                    if member.type in ("public_field_definition", "property_signature") and name and touched(member):
                        names[_text(name)] = _text(owner)
        return {name: names[name] for name in searchable(list(names), TYPESCRIPT.ignored)}

    def top_level_definitions(self) -> Dict[str, Block]:
        definitions: Dict[str, Block] = {}
        default_name = None
        for statement in self.root.children:
            declared = _declared(statement)
            block = (lambda name: Block(_start(statement), _end(statement), "defines", name))
            if declared is not None:
                name = declared.child_by_field_name("name")
                if declared.type in _VARIABLES:
                    for declarator_name, _ in _declarators(declared):
                        definitions[declarator_name] = block(declarator_name)
                elif name is not None:
                    definitions[_text(name)] = block(_text(name))
                    if statement.type == "export_statement" and any(c.type == "default" for c in statement.children):
                        definitions["default"] = block(_text(name))
            elif statement.type == "export_statement" and any(c.type == "default" for c in statement.children):
                value = statement.child_by_field_name("value")
                default_name = _text(value) if value is not None and value.type == "identifier" else None
        if default_name in definitions:  # export default Thing;
            definitions["default"] = definitions[default_name]
        return definitions

    def _import_statements(self) -> Iterator[Tuple[str, Node]]:
        for statement in self.root.children:
            source = statement.child_by_field_name("source")
            if statement.type == "import_statement" and source is not None:
                yield _text(source).strip("'\"`"), statement

    def imports(self) -> Dict[str, Tuple[str, object]]:
        found: Dict[str, Tuple[str, object]] = {}
        for source, statement in self._import_statements():
            for node in _walk(statement):
                if node.type == "import_clause":
                    default = next((c for c in node.children if c.type == "identifier"), None)
                    if default is not None:
                        found[_text(default)] = ("default", source)
                elif node.type == "import_specifier":
                    name, alias = node.child_by_field_name("name"), node.child_by_field_name("alias")
                    if name is not None:
                        found[_text(alias or name)] = (_text(name), source)
                elif node.type == "namespace_import":
                    local = next((c for c in node.children if c.type == "identifier"), None)
                    if local is not None:
                        found[_text(local)] = ("*", source)
        return found

    def imported_from(self, module: str) -> Set[str]:
        found = set()
        for local, (name, source) in self.imports().items():
            if _module(source) == module:
                # A default import's local name is usually the definition's own (a component's)
                found |= {"*"} if name == "*" else {name, local} if name == "default" else {name}
        return found

    def references(self, names: Set[str]) -> List[Tuple[int, str]]:
        """As a name, a property, a type, or a JSX tag; not in the imports themselves"""
        found = QueryCursor(_NAME_QUERIES[self.grammar]).captures(self.root).get("name", [])
        return sorted((_start(node), _text(node)) for node in found
                      if _text(node) in names and not _in_import(node))


class TypeScript:
    extensions = _EXTENSIONS
    ignored = {
        "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else",
        "enum", "export", "extends", "false", "finally", "for", "function", "if", "import", "in", "instanceof",
        "new", "null", "return", "super", "switch", "this", "throw", "true", "try", "typeof", "var", "void",
        "while", "with", "yield", "let", "static", "implements", "interface", "package", "private", "protected",
        "public", "await", "async", "type", "readonly", "declare", "namespace", "abstract", "keyof", "infer",
        "never", "unknown", "undefined", "string", "number", "boolean", "object", "symbol", "bigint", "any",
        "console", "window", "document", "Promise", "Array", "Object", "String", "Number", "Boolean", "Symbol",
        "JSON", "Math", "Date", "Error", "Map", "Set", "RegExp", "Record", "Partial", "Required", "Readonly",
        "Pick", "Omit", "ReturnType", "React", "process", "require", "module", "exports",
    }

    def parse(self, path: str, text: str) -> Optional[TypeScriptCode]:
        grammar = _GRAMMARS.get(Path(path).suffix)
        return _parse(grammar, text) if grammar is not None else None

    def module_name(self, path: str) -> str:
        return _module(path)

    def module_paths(self, source: object, importer: str, repo_paths: Set[str]) -> List[str]:
        """
        For `import ... from "<source>"`: a relative path from the importer's folder, or a path
        alias (like Next.js's "@/lib/thing"), matched against the end of the repository's paths.
        A package from node_modules isn't in the repository, so it means nothing here.
        """
        spec = str(source).split("?")[0]
        stem = re.sub(r"\.[mc]?[jt]sx?$", "", spec)  # ESM imports can name "./thing.js" for thing.ts
        if spec.startswith("."):
            root = posixpath.normpath(posixpath.join(posixpath.dirname(importer), stem))
            candidates = [root + ext for ext in _EXTENSIONS] + [f"{root}/index{ext}" for ext in _EXTENSIONS]
            return [c for c in candidates if c in repo_paths]
        tail = re.sub(r"^[@~#]/", "", stem)
        candidates = [tail + ext for ext in _EXTENSIONS] + [f"{tail}/index{ext}" for ext in _EXTENSIONS]
        return sorted(p for p in repo_paths if any(p == c or p.endswith("/" + c) for c in candidates))


@functools.lru_cache(maxsize=512)  # files are read again for each chunk of a diff, and for several names
def _parse(grammar: Grammar, text: str) -> Optional[TypeScriptCode]:
    tree = Parser(grammar).parse(text.encode("utf-8"))
    return TypeScriptCode(tree.root_node, grammar) if tree is not None else None


TYPESCRIPT = TypeScript()
