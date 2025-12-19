import argparse
import csv
from pathlib import Path
import sys
from typing import Set, Tuple
import re

from common_types.group_types import (
    GlobalGroupPinIdentifier,
    GroupIdentifier,
    GroupNetlistWithConnections,
    GroupPath,
    GroupPinName,
    GroupType,
    Schematic,
    connect_netlist,
    stringify_group_id,
)
from common_types.parse_xml import parse_group_netlist

# TODO: set this properly
TOOL_NAME = "group_many_to_many_map_to_csv v0.1.0"

sort_key_pattern = re.compile(r"(\d+)")


def _get_sort_key(name: str) -> Tuple[int, str]:
    matches = re.findall(sort_key_pattern, name)
    num = 0 if len(matches) == 0 else int(matches[-1])
    return num, name


def _simplify_nets(
    netlist: GroupNetlistWithConnections,
    simplify_pins: Set[GroupPinName],
) -> GroupNetlistWithConnections:
    # Simplify some nets.
    for group in netlist.groups.values():
        for pin in group.pins.values():
            # Check if this net can be simplified.

            # Not None iff we found a simplification.
            found_simplify_pin: GroupPinName | None = None
            for _, other_pin in pin:
                for simplify_pin in simplify_pins:
                    if simplify_pin in other_pin:
                        found_simplify_pin = simplify_pin
                        print(
                            f"Warning: Simplifying {other_pin} to {found_simplify_pin}",
                            file=sys.stderr,
                        )
                        break
                if found_simplify_pin is not None:
                    break
            if found_simplify_pin is not None:
                pin.clear()
                pin.add(
                    GlobalGroupPinIdentifier(
                        GroupIdentifier(
                            # TODO: do this better
                            Schematic("This_was"),
                            GroupPath("/Simplified/"),
                            GroupType("Away"),
                        ),
                        found_simplify_pin,
                    )
                )

    return netlist


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Convert a group netlist to a csv. "
        "The output is printed to stdout, errors and warnings to stderr.",
    )
    parser.add_argument("group_netlist_path", help="The path to the group netlist.")
    parser.add_argument(
        "--simplify-pins",
        help="If a group connects to a pin that has this field as a substring, reduce all pins that belong to this net to a single pin with the provided name. "
        "Separate multiple values with a comma (,). "
        "When more than on simplification matches, an arbitraty one will be chosen."
        "This is, for example, useful to replace all GND connections with a single GND pin.",
    )
    args = parser.parse_args()

    group_netlist_path = Path(args.group_netlist_path)

    simplify_pins: Set[GroupPinName] = {
        GroupPinName(pin)
        for pin in ([] if args.simplify_pins is None else args.simplify_pins.split(","))
    }

    netlist = connect_netlist(parse_group_netlist(group_netlist_path))
    simple_netlist = _simplify_nets(netlist, simplify_pins)

    csv_writer = csv.DictWriter(
        sys.stdout,
        delimiter=",",
        quotechar='"',
        fieldnames=["schematic", "group_path", "group_type", "pin_name", "other_pins"],
        quoting=csv.QUOTE_MINIMAL,
    )
    csv_writer.writeheader()
    group_ids = list(simple_netlist.groups.keys())
    group_ids.sort()
    for group_id in group_ids:
        group = simple_netlist.groups[group_id]
        pins = list(group.pins.items())
        pins.sort(key=lambda p: _get_sort_key(p[0]))
        for pin_name, other_pins in pins:
            other_pins_list = list(other_pins)
            other_pins_list.sort()
            other_pins_str = "|".join([
                stringify_group_id(other_group_id) + "/" + other_pin
                for other_group_id, other_pin in other_pins_list
            ])
            csv_writer.writerow({
                "schematic": group.schematic,
                "group_path": group.path,
                "group_type": group.group_type,
                "pin_name": pin_name,
                "other_pins": other_pins_str,
            })


if __name__ == "__main__":
    main()
