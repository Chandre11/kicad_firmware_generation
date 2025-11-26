import sys
from datetime import datetime
from pathlib import Path

from common_types.parse_xml import parse_group_netlist
from common_types.group_types import (
    OtherGroupPinType,
    GroupIdentifier,
    GroupMap,
    GroupNetlist,
    GroupPath,
    GroupPinName,
    GroupType,
    stringify_group_id,
)
from common_types.stringify_xml import stringify_group_map

GROUP_TYPE_FIELD_NAME = "GroupType"
# TODO: set this properly
TOOL_NAME = "group_one_to_many_mapper v0.1.0"


def _gen_one_to_many_group_map(
    netlist: GroupNetlist, root_group_identifier: GroupIdentifier
) -> GroupMap:
    # general metadata
    group_map = GroupMap()
    group_map.map_type = OtherGroupPinType.ONE_TO_MANY
    group_map.source = netlist.source
    group_map.date = datetime.now()
    group_map.tool = TOOL_NAME

    if root_group_identifier not in netlist.groups:
        all_group_identifiers = ", ".join([
            f"{stringify_group_id(group_id)}" for group_id in netlist.groups.keys()
        ])
        all_group_print = (
            f"There are no groups. Define them by specifying at least one component with the {GROUP_TYPE_FIELD_NAME} field."
            if len(all_group_identifiers) == 0
            else f"These groups exist: {all_group_identifiers}"
        )
        print(
            f"Error: Didn't find a root group with identifier {stringify_group_id(root_group_identifier)}.\n{all_group_print}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Figure out what groups are connected how.
    for net in netlist.nets:
        # Some nets contain a root group pin, others don't.
        root_group_pin_name: GroupPinName | None = None
        for group_identifier, group_pin_name in net:
            # Does this pin belong to the root group?
            if group_identifier == root_group_identifier:
                if root_group_pin_name is not None:
                    print(
                        f"Warning: At least two pins of the root group {stringify_group_id(root_group_identifier)}, {group_pin_name} and {root_group_pin_name} are connected together.\n"
                        "The entire net these pins are connected to will not be part of the group map.",
                        file=sys.stderr,
                    )
                    # Remove those pins from the root group.
                    for group_id_of_in_to_remove, pin_name_to_remove in net:
                        if group_id_of_in_to_remove != root_group_identifier:
                            # Skip all groups that aren't the root group.
                            # Those groups get to keep all their pins.
                            continue
                        print(group_identifier, pin_name_to_remove, file=sys.stderr)
                        netlist.groups[root_group_identifier].pins.pop(
                            pin_name_to_remove
                        )
                    root_group_pin_name = None
                    break
                root_group_pin_name = group_pin_name

        if root_group_pin_name is None:
            # We didn't find a root group's pin in this net.
            continue

        for group_identifier, group_pin_name in net:
            # Does this pin belong to the root group?
            if group_identifier == root_group_identifier:
                # We've already figured out what root pin this net is connected to.
                # The root group's pins are all set to None already, so we don't have to do anything.
                continue
            # No one has touched this before so it must have remained None.
            assert netlist.groups[group_identifier].pins[group_pin_name] is None
            # Because we only do this when this isn't a root group, all pins of the root group are connected to None.
            netlist.groups[group_identifier].pins[group_pin_name] = root_group_pin_name

    group_map.groups = {
        group
        for group in netlist.groups.values()
        if group.get_id() != root_group_identifier
    }
    assert root_group_identifier not in {group.get_id() for group in group_map.groups}
    group_map.root_group = netlist.groups[root_group_identifier]

    return group_map


def _get_group_identifier(in_str: str) -> GroupIdentifier:
    idx = in_str.rfind("/")
    if "/" not in in_str:
        print(
            "Error: group identifier must contain at least one `/`.",
            file=sys.stderr,
        )
        sys.exit(1)
    return GroupIdentifier((
        GroupPath(in_str[0 : idx + 1]),
        GroupType(in_str[idx + 1 :]),
    ))


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Error: Provide two arguments: the input group netlist file path and the root group name.",
            file=sys.stderr,
        )
        sys.exit(1)
    group_netlist_path = Path(sys.argv[1])
    root_group_identifier = _get_group_identifier(sys.argv[2])
    group_netlist = parse_group_netlist(group_netlist_path)
    group_map = _gen_one_to_many_group_map(group_netlist, root_group_identifier)
    sys.stdout.buffer.write(stringify_group_map(group_map))


if __name__ == "__main__":
    main()
