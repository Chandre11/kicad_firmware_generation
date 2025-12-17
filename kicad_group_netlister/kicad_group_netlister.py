import argparse
from collections import deque
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, FrozenSet, Set, Tuple

from common_types.group_types import (
    GlobalGroupPinIdentifier,
    Group,
    GroupGlob,
    GroupIdentifier,
    GroupNet,
    GroupNetlist,
    GroupPath,
    GroupPinName,
    GroupType,
    MutableGroupNet,
    compile_group_glob,
    does_match_pattern,
    stringify_group_id,
)
from common_types.stringify_xml import stringify_group_netlist
from kicad_group_netlister.kicad_netlist_xml import parse_kicad_netlist
from kicad_group_netlister.kicad_types import (
    GlobalKiCadPinIdentifier,
    GroupPinNameLookups,
    GroupsReverseLookup,
    KiCadComponentRef,
    KiCadNetlist,
    KiCadNodePinName,
    KiCadSheetPath,
    RawGroup,
    RawGroupLookup,
)

GROUP_TYPE_FIELD_NAME = "GroupType"
GROUP_PIN_FIELD_PREFIX = "GroupPin"
GROUP_MAP_FIELD_PREFIX = "GroupMapField"
# TODO: set this properly
TOOL_NAME = "kicad_group_netlister v0.1.0"


def _group_components_by_group(
    netlist: KiCadNetlist,
) -> Tuple[RawGroupLookup, GroupsReverseLookup]:
    groups = RawGroupLookup(dict())
    reverse_lookup = GroupsReverseLookup(dict())
    for component in netlist.components.values():
        if GROUP_TYPE_FIELD_NAME not in component.fields:
            false_friend_fields = [
                field
                for field in component.fields.keys()
                if field.startswith(GROUP_PIN_FIELD_PREFIX)
                or field.startswith(GROUP_MAP_FIELD_PREFIX)
            ]
            if len(false_friend_fields) != 0:
                print(
                    f"Warning: The component {component.ref} defines the {'fields' if len(false_friend_fields) > 1 else 'field'} {', '.join(false_friend_fields)} but not the field {GROUP_TYPE_FIELD_NAME}.\n"
                    "Therefore, it is not part of a group.",
                    file=sys.stderr,
                )

            # This component is not part of any group.
            continue
        group_type = GroupType(component.fields[GROUP_TYPE_FIELD_NAME])
        group_path = GroupPath(component.sheetpath)
        group_identifier = GroupIdentifier((netlist.schematic, group_path, group_type))

        if group_identifier not in groups:
            groups[group_identifier] = RawGroup()
            groups[group_identifier].schematic = netlist.schematic
            groups[group_identifier].path = group_path
            groups[group_identifier].type_name = group_type
            groups[group_identifier].components = {component}
            groups[group_identifier].group_map_fields = dict()
        else:
            groups[group_identifier].components.add(component)

        for field_name, field_value in component.fields.items():
            if not field_name.startswith(GROUP_MAP_FIELD_PREFIX):
                # This is not a GroupMapField.
                continue
            group_map_field_name = field_name[len(GROUP_MAP_FIELD_PREFIX) :]
            if len(group_map_field_name) == 0:
                print(
                    f"Warning: The group {stringify_group_id(group_identifier)} contains a GroupMapField with the empty string as key.",
                    file=sys.stderr,
                )

            if group_map_field_name in groups[group_identifier].group_map_fields:
                print(
                    f"Error: The group {stringify_group_id(group_identifier)} contains the GroupMapField {group_map_field_name} twice.\n"
                    f"They have the values {field_value} and {groups[group_identifier].group_map_fields[group_map_field_name]}.\n"
                    f"One is in component {component.ref}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            groups[group_identifier].group_map_fields[group_map_field_name] = (
                field_value
            )

        assert component.ref not in reverse_lookup
        reverse_lookup[component.ref] = group_identifier

    return (groups, reverse_lookup)


# Groups without a explicit naming don't appear in this dict.
def _get_explicit_pin_name_lookups(
    groups_lookup: RawGroupLookup,
) -> GroupPinNameLookups:
    explicit_pin_namings = GroupPinNameLookups(dict())
    for group_identifier, raw_group in groups_lookup.items():
        # Use this set to verify no GroupPin name is used twice for the same group.
        group_pin_names: Set[GroupPinName] = set()
        for component in raw_group.components:
            for field_name, field_value in component.fields.items():
                # Only consider field names that define explic GroupPin names.
                if not field_name.startswith(GROUP_PIN_FIELD_PREFIX):
                    continue

                # After the GroupPin prefix comes the pin shown in KiCad that belongs to the component.
                node_pin_name = KiCadNodePinName(
                    field_name[len(GROUP_PIN_FIELD_PREFIX) :]
                )
                global_pin_identifier = GlobalKiCadPinIdentifier((
                    component.ref,
                    node_pin_name,
                ))
                # We can't have the same globally unique reference for two pins.
                for other_expicit_in_naming_group in explicit_pin_namings.values():
                    assert global_pin_identifier not in other_expicit_in_naming_group

                # This is the name the user explicitly set for this pin.
                group_pin_name = GroupPinName(field_value)
                if group_pin_name in group_pin_names:
                    print(
                        f"Error: The GroupPin {group_pin_name} exists at least twice for the group {stringify_group_id(group_identifier)}.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                group_pin_names.add(group_pin_name)

                # update explicit_pin_namings
                if group_identifier in explicit_pin_namings:
                    explicit_pin_namings[group_identifier][global_pin_identifier] = (
                        group_pin_name
                    )
                else:
                    explicit_pin_namings[group_identifier] = {
                        global_pin_identifier: group_pin_name
                    }
    return explicit_pin_namings


# The KiCad netlist connects pins on components to other pins on other components.
# This function converts that netlist into a netlist that connects pins on groups to other pins on other groups.
# The names of the pins are the GroupPin names and not the KiCad pin names any longer.
def _gen_group_netlist(
    netlist: KiCadNetlist,
    raw_groups_lookup: RawGroupLookup,
    groups_reverse_lookup: GroupsReverseLookup,
) -> GroupNetlist:
    explicit_pin_name_lookups = _get_explicit_pin_name_lookups(raw_groups_lookup)

    # We only use this to check that no two components have the same global group pin identifier.
    global_group_pin_to_component: Dict[GlobalGroupPinIdentifier, KiCadComponentRef] = (
        dict()
    )

    group_netlist = GroupNetlist()
    group_netlist.sources = {netlist.source}
    group_netlist.date = datetime.now()
    group_netlist.tool = TOOL_NAME

    # Create representations for all groups without their pins.
    # same as raw_groups_lookup but this time with the final Group class
    groups_lookup: Dict[GroupIdentifier, Group] = dict()
    for raw_group in raw_groups_lookup.values():
        group = Group()
        group.schematic = raw_group.schematic
        group.path = raw_group.path
        group.type_name = raw_group.type_name
        group.group_map_fields = raw_group.group_map_fields
        # We populate the pins when we loop over all nets.
        group.pins = dict()
        group_id = raw_group.get_id()
        assert group_id not in groups_lookup
        groups_lookup[group_id] = group

    group_netlist.nets = set()
    for net in netlist.nets:
        group_net = MutableGroupNet(set())
        for node in net:
            if node.ref not in groups_reverse_lookup:
                # The node does not belong to a component that belongs to a group.
                continue
            group_identifier = groups_reverse_lookup[node.ref]
            global_pin_identifier = GlobalKiCadPinIdentifier((node.ref, node.pin))

            # Figure out what name this pin has.
            group_pin_name: GroupPinName
            if group_identifier in explicit_pin_name_lookups:
                explicit_pin_name_lookup = explicit_pin_name_lookups[group_identifier]
                if global_pin_identifier not in explicit_pin_name_lookup:
                    # The pin does belong to components that belong to the group.
                    # Nevertheless, the user chose to explicitly define GroupPin names to some of the group's pins and this pin doesn't have one.
                    # Therefore, we don't consider this pin to belong to the group.
                    continue
                group_pin_name = explicit_pin_name_lookup[global_pin_identifier]
            else:
                # When the user didn't define any GroupPin names for at all we use a fallback:
                # We consider all pins that belong to components that belong to the group as pins of the group.
                group_pin_name = GroupPinName(node.pinfunction)

            # Assign None because we represent connections using nets and not other pins in the groups.
            groups_lookup[group_identifier].pins[group_pin_name] = None

            # This uniquely identifies the pin in the entire group map.
            global_group_pin_identifier = GlobalGroupPinIdentifier((
                group_identifier,
                group_pin_name,
            ))

            if (
                global_group_pin_identifier in global_group_pin_to_component
                and global_group_pin_to_component[global_group_pin_identifier]
                != node.ref
            ):
                print(
                    f"Error: The pin {group_pin_name} in the group {stringify_group_id(group_identifier)} occurs in multiple components: {global_group_pin_to_component[global_group_pin_identifier]} and {node.ref}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            global_group_pin_to_component[global_group_pin_identifier] = node.ref

            # This might very well be the only pin in the group net.
            group_net.add(global_group_pin_identifier)
        group_netlist.nets.add(GroupNet(frozenset(group_net)))

    group_netlist.groups = groups_lookup

    for group in group_netlist.groups.values():
        if len(group.pins) == 0:
            print(
                f"Warning: The group {stringify_group_id(group.get_id())} has no pins.",
                file=sys.stderr,
            )

    return group_netlist


# There are a few stupid things one can do with a netlist.
# This function ensures the electrical engineer didn't do such things and exits otherwise.
def _check_kicad_netlist_structure(netlist: KiCadNetlist) -> None:
    sheet_paths: Set[KiCadSheetPath] = set()
    # The first element is required path and second is the requiring path.
    required_paths: Set[Tuple[KiCadSheetPath, KiCadSheetPath]] = set()

    for sheet in netlist.sheets:
        # The root sheet has path `/`.
        # Any other sheet has a path like `/asfd/`.
        assert len(sheet.path) >= 1
        assert sheet.path[0] == "/"
        assert sheet.path[-1] == "/"

        if sheet.path in sheet_paths:
            print(
                f"Error: two sheets have the same path {sheet.path}.",
                file=sys.stderr,
            )
            sys.exit(1)
        sheet_paths.add(sheet.path)

        nodes = sheet.path.split("/")
        assert len(nodes) > 1
        # Don't do this when we're already at the root.
        if len(nodes) > 2:
            required_paths.add((
                KiCadSheetPath("/".join(nodes[:-1]) + "/"),
                sheet.path,
            ))

    for required_path, requiring_path in required_paths:
        if required_path not in sheet_paths:
            # TODO: read the schematics file directly and figure this out perfectly.
            print(
                f"Warning: The the last node of sheet path {requiring_path} uses the character `/`. "
                "This is not allowed because then separating path nodes isn't possible. "
                f"The script knows this because it didn't find {required_path}. ",
                "You need to fix this as this should be an error! ",
                "Though, this is a warning because there are situations in which the script doesn't notice the user's stupidity. ",
                "You need to watch out for this yourself.",
                file=sys.stderr,
            )
            sys.exit(1)


# TODO: maybe break this into a separate tool.
# TODO: This doesn't have anything to do with kicad.
def _merge_group_netlists(netlists: Set[GroupNetlist]) -> GroupNetlist:
    netlists_list = list(netlists)
    assert len(netlists_list) > 0
    netlist = netlists_list[0]
    for new_netlist in netlists_list[1:]:
        for source in netlist.sources:
            assert source not in new_netlist.sources
        netlist.sources |= new_netlist.sources
        for group_id in netlist.groups.keys():
            assert group_id not in new_netlist.groups
        netlist.groups |= new_netlist.groups
        for net in netlist.nets:
            assert net not in new_netlist.nets
        netlist.nets |= new_netlist.nets
    return netlist


# TODO: maybe break this into a separate tool.
# TODO: This doesn't have anything to do with kicad.
def _connect_netlist(
    netlist: GroupNetlist, connect_group_globs: Set[GroupGlob]
) -> GroupNetlist:
    # For each group glob figure out what groups it matches.
    to_connect_group_sets: Set[FrozenSet[GroupIdentifier]] = set()
    for connect_group_glob in connect_group_globs:
        to_connect_group_set: Set[GroupIdentifier] = set()
        for group_id in netlist.groups:
            if not does_match_pattern(connect_group_glob, group_id):
                continue
            # Ensure we only connect groups that can be connected.
            if len(to_connect_group_set) != 0:
                group = netlist.groups[group_id]
                other_group = netlist.groups[list(to_connect_group_set)[0]]
                if set(other_group.pins.keys()) != set(group.pins.keys()):
                    print(
                        f"Error: The connect group glob pattern {connect_group_glob} matches both {stringify_group_id(group.get_id())} and {stringify_group_id(other_group.get_id())} but they don't have the same pins.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            to_connect_group_set.add(group_id)

        print(f"Merging groups: {to_connect_group_set}", file=sys.stderr)
        if len(to_connect_group_set) < 2:
            print(
                f"Warning: The connect group glob pattern {connect_group_glob} matches fewer than two groups: {to_connect_group_set}.",
                file=sys.stderr,
            )
        to_connect_group_sets.add(frozenset(to_connect_group_set))

    # This relation should be transitive but isn't.
    # We implement the transitive nature further down.
    def should_nets_be_merged(net_a: GroupNet, net_b: GroupNet) -> bool:
        if net_a == net_b:
            return True
        # All groups that are in net_a.
        net_a_groups = {node[0] for node in net_a}
        # All groups that are in net_b.
        net_b_groups = {node[0] for node in net_a}
        for group_set in to_connect_group_sets:
            if len(net_a_groups & group_set) == 0:
                # No group that matches this glob is connected to net_a.
                continue
            if len(net_b_groups & group_set) == 0:
                # No group that matches this glob is connected to net_b.
                continue
            # if "PO_PROTECTED_NONE" in {
            #     node[1] for node in net_a
            # } and "PO_PROTECTED_NONE" in {node[1] for node in net_b}:
            #     print(
            #         f"{set({node for node in net_a if node[0] in group_set})}, {set({node for node in net_b if node[0] in group_set})} should maybe be merged.",
            #         file=sys.stderr,
            #     )
            #     # print(
            #     #     f"{net_a}, {net_b} should maybe be merged.",
            #     #     file=sys.stderr,
            #     # )
            # So there are a few groups that are in net_a and to be connected.
            # What pins of those groups are connected to this net?
            net_a_pins = {node[1] for node in net_a if (node[0] in group_set)}
            net_b_pins = {node[1] for node in net_b if (node[0] in group_set)}
            # if (
            #     net_a_pins
            #     and net_b_pins
            #     and "PO_PROTECTED_NONE" in net_a_pins
            #     or "PO_PROTECTED_NONE" in net_b_pins
            # ):
            # print(
            #     f"{net_a_group_intersection}, {net_b_group_intersection} should maybe be merged.",
            #     file=sys.stderr,
            # )
            # print(
            #     f"{net_a}|{net_b}",
            #     file=sys.stderr,
            # )
            # print(
            #     f"{net_a_pins}{net_b_pins} should maybe be merged.",
            #     file=sys.stderr,
            # )
            # If the same pin is present in both nets and the groups those pins belong to, should be connected, the pins should be connected (i.e., the nets should be connected).
            if len(net_a_pins & net_b_pins) != 0:
                print(f"{net_a}, {net_b} should be merged.", file=sys.stderr)
                return True
        return False

    # for net_a in netlist.nets:
    #     for net_b in netlist.nets:
    #         if net_a == net_b:
    #             continue
    #         if should_nets_be_merged(net_a, net_b):
    #             print(f"HIT: {net_a}{net_b}", file=sys.stderr)

    out_nets: Set[GroupNet] = set()
    for net in netlist.nets:
        unioned = False
        # Should this net be unioned instead of appended?
        for out_net in out_nets:
            assert should_nets_be_merged(net, out_net) == should_nets_be_merged(
                out_net, net
            )
            if should_nets_be_merged(net, out_net):
                print(f"Merging nets: {net} {out_net}", file=sys.stderr)
                # Update the old net with the new nodes.
                out_nets.remove(out_net)
                out_net |= net
                out_nets.add(GroupNet(out_net))
                unioned = True
                break
        if not unioned:
            out_nets.add(net)

    # We perform a breadth-first-search to implement the transitive relation.
    # while True:
    #     if len(netlist.nets) == 0:
    #         break

    #     net = netlist.nets.pop()
    #     # Nets to walk over later.
    #     found: deque[GroupNet] = deque()
    #     found.append(net)
    #     # All the nets that should be merged with net.
    #     nets_to_merge: Set[GroupNet] = set()
    #     while True:
    #         if len(found) == 0:
    #             break
    #         net = found.popleft()
    #         # Because we delete all nets that we've found from the original netlist.nets set this should never happen.
    #         # We never walk backwards.
    #         if net in nets_to_merge:
    #             assert False
    #             # continue
    #         nets_to_merge.add(net)
    #         to_connect_with_nets = {
    #             other_net
    #             for other_net in netlist.nets
    #             if should_nets_be_merged(net, other_net)
    #         }
    #         # We only want nets to be seen once.
    #         netlist.nets -= to_connect_with_nets
    #         found += to_connect_with_nets
    #     # Merge the nets to be merged.
    #     assert len(nets_to_merge) != 0
    #     merged_group_net: Set[GlobalGroupPinIdentifier] = set()
    #     if len(nets_to_merge) > 1:
    #         print(f"Merging nets: {nets_to_merge}", file=sys.stderr)
    #     for net in nets_to_merge:
    #         merged_group_net |= net
    #     out_nets.add(GroupNet(frozenset(merged_group_net)))

    netlist.nets = out_nets
    return netlist


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Convert a KiCad Netlist into a Group Netlist.",
    )
    parser.add_argument(
        "kicad_netlist_file",
        help="The path to a KiCad Netlist files (in the kicadxml format). "
        "You may provide multiple.",
        nargs="+",
    )
    parser.add_argument(
        "--connect-group-glob",
        help="All groups that match this glob are merged into a single one. "
        "All groups that match must have exactly the same pins. "
        "All matching groups are connected together. "
        "This reflects the use of a physical connector, connecting multiple schematics together. "
        "You may provide multiple.",
        action="append",
    )
    args = parser.parse_args()
    kicad_netlist_paths = {Path(path) for path in args.kicad_netlist_file}

    group_schematic_netlists: Set[GroupNetlist] = set()

    for kicad_netlist_path in kicad_netlist_paths:
        kicad_netlist = parse_kicad_netlist(kicad_netlist_path)
        _check_kicad_netlist_structure(kicad_netlist)

        groups_lookup, groups_reverse_lookup = _group_components_by_group(kicad_netlist)

        group_schematic_netlists.add(
            _gen_group_netlist(kicad_netlist, groups_lookup, groups_reverse_lookup)
        )

    merged_group_netlist = _merge_group_netlists(
        group_schematic_netlists,
    )
    connected_merged_group_netlist = _connect_netlist(
        merged_group_netlist,
        set()
        if args.connect_group_glob is None
        else {compile_group_glob(group_glob) for group_glob in args.connect_group_glob},
    )
    sys.stdout.buffer.write(stringify_group_netlist(connected_merged_group_netlist))


if __name__ == "__main__":
    main()
