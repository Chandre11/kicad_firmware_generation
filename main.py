import sys
from pathlib import Path
from typing import Set, Dict, Tuple, NewType
from datetime import datetime
import xml.etree.ElementTree as ET


SNIPPET_TYPE_FIELD_NAME = "SnippetType"
SNIPPET_PIN_FIELD_PREFIX = "SnippetPin"
SNIPPET_MAP_FIELD_PREFIX = "SnippetMapField"
TOOL_NAME = "kicad_snippet_mapper v0.1.0"

ComponentRef = NewType("ComponentRef", str)
SheetPath = NewType("SheetPath", str)
NodePinName = NewType("NodePinName", str)
# globally unique descriptor for a pin
GlobalPinIdentifier = NewType("GlobalPinIdentifier", Tuple[ComponentRef, NodePinName])
NodePinFunction = NewType("NodePinFunction", str)

SnippetName = NewType("SnippetName", str)
SnippetType = NewType("SnippetType", str)
SnippetPinName = NewType("SnippetPinName", str)
GlobalSnippetPinIdentifier = NewType(
    "GlobalSnippetPinIdentifier", Tuple[SnippetName, SnippetPinName]
)
# These pins are connected.
SnippetNet = NewType("SnippetNet", Set[GlobalSnippetPinIdentifier])
SnippetNetList = NewType("SnippetNetList", Set[SnippetNet])


class Component:
    ref: ComponentRef
    sheetpath: SheetPath
    fields: Dict[str, str]


# a pin on a component that is connected to some net(s)
class Node:
    ref: ComponentRef
    pin: NodePinName
    pinfunction: NodePinFunction


class Net:
    nodes: Set[Node]


class Netlist:
    source: Path
    # Map component's ref to component.
    # TODO: ensure refs are unique
    components: Dict[ComponentRef, Component]
    nets: Set[Net]


class Snippet:
    name: SnippetName
    type_name: SnippetType
    # Map key to value.
    snippet_map_fields: Dict[str, str]
    # Map snippet pin name to connected root snippet pin name.
    # If this is the root snippet the value is always None.
    pins: Dict[SnippetPinName, SnippetPinName | None]


class SnippetMap:
    source: Path
    date: datetime
    tool: str

    root_snippet: Snippet
    snippets: Set[Snippet]


def parse_netlist(netlist_path: Path) -> Netlist:
    tree = ET.parse(netlist_path)
    root = tree.getroot()
    print(root)


# mapping from snippet name to set of components that belong to this snippet
SnippetsLookup = NewType("SnippetsLookup", Dict[SnippetName, Set[Component]])
# mapping from component ref to snippet name
SnippetsReverseLookup = NewType(
    "SnippetsReverseLookup", Dict[ComponentRef, SnippetName]
)


def group_components_by_snippet(
    netlist: Netlist,
) -> Tuple[SnippetsLookup, SnippetsReverseLookup]:
    snippets = SnippetsLookup(dict())
    reverse_lookup = SnippetsReverseLookup(dict())
    for component in netlist.components.values():
        if SNIPPET_TYPE_FIELD_NAME not in component.fields:
            # This component is not part of any snippet.
            continue
        snippet_type = SnippetType(component.fields[SNIPPET_TYPE_FIELD_NAME])
        snippet_name = SnippetName(f"{component.sheetpath}{snippet_type}")
        if snippet_name in snippets:
            snippets[snippet_name].add(component)
        else:
            snippets[snippet_name] = {component}
        assert component.ref not in reverse_lookup
        reverse_lookup[component.ref] = snippet_name

    return (snippets, reverse_lookup)


# For each snippet this resolves the pins global identifier to the explicitly chosen pin name.
SnippetPinNameLookups = NewType(
    "SnippetPinNameLookups",
    Dict[SnippetName, Dict[GlobalPinIdentifier, SnippetPinName]],
)


# Snippets without a explicit naming don't appear in this dict.
def get_explicit_pin_name_lookups(
    snippets_lookup: SnippetsLookup,
) -> SnippetPinNameLookups:
    explicit_pin_namings = SnippetPinNameLookups(dict())
    for snippet_name, components in snippets_lookup.items():
        # Use this set to verify no SnippetPin name is used twice for the same snippet.
        snippet_pin_names: Set[SnippetPinName] = set()
        for component in components:
            for field_name, field_value in component.fields.items():
                # Only consider field names that define explic SnippetPin names.
                if not field_name.startswith(SNIPPET_PIN_FIELD_PREFIX):
                    continue

                # After the SnippetPin prefix comes the pin shown in KiCad that belongs to the component.
                node_pin_name = NodePinName(field_name[len(SNIPPET_PIN_FIELD_PREFIX) :])
                global_pin_identifier = GlobalPinIdentifier((
                    component.ref,
                    node_pin_name,
                ))
                # We can't have the same globally unique reference for two pins.
                for other_expicit_in_naming_snippet in explicit_pin_namings.values():
                    assert global_pin_identifier not in other_expicit_in_naming_snippet

                # This is the name the user explicitly set for this pin.
                snippet_pin_name = SnippetPinName(field_value)
                if snippet_pin_name in snippet_pin_names:
                    print(
                        f"The SnippetPin {snippet_pin_name} exists twice for the snippet {snippet_name}.",
                        sys.stderr,
                    )
                    sys.exit(1)
                snippet_pin_names.add(snippet_pin_name)

                # update explicit_pin_namings
                if snippet_name in explicit_pin_namings:
                    explicit_pin_namings[snippet_name][global_pin_identifier] = (
                        snippet_pin_name
                    )
                else:
                    explicit_pin_namings[snippet_name] = {
                        global_pin_identifier: snippet_pin_name
                    }
    return explicit_pin_namings


# The KiCad netlist connects pins on components to other pins on other components.
# This function converts that netlist into a netlist that connects pins on snippets to other pins on other snippets.
# The names of the pins are the SnippetPin names and not the KiCad pin names any longer.
def convert_netlist(
    netlist: Netlist,
    snippets_lookup: SnippetsLookup,
    snippets_reverse_lookup: SnippetsReverseLookup,
) -> SnippetNetList:
    explicit_pin_name_lookups = get_explicit_pin_name_lookups(snippets_lookup)

    # We only use this to check that no two components have the same global snippet pin identifier.
    global_snippet_pin_to_component: Dict[GlobalSnippetPinIdentifier, ComponentRef] = (
        dict()
    )

    snippet_netlist = SnippetNetList(set())
    for net in netlist.nets:
        snippet_net = SnippetNet(set())
        for node in net.nodes:
            if node.ref not in snippets_reverse_lookup:
                # The node does not belong to a component that belongs to a snippet.
                continue
            snippet_name = snippets_reverse_lookup[node.ref]
            global_pin_identifier = GlobalPinIdentifier((node.ref, node.pin))

            # Figure out what name this pin has.
            snippet_pin_name: SnippetPinName
            if snippet_name in explicit_pin_name_lookups:
                explicit_pin_name_lookup = explicit_pin_name_lookups[snippet_name]
                if global_pin_identifier not in explicit_pin_name_lookup:
                    # The pin does belong to components that belong to the snippet.
                    # Nevertheless, the user chose to explicitly define SnippetPin names to some of the snippet's pins and this pin doesn't have one.
                    # Therefore, we don't consider this pin to belong to the snippet.
                    continue
                snippet_pin_name = explicit_pin_name_lookup[global_pin_identifier]
            else:
                # When the user didn't define any SnippetPin names for at all we use a fallback:
                # We consider all pins that belong to components that belong to the snippet as pins of the snippet.
                snippet_pin_name = SnippetPinName(node.pinfunction)
            # This uniquely identifies the pin in the entire snippet map.
            global_snippet_pin_identifier = GlobalSnippetPinIdentifier((
                snippet_name,
                snippet_pin_name,
            ))

            if (
                global_snippet_pin_identifier in global_snippet_pin_to_component
                and global_snippet_pin_to_component[global_snippet_pin_identifier]
                != node.ref
            ):
                print(
                    f"the pin {snippet_pin_name} in the snippet {snippet_name} occurs in multiple components: {global_snippet_pin_to_component[global_snippet_pin_identifier]} and {node.ref}.",
                    sys.stderr,
                )
                sys.exit(1)
            global_snippet_pin_to_component[global_snippet_pin_identifier] = node.ref

            # This might very well be the only pin in the snippet net.
            snippet_net.add(global_snippet_pin_identifier)
        snippet_netlist.add(snippet_net)
    return snippet_netlist


def gen_snippet_map(netlist: Netlist, root_snippet_name: str) -> SnippetMap:
    snippets_lookup, snippets_reverse_lookup = group_components_by_snippet(netlist)
    snippet_netlist = convert_netlist(netlist, snippets_lookup, snippets_reverse_lookup)

    snippet_map = SnippetMap()
    snippet_map.source = netlist.source
    snippet_map.date = datetime.now()
    snippet_map.tool = TOOL_NAME

    if snippets[root_snippet_name] is None:
        print(f"Didn't find a root snippet with name {root_snippet_name}", sys.stderr)
        sys.exit(1)
    snippet_map.root_snippet = snippets[root_snippet_name]

    return snippet_map


def stringify_snippet_map(snippet_map: SnippetMap) -> str:
    pass


def main():
    if len(sys.argv) != 3:
        print(
            "Provide two arguments: the input file path and the root snippet name",
            sys.stderr,
        )
        sys.exit(1)
    netlist_path = sys.argv[1]
    root_snippet_name = sys.argv[2]
    netlist = parse_netlist(Path(netlist_path))
    snippet_map = gen_snippet_map(netlist, root_snippet_name)
    print(stringify_snippet_map(snippet_map))


if __name__ == "__main__":
    main()
