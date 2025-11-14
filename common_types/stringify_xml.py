import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List

from common_types.snippet_types import (
    OtherSnippetPinType,
    Snippet,
    SnippetMap,
    SnippetNet,
    SnippetNetlist,
)

XML_WARNING = "WARNING: This file has been automatically generated. Do not edit!"


def _xmlify_snippet(
    snippet: Snippet,
    other_snippet_pin_type: OtherSnippetPinType,
    tag_name: str,
) -> ET.Element:
    root = ET.Element(tag_name)
    root.set("path", snippet.path)
    root.set("type", snippet.type_name)

    snippet_map_fields = ET.SubElement(root, "snippetMapFields")
    for key, value in snippet.snippet_map_fields.items():
        snippet_map_field = ET.SubElement(snippet_map_fields, "snippetMapField")
        snippet_map_field.set("name", key)
        snippet_map_field.text = value

    xml_pins = ET.SubElement(root, "pins")
    # Ensure xml is deterministic.
    pins = list(snippet.pins.items())
    pins.sort(key=lambda item: item[0])
    for name, pin_connection in pins:
        pin = ET.SubElement(xml_pins, "pin")
        pin.set("name", name)

        if other_snippet_pin_type == OtherSnippetPinType.MANY_TO_MANY:
            # This should be a Set[GlobalSnippetPinIdentifier] but that typing isn't present at runtime
            assert type(pin_connection) is set
            other_pins = list(pin_connection)
            other_pins.sort()
            for other_pin in other_pins:
                xml_other_pin = ET.SubElement(pin, "otherPin")
                xml_other_pin.set("path", other_pin[0][0])
                xml_other_pin.set("type", other_pin[0][1])
                xml_other_pin.set("pin", other_pin[1])
        elif other_snippet_pin_type == OtherSnippetPinType.ONE_TO_MANY:
            root_snippet_pin = pin_connection
            if root_snippet_pin is not None:
                # This should be a SnippetPinName but is actually a str at runtime...
                assert type(root_snippet_pin) is str
                pin.set("rootSnippetPin", root_snippet_pin)
        else:
            assert other_snippet_pin_type == OtherSnippetPinType.NO_OTHER_PINS
            assert pin_connection is None
            # is None: don't add anything
    return root


def _xmlify_snippets(
    snippets: List[Snippet],
    other_snippet_pin_type: OtherSnippetPinType,
    tag_name: str,
) -> ET.Element:
    xml_snippets = ET.Element(tag_name)
    # Ensure xml is deterministic.
    snippets.sort(key=lambda s: s.get_id())
    for snippet in snippets:
        xml_snippet = _xmlify_snippet(snippet, other_snippet_pin_type, "snippet")
        xml_snippets.append(xml_snippet)
    return xml_snippets


def _xmlify_net(net: SnippetNet, tag_name: str) -> ET.Element:
    xml_net = ET.Element(tag_name)
    # Ensure xml is deterministic.
    nodes = list(net)
    nodes.sort()
    for node in nodes:
        xml_node = ET.SubElement(xml_net, "node")
        xml_node.set("path", node[0][0])
        xml_node.set("type", node[0][1])
        xml_node.set("pin", node[1])
    return xml_net


def _xmlify_nets(nets: List[SnippetNet], tag_name: str) -> ET.Element:
    xml_nets = ET.Element(tag_name)
    # Ensure xml is deterministic.
    nets.sort(key=lambda n: bytes(ET.tostring(_xmlify_net(n, "net"), encoding="utf-8")))
    for net in nets:
        xml_net = _xmlify_net(net, "net")
        xml_nets.append(xml_net)
    return xml_nets


def _create_xml_root(
    source: Path, date: datetime, tool: str, tag_name: str
) -> ET.Element:
    root = ET.Element(tag_name)
    warning_comment = ET.Comment(XML_WARNING)
    root.append(warning_comment)

    netlist = ET.SubElement(root, "netlist")
    source_tag = ET.SubElement(netlist, "source")
    source_tag.text = str(source)
    date_tag = ET.SubElement(netlist, "date")
    date_tag.text = date.isoformat()
    tool_tag = ET.SubElement(netlist, "tool")
    tool_tag.text = tool

    return root


def _stringify_xml(element: ET.Element) -> bytes:
    ET.indent(element, space="    ", level=0)
    return bytes(
        ET.tostring(element, encoding="utf-8", method="xml", xml_declaration=True)
    )


def stringify_snippet_netlist(snippet_netlist: SnippetNetlist) -> bytes:
    root = _create_xml_root(
        snippet_netlist.source,
        snippet_netlist.date,
        snippet_netlist.tool,
        "snippetNetlist",
    )
    root.append(
        _xmlify_snippets(
            list(snippet_netlist.snippets.values()),
            OtherSnippetPinType.NO_OTHER_PINS,
            "snippets",
        )
    )
    root.append(_xmlify_nets(list(snippet_netlist.nets), "nets"))
    return _stringify_xml(root)


def stringify_snippet_map(snippet_map: SnippetMap) -> bytes:
    root = _create_xml_root(
        snippet_map.source, snippet_map.date, snippet_map.tool, "snippetMap"
    )
    if snippet_map.map_type == OtherSnippetPinType.ONE_TO_MANY:
        assert snippet_map.root_snippet is not None
        assert snippet_map.map_type == OtherSnippetPinType.ONE_TO_MANY
        root.append(
            _xmlify_snippet(
                snippet_map.root_snippet,
                OtherSnippetPinType.NO_OTHER_PINS,
                "rootSnippet",
            )
        )
    else:
        # NO_OTHER_PINS is not possible for a snippet map.
        assert snippet_map.map_type == OtherSnippetPinType.MANY_TO_MANY
        assert snippet_map.root_snippet is None
    root.append(
        _xmlify_snippets(list(snippet_map.snippets), snippet_map.map_type, "snippets")
    )
    return _stringify_xml(root)
