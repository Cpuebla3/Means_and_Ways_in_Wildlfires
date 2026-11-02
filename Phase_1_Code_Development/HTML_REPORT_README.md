# Phase 1 HTML report

Open `Phase_1_Step_4_2_v3_output.html` in a web browser. It is self-contained,
works offline, and displays baseline capability requirements in red.

The report includes mission provenance, function–dimension mappings, searchable
baseline requirements, selected OE states, and a clickable C/K/X matrix. It also
provides JSON download and browser print / PDF controls.

## Regenerate after updating the workbook

Requires Python 3.10+, `pandas`, and `openpyxl`, as does the original script.
From the repository root:

```sh
python3 Phase_1_Code_Development/Phase_1_Step_4_2_v3_html.py
```

This runs the original `main()` workflow, including terminal analyst prompts,
then writes the HTML report. The original Python script and workbook are not
modified. Keep the HTML template beside the generator.

To generate an available-data snapshot without answering analyst prompts:

```sh
python3 Phase_1_Code_Development/Phase_1_Step_4_2_v3_html.py --non-interactive
```

Batch mode uses the original engine's loaders and decision functions. It leaves
inferred decisions unconfirmed, lists missing OE selections, and evaluates only
pairs of available states. Missing selections keep Step 4.2 incomplete and
scenario admissibility undetermined; K dispositions are never auto-accepted.

Use `--workbook PATH` or `--output PATH` to choose another workbook or output file.
By default, the generator selects the first existing workbook from the original
script's candidate list, beside the script, and saves the report in this folder.

The included report is a batch snapshot of the September 29 workbook. It has 11
baseline requirements, 12 of 14 OE states, and 66 of 91 required pair checks (65 C,
1 K, 0 X). Terrain/geography and proximity to water resources need selections;
the inferred mission class and conditional pair still need analyst review.
