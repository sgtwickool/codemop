"""TypeScript and JavaScript (with JSX), read with tree-sitter (see codemop.review.code)."""
import functools
import posixpath
import re
from typing import Dict, Hashable, Iterator, List, Optional, Set, Tuple

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language as Grammar, Node, Parser, Query, QueryCursor

from codemop.review.code.base import Block, Import, owners, paths_ending_with, searchable, touches

_TYPESCRIPT = Grammar(tree_sitter_typescript.language_typescript())
_TSX = Grammar(tree_sitter_typescript.language_tsx())
_JAVASCRIPT = Grammar(tree_sitter_javascript.language())  # with JSX
# In the order an import's file is looked for
_GRAMMARS = {".ts": _TYPESCRIPT, ".tsx": _TSX, ".js": _JAVASCRIPT, ".jsx": _JAVASCRIPT, ".mjs": _JAVASCRIPT,
             ".cjs": _JAVASCRIPT, ".mts": _TYPESCRIPT, ".cts": _TYPESCRIPT}
_EXTENSION = re.compile(r"\.(d\.)?[mc]?[jt]sx?$")  # an import may name it, as ESM does ("./thing.js" for thing.ts)

# Declarations with a name of their own, and how they're described
_DECLARATIONS = {
    "function_declaration": "function", "generator_function_declaration": "function",
    "class_declaration": "class", "abstract_class_declaration": "class", "method_definition": "method",
    "interface_declaration": "interface", "type_alias_declaration": "type", "enum_declaration": "enum",
}
_FUNCTIONS = {"arrow_function", "function_expression", "function", "generator_function"}
_VARIABLES = {"lexical_declaration", "variable_declaration"}
_MEMBERS = {"public_field_definition", "property_signature"}  # a class's fields, an interface's or type's members
_NAMES = {"identifier", "property_identifier", "shorthand_property_identifier",
          "shorthand_property_identifier_pattern", "type_identifier"}


def _name_query(grammar: Grammar, kinds: Set[str]) -> Query:
    """Every name in a file, found by tree-sitter itself (walking the tree in Python is far slower)"""
    return Query(grammar, " ".join(f"({kind}) @name" for kind in sorted(kinds)))


_NAME_QUERIES = {_TYPESCRIPT: _name_query(_TYPESCRIPT, _NAMES), _TSX: _name_query(_TSX, _NAMES),
                 _JAVASCRIPT: _name_query(_JAVASCRIPT, _NAMES - {"type_identifier"})}


def _start(node: Node) -> int:
    return node.start_point[0] + 1


def _end(node: Node) -> int:
    return node.end_point[0] + 1


def _text(node: Node) -> str:
    return node.text.decode("utf-8", "replace")


def _block(node: Node, kind: str, name: str) -> Block:
    return Block(_start(node), _end(node), kind, name)


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _identifier(node: Node) -> Optional[Node]:
    return next((child for child in node.children if child.type == "identifier"), None)


def _in_import(node: Node) -> bool:
    while node is not None:
        if node.type == "import_statement":
            return True
        node = node.parent
    return False


def _named(node: Node) -> Optional[Block]:
    """The block a node is, if it's a named function, class or other declaration"""
    name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
    if node.type in _DECLARATIONS:
        return _block(node, _DECLARATIONS[node.type], _text(name)) if name else None
    if node.type == "variable_declarator" and value and value.type in _FUNCTIONS and name and name.type == "identifier":
        return _block(node.parent, "function", _text(name))  # const Thing = () => ..., including the `const`
    if node.type == "public_field_definition" and value and value.type in _FUNCTIONS and name:
        return _block(node, "method", _text(name))
    return None


def _declared(statement: Node) -> Optional[Node]:
    """The declaration a top-level statement makes (unwrapping `export`)"""
    return statement.child_by_field_name("declaration") if statement.type == "export_statement" else statement


def _default_export(statement: Node) -> bool:
    return statement.type == "export_statement" and any(child.type == "default" for child in statement.children)


def _declarators(declaration: Node) -> List[Tuple[str, Node]]:
    """The names a const/let/var declaration sets, each with its declarator"""
    return [(_text(name), d) for d in declaration.children
            if d.type == "variable_declarator" and (name := d.child_by_field_name("name")) is not None
            and name.type == "identifier"]


def _module(source: str) -> str:
    """The last part of an import's path, as module_name gives it for the file it means"""
    parts = [p for p in source.split("?")[0].split("/") if p not in ("", ".", "..")]
    if not parts:
        return ""
    last = _EXTENSION.sub("", parts[-1])
    return parts[-2] if last == "index" and len(parts) > 1 else last


def _candidates(stem: str) -> List[str]:
    """The files an import of `stem` could mean"""
    return [stem + extension for extension in _GRAMMARS] + [f"{stem}/index{extension}" for extension in _GRAMMARS]


class TypeScriptCode:
    def __init__(self, root: Node, grammar: Grammar):
        self.root, self.grammar = root, grammar

    @functools.cached_property
    def _blocks(self) -> List[Block]:
        return [block for block in map(_named, _walk(self.root)) if block]

    @functools.cached_property
    def _definitions(self) -> Dict[str, Block]:
        definitions: Dict[str, Block] = {}
        default_name = None
        for statement in self.root.children:
            declared = _declared(statement)
            if declared is None:  # export default <expression>, export { ... }
                value = statement.child_by_field_name("value")
                if _default_export(statement) and value is not None and value.type == "identifier":
                    default_name = _text(value)
                continue
            name = declared.child_by_field_name("name")
            names = [n for n, _ in _declarators(declared)] if declared.type in _VARIABLES else (
                [_text(name)] if name is not None else [])
            for n in names:
                definitions[n] = _block(statement, "defines", n)
            if names and _default_export(statement):
                definitions["default"] = definitions[names[0]]
        if default_name in definitions:  # export default Thing;
            definitions["default"] = definitions[default_name]
        return definitions

    @functools.cached_property
    def _imports(self) -> Dict[str, Import]:
        found: Dict[str, Import] = {}
        for statement in self.root.children:
            source_node = statement.child_by_field_name("source")
            if statement.type != "import_statement" or source_node is None:
                continue
            source = _text(source_node).strip("'\"`")
            for node in _walk(statement):
                if node.type == "import_clause" and (default := _identifier(node)) is not None:
                    found[_text(default)] = Import("default", source)
                elif node.type == "import_specifier" and (name := node.child_by_field_name("name")) is not None:
                    found[_text(node.child_by_field_name("alias") or name)] = Import(_text(name), source)
                elif node.type == "namespace_import" and (local := _identifier(node)) is not None:
                    found[_text(local)] = Import("*", source)
        return found

    def innermost(self, line: int) -> Optional[Block]:
        return min((b for b in self._blocks if b.covers(line)), key=lambda b: b.end - b.start, default=None)

    def changed_definitions(self, changed: Set[int]) -> Dict[str, Set[str]]:
        names: Dict[str, Set[str]] = {}

        def add(name: str, line: int) -> None:
            names.setdefault(name, set()).update(owners(self._definitions, line) or {name})

        def touched(node: Node) -> bool:
            return touches(_start(node), _end(node), changed)

        for block in filter(None, map(self.innermost, sorted(changed))):
            add(block.name, block.start)
        for statement in self.root.children:
            declared = _declared(statement)
            if declared is None:
                continue
            if declared.type in _VARIABLES:  # a constant, or a function held in one
                for name, declarator in _declarators(declared):
                    if touched(declarator):
                        add(name, _start(declarator))
            # A class's fields, and an interface's or type's members: a renamed field's uses matter
            body = declared.child_by_field_name("body") or declared.child_by_field_name("value")
            if declared.child_by_field_name("name") is not None and body is not None and touched(body):
                for member in body.children:
                    name = member.child_by_field_name("name")
                    if member.type in _MEMBERS and name is not None and touched(member):
                        add(_text(name), _start(member))
        return searchable(names, TYPESCRIPT.ignored)

    def top_level_definitions(self) -> Dict[str, Block]:
        return self._definitions

    def imports(self) -> Dict[str, Import]:
        return self._imports

    def imported_from(self, module: str) -> Set[str]:
        return {imported.name for imported in self._imports.values() if _module(imported.source) == module}

    def references(self, names: Set[str]) -> List[Tuple[int, str]]:
        """As a name, a property, a type, or a JSX tag; not in the imports themselves"""
        wanted = {name.encode() for name in names}
        found = QueryCursor(_NAME_QUERIES[self.grammar]).captures(self.root).get("name", [])
        return sorted((_start(node), _text(node)) for node in found if node.text in wanted and not _in_import(node))


class TypeScript:
    extensions = tuple(_GRAMMARS)
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
        grammar = _GRAMMARS.get(posixpath.splitext(path)[1])
        return _parse(grammar, text) if grammar is not None else None

    def module_name(self, path: str) -> str:
        return _module(path)

    def module_paths(self, source: Hashable, importer: str, repo_paths: Set[str]) -> List[str]:
        """
        For `import ... from "<source>"`: a relative path from the importer's folder, or a path
        alias (like Next.js's "@/lib/thing"), matched against the end of the repository's paths.
        A package from node_modules isn't in the repository, so it means nothing here.
        """
        spec = str(source).split("?")[0]
        stem = _EXTENSION.sub("", spec)
        if spec.startswith("."):
            root = posixpath.normpath(posixpath.join(posixpath.dirname(importer), stem))
            return [candidate for candidate in _candidates(root) if candidate in repo_paths]
        return paths_ending_with(repo_paths, _candidates(re.sub(r"^[@~#]/", "", stem)))


@functools.lru_cache(maxsize=512)  # files are read again for each chunk of a diff, and for several names
def _parse(grammar: Grammar, text: str) -> Optional[TypeScriptCode]:
    tree = Parser(grammar).parse(text.encode("utf-8"))
    return TypeScriptCode(tree.root_node, grammar) if tree is not None else None


TYPESCRIPT = TypeScript()
