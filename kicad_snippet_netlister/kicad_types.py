from pathlib import Path
from typing import Dict, FrozenSet, NewType, Set, Tuple

from common_types.snippet_types import (
    SnippetIdentifier,
    SnippetPath,
    SnippetPinName,
    SnippetType,
)

KiCadComponentRef = NewType("KiCadComponentRef", str)
KiCadSheetPath = NewType("KiCadSheetPath", str)
KiCadNodePinName = NewType("KiCadNodePinName", str)
"""
globally unique descriptor for a pin
"""
GlobalKiCadPinIdentifier = NewType(
    "GlobalKiCadPinIdentifier", Tuple[KiCadComponentRef, KiCadNodePinName]
)
KiCadNodePinFunction = NewType("KiCadNodePinFunction", str)


class KiCadSheet:
    path: KiCadSheetPath


class KiCadComponent:
    ref: KiCadComponentRef
    sheetpath: KiCadSheetPath
    fields: Dict[str, str]

    def __repr__(self) -> str:
        return f"Component(ref={self.ref!r}, sheetpath={self.sheetpath!r}, fields={list(self.fields.keys())!r})"


class KiCadNode:
    """
    a pin on a component that is connected to some net(s)
    """

    ref: KiCadComponentRef
    pin: KiCadNodePinName
    pinfunction: KiCadNodePinFunction

    def __repr__(self) -> str:
        return f"Node(ref={self.ref!r}, pin={self.pin!r}, pinfunction={self.pinfunction!r})"


KiCadNet = NewType("KiCadNet", FrozenSet[KiCadNode])


class KiCadNetlist:
    source: Path
    sheets: Set[KiCadSheet]
    """
    Map component's ref to component.
    """
    components: Dict[KiCadComponentRef, KiCadComponent]
    nets: Set[KiCadNet]

    def __repr__(self) -> str:
        return (
            f"Netlist(source={self.source!r}, "
            f"components={len(self.components)} components, "
            f"nets={len(self.nets)} nets)"
        )


class RawSnippet:
    path: SnippetPath
    type_name: SnippetType
    """
    Map key to value.
    """
    snippet_map_fields: Dict[str, str]

    components: Set[KiCadComponent]

    def get_id(self) -> SnippetIdentifier:
        return SnippetIdentifier((self.path, self.type_name))

    def __repr__(self) -> str:
        return (
            f"RawSnippet(path={self.path!r}, type_name={self.type_name!r}, "
            f"fields={list(self.snippet_map_fields.keys())!r}, components={len(self.components)})"
        )


"""
mapping from snippet name to the info we can directly pull from the KiCad netlist
"""
RawSnippetLookup = NewType("RawSnippetLookup", Dict[SnippetIdentifier, RawSnippet])
"""
mapping from component ref to snippet name
"""
SnippetsReverseLookup = NewType(
    "SnippetsReverseLookup", Dict[KiCadComponentRef, SnippetIdentifier]
)
"""
For each snippet this resolves the pins global identifier to the explicitly chosen pin name.
"""
SnippetPinNameLookups = NewType(
    "SnippetPinNameLookups",
    Dict[SnippetIdentifier, Dict[GlobalKiCadPinIdentifier, SnippetPinName]],
)
