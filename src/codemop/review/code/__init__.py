"""
What repository context needs to know about code, for each language it can read: the
function or class around a line, what a change defines, where names are used, and what a file
imports and from where. Python is read with the standard library's ast, TypeScript and
JavaScript with tree-sitter; any other language gets the lines around each change instead.
"""
import posixpath
from typing import Optional

from codemop.review.code.base import Block, Import, Language, Parsed  # noqa: F401
from codemop.review.code.python import PYTHON
from codemop.review.code.typescript import TYPESCRIPT

_BY_EXTENSION = {extension: language for language in (PYTHON, TYPESCRIPT) for extension in language.extensions}


def language_for(path: str) -> Optional[Language]:
    """The language a file is in, if it's one context can read"""
    return _BY_EXTENSION.get(posixpath.splitext(path)[1])
