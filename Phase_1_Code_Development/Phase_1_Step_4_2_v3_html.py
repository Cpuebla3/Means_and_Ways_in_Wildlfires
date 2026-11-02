"""Run the original Phase 1 workflow and render its results as standalone HTML.

Usage (from any directory):
    python Phase_1_Step_4_2_v3_html.py
    python Phase_1_Step_4_2_v3_html.py --non-interactive

The default retains all terminal analyst confirmations and C/K dispositions.
Non-interactive reports preserve unconfirmed/incomplete statuses from the engine.
The HTML is read-only: analyst decisions continue to use the original workflow.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def batch_snapshot(engine) -> dict:
    """Show available workbook data without inventing missing analyst choices."""
    workbook = engine.resolve_workbook_path()
    engine.validate_workbook_sheets(workbook)
    definitions = engine.load_mission_class_definitions(workbook)
    engine.validate_mission_class_interface(definitions)
    mission_input = engine.load_mission_input(workbook)
    assessments = engine.classify_mission_candidates(
        engine.assess_mission_classes(mission_input, definitions)
    )
    decision = engine.resolve_mission_class(mission_input, assessments, definitions, interactive=False)
    mission = engine.Mission(decision, definitions,
                             engine.load_function_to_dimensions(workbook),
                             engine.load_baseline_mapping(workbook))
    catalog = engine.load_oe_catalog(workbook)
    oe_input = engine.load_oe_input_template(workbook, catalog)
    engine.validate_oe_input_state_ids(oe_input, catalog)
    # Validate explicit constraints against the complete catalog first.
    engine.extract_mission_constraint_states(mission_input, catalog)
    selected, unresolved = {}, []
    for parameter, states in catalog.items():
        scoped_input = dict(mission_input)
        for field, target in engine.MISSION_CONSTRAINT_TO_OE.items():
            if target != parameter:
                scoped_input[field] = None
        try:
            selected.update(engine.build_oe_vector(
                scoped_input, oe_input, {parameter: states}, interactive=False
            ))
        except RuntimeError as exc:
            if not str(exc).startswith("No OE state is available for"):
                raise
            unresolved.append(parameter)
    result = engine.resolve_oe_compatibility(
        selected, engine.load_compatibility_matrix(workbook), catalog, interactive=False
    )
    if unresolved:
        result["step42_complete"] = False
        # Admissibility cannot be determined for an incomplete OE vector.
        result["admissible"] = None
    return {"workbook_path": workbook, "mission_input": mission_input,
            "mission_class_assessment": assessments, "mission_class_decision": decision,
            "mission": mission, "oe_catalog": catalog, "step42_result": result,
            "unresolved_oe": unresolved}


def render_report(results: dict, output: Path, *, interactive: bool) -> None:
    """Render actual engine output; do not infer or resolve additional decisions."""
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "interactive": interactive,
        "workbook": Path(results["workbook_path"]).name,
        "mission_input": results["mission_input"],
        "mission_class_assessment": results["mission_class_assessment"],
        "mission_class_decision": results["mission_class_decision"],
        "mission": vars(results["mission"]),
        "oe_catalog": results["oe_catalog"],
        "step42_result": results["step42_result"],
        "unresolved_oe": results.get("unresolved_oe", []),
    }
    # Escape '<' so workbook text cannot terminate the inert JSON script block.
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = HERE / "Phase_1_Step_4_2_v3_report_template.html"
    output.write_text(template.read_text(encoding="utf-8").replace("__PHASE1_DATA__", data), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, help="Workbook; defaults to the latest expected workbook beside the original script.")
    parser.add_argument("--output", type=Path, default=HERE / "Phase_1_Step_4_2_v3_output.html")
    parser.add_argument("--non-interactive", action="store_true", help="Use batch inputs; leave analyst confirmations and K dispositions unresolved.")
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("phase1_engine", HERE / "Phase_1_Step_4_2_v3.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    engine.INTERACTIVE = not args.non_interactive
    if args.workbook:
        engine.WORKBOOK_PATH = str(args.workbook.resolve())
    else:
        engine.WORKBOOK_PATH = str(next(
            (HERE / name for name in engine.WORKBOOK_CANDIDATES if (HERE / name).exists()),
            HERE / engine.WORKBOOK_CANDIDATES[0],
        ))
    results = engine.main() if engine.INTERACTIVE else batch_snapshot(engine)
    render_report(results, args.output.resolve(), interactive=engine.INTERACTIVE)
    print(f"\nHTML report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
