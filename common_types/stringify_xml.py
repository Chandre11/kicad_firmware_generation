import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Set

from common_types.group_types import (
    GroupNetlist,
    Group,
    GroupNet,
)

XML_WARNING = "WARNING: This file has been automatically generated. Do not edit!"


def _xmlify_group(
    group: Group,
    tag_name: str,
) -> ET.Element:
    root = ET.Element(tag_name)
    root.set("schematic", group.schematic)
    root.set("path", group.path)
    root.set("type", group.group_type)

    group_map_fields = ET.SubElement(root, "groupMapFields")
    for key, value in group.group_map_fields.items():
        group_map_field = ET.SubElement(group_map_fields, "groupMapField")
        group_map_field.set("name", key)
        group_map_field.text = value

    xml_pins = ET.SubElement(root, "pins")
    # Ensure xml is deterministic.
    pins = list(group.pins)
    pins.sort()
    for name in pins:
        pin = ET.SubElement(xml_pins, "pin")
        pin.set("name", name)
    return root


def _xmlify_groups(
    groups: List[Group],
    tag_name: str,
) -> ET.Element:
    xml_groups = ET.Element(tag_name)
    # Ensure xml is deterministic.
    groups.sort(key=lambda s: s.get_id())
    for group in groups:
        xml_group = _xmlify_group(group, "group")
        xml_groups.append(xml_group)
    return xml_groups


def _xmlify_net(net: GroupNet, tag_name: str) -> ET.Element:
    xml_net = ET.Element(tag_name)
    # Ensure xml is deterministic.
    nodes = list(net)
    nodes.sort()
    for node in nodes:
        xml_node = ET.SubElement(xml_net, "node")
        xml_node.set("schematic", node.group_id.schematic)
        xml_node.set("path", node.group_id.path)
        xml_node.set("type", node.group_id.group_type)
        xml_node.set("pin", node.pin)
    return xml_net


def _xmlify_nets(nets: List[GroupNet], tag_name: str) -> ET.Element:
    xml_nets = ET.Element(tag_name)
    # Ensure xml is deterministic.
    nets.sort(key=lambda n: bytes(ET.tostring(_xmlify_net(n, "net"), encoding="utf-8")))
    for net in nets:
        xml_net = _xmlify_net(net, "net")
        xml_nets.append(xml_net)
    return xml_nets


def _create_xml_root(
    sources: Set[Path], date: datetime, tool: str, tag_name: str
) -> ET.Element:
    root = ET.Element(tag_name)
    warning_comment = ET.Comment(XML_WARNING)
    root.append(warning_comment)

    netlist = ET.SubElement(root, "netlist")
    sources_tag = ET.SubElement(netlist, "sources")
    sources_list = list(sources)
    sources_list.sort()
    for source in sources_list:
        source_tag = ET.SubElement(sources_tag, "source")
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


def stringify_group_netlist(group_netlist: GroupNetlist) -> bytes:
    root = _create_xml_root(
        group_netlist.sources,
        group_netlist.date,
        group_netlist.tool,
        "groupNetlist",
    )
    root.append(
        _xmlify_groups(
            list(group_netlist.groups.values()),
            "groups",
        )
    )
    assert GroupNet(frozenset()) not in group_netlist.nets
    root.append(_xmlify_nets(list(group_netlist.nets), "nets"))
    return _stringify_xml(root)
