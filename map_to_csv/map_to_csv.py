import argparse
import csv
from pathlib import Path
import sys
from typing import Tuple
import re

from common_types.parse_xml import parse_many_to_many_snippet_map
from common_types.snippet_types import stringify_snippet_id

# TODO: set this properly
TOOL_NAME = "snippet_many_to_many_map_to_csv v0.1.0"

sort_key_pattern = re.compile(r"[^A-Za-z](\d+)")


def _get_sort_key(name: str) -> Tuple[int, str]:
    matches = re.findall(sort_key_pattern, name)
    num = 0 if len(matches) == 0 else int(matches[-1])
    return num, name


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Convert a many-to-many snippet map to a csv.",
    )
    parser.add_argument(
        "snippet_many_to_many_map", help="The path to the snippet_many_to_many_map."
    )
    args = parser.parse_args()

    snippet_many_to_many_map = Path(args.snippet_many_to_many_map)
    map = parse_many_to_many_snippet_map(snippet_many_to_many_map)

    csv_writer = csv.DictWriter(
        sys.stdout,
        delimiter=",",
        quotechar='"',
        fieldnames=["snippet_path", "snippet_type", "pin_name", "other_pins"],
        quoting=csv.QUOTE_MINIMAL,
    )
    csv_writer.writeheader()
    snippets = list(map.snippets)
    snippets.sort(key=lambda s: stringify_snippet_id(s.get_id()))
    for snippet in snippets:
        pins = list(snippet.pins.items())
        pins.sort(key=lambda p: _get_sort_key(p[0]))
        for pin_name, other_pins in pins:
            # This should be Set[GlobalSnippetPinIdentifier] but that isn't known at runtime.
            assert type(other_pins) is set
            other_pins_list = list(other_pins)
            other_pins_list.sort()
            other_pins_str = "|".join([
                stringify_snippet_id(other_snippet_id) + "/" + other_pin
                for other_snippet_id, other_pin in other_pins_list
            ])
            csv_writer.writerow({
                "snippet_path": snippet.path,
                "snippet_type": snippet.type_name,
                "pin_name": pin_name,
                "other_pins": other_pins_str,
            })


if __name__ == "__main__":
    main()
