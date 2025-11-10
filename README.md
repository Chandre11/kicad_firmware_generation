# KiCad Code Generation

Parse KiCad [intermediate XML netlist format](https://docs.kicad.org/9.0/en/eeschema/eeschema.html#generator-command-line-format).

Create the netlist, snippet_map and code like this:
```bash
kicad-cli sch export netlist --format kicadxml --output ICA_EPS_Distribution_netlist.xml ~/pluto_eps_distribution/ICA_EPS_Distribution.kicad_sch
python3 -m kicad_snippet_mapper.kicad_snippet_mapper ICA_EPS_Distribution_netlist.xml '/Controller/Controller' > ICA_EPS_Distribution_snippet_map.xml
python3 -m code_gen.code_gen ICA_EPS_Distribution_snippet_map.xml pluto_eps_templates/board.h.tmpl > board.h
```
