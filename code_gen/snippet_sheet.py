from typing import Dict

from snippet_map.snippet_types import Snippet, SnippetPathNode, SnippetType


class SnippetSheet:
    """
    In some situation multiple snippets fulfill a purpose as a group.
    In that case the user might want to generate firmware for the entire group and not each individual snippet.
    For this purpose every snippet has a path.
    This path consists of multiple nodes concatenated with `/`.
    With this the snippet map can group snippets together.

    A SnippetSheet represents all snippets with a path prefixed by the SnippetSheet's path.
    If there is a snippet with exactly the same path, the SnippetSheet contains all the snippet's information.
    """

    """
    A sheet that is a snippet might have sub-sheets, too.
    """
    children: Dict[SnippetPathNode, "SnippetSheet"]
    """
    None iff this is belongs to the root snippet sheet.
    Be aware that this may not be the root snippet.
    That is a different concept.
    The root snippet is the snippet with the snippet map's perspective.
    """
    parent: "SnippetSheet | None"

    snippets: Dict[SnippetType, Snippet]
