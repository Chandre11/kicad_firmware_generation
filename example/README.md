- [`schematics`](./schematics) contains the input KiCad schematics,
- [`pindefs.h`](./pindefs.h) is the final output file.
  Our tools automatically generate it.
- [`template.jinja2`](./template.jinja2) is the template to generate the output with,
- [`kicad_netlist.xml`](./kicad_netlist.xml) is the intermediary KiCad Netlist and
- [`group_netlist.xml`](./group_netlist.xml) is the intermediary Group Netlist.
