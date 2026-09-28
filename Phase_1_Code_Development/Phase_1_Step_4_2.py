"""
PHASE 1 - OPERATIONAL SCENARIO DEVELOPMENT
Revision: Workbook-driven reference data + coded decision rules
Implemented through Step 4.2

PURPOSE
-------
This single Python program implements the current Phase 1 workflow:

    Mission input
        -> Mission-class assessment and analyst confirmation
        -> Step 1: final mission class
        -> Step 2: operational functions
        -> Step 3: linked capability dimensions and baseline capability requirements
        -> Step 4.1: select exactly one OE state per OE parameter
        -> Step 4.2: screen all selected OE-state pairs for C/K/X compatibility

ARCHITECTURAL PRINCIPLE
-----------------------
The workbook is the human-readable reference/data repository.
Python is the executable implementation of the methodology.

The program READS the following workbook sheets:
    1. Mission Class Definitions
       - mission-class names, definitions, documentation/source basis
    2. Mission Input Template
       - current mission/tasking values
    3. Baseline Mapping
       - function -> linked capability dimensions
       - baseline capability requirements
    4. OE State Definitions
       - valid OE parameters/states and selection guidance
    5. OE Input Template
       - optional structured planning State IDs and optional explicit
         mission/tasking State IDs
    6. OE Compatibility
       - C/K/X pairwise compatibility matrix

The following remain CODED in Python:
    - mission-class inference rules
    - mission-class -> operational-function mapping
    - source-precedence rules
    - OE inference rules
    - compatibility-screening logic
    - X-conflict resolution
    - traceability/provenance logic

The workbook sheets "Mission Class Rules", "OE Selection Rules", and
"Code Interface" are documentation/reference sheets. They are not used as
executable rule engines in this revision.

TRACEABILITY
------------
Every consequential inferred/selected value is represented by:

    value
    source     = explicit | inferred | user_selected
    status     = accepted | confirmed | overridden | unconfirmed
    evidence
    rule_id
    history

IMPORTANT METHODOLOGICAL BOUNDARIES
-----------------------------------
1. Mission-class definitions describe operational context/effect and do not
   preselect Means.
2. Mission-class inference is decision support. If not explicitly assigned,
   the analyst confirms or overrides the recommendation.
3. Environmental states are not guessed when the available information does
   not support a unique selection.
4. Exactly one state is selected for each OE parameter.
5. An X incompatibility does NOT authorize automatic deletion of either state.
   The analyst must reconsider one of the conflicting parameters.
6. A K pair remains in the scenario and is explicitly carried forward.

REQUIREMENTS
------------
Python 3.10+
pandas
openpyxl

Typical installation:
    python -m pip install pandas openpyxl
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError as exc:
    raise ImportError(
        "This program requires pandas and openpyxl. Install them with:\n"
        "    python -m pip install pandas openpyxl"
    ) from exc

def load_oe_input_template(
    workbook_path: Path,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Load optional explicit Step 4.1 inputs from 'OE Input Template'.

    The workbook may supply:
        - Structured Planning State ID
        - Mission/Tasking State ID
        - Analyst-Selected State ID

    Blank cells remain None.

    Only rows whose OE Parameter matches one of the valid parameters
    in 'OE State Definitions' are treated as executable input rows.
    Explanatory/documentation rows in the worksheet are ignored.

    Final State ID / Final Source / Final Status are currently treated
    as documentation/output placeholders and are not executable inputs.
    """

    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_OE_INPUT,
        header=3,
    )

    required = [
        "OE Parameter",
        "Structured Planning State ID",
        "Mission/Tasking State ID",
        "Analyst-Selected State ID",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"'{SHEET_OE_INPUT}' is missing columns: {missing}"
        )

    # -------------------------------------------------------------
    # Valid OE parameters come from the authoritative OE catalog.
    # This prevents notes or documentation text elsewhere in the
    # worksheet from being interpreted as executable input rows.
    # -------------------------------------------------------------

    valid_parameters = set(oe_catalog.keys())

    result: Dict[str, Dict[str, Optional[str]]] = {}

    for _, row in df.iterrows():

        parameter = clean_cell(
            row["OE Parameter"]
        )

        # Ignore blank rows.
        if parameter is None:
            continue

        # Ignore explanatory/documentation rows.
        if parameter not in valid_parameters:
            continue

        result[parameter] = {
            "structured_planning_state_id":
                clean_cell(
                    row["Structured Planning State ID"]
                ),

            "mission_tasking_state_id":
                clean_cell(
                    row["Mission/Tasking State ID"]
                ),

            "analyst_selected_state_id":
                clean_cell(
                    row["Analyst-Selected State ID"]
                ),

            "planning_context_evidence":
                clean_cell(
                    row.get("Planning-Context Evidence")
                ),
        }

    # -------------------------------------------------------------
    # Confirm that all OE parameters are actually represented in
    # the input template.
    # -------------------------------------------------------------

    missing_parameters = [
        parameter
        for parameter in oe_catalog
        if parameter not in result
    ]

    if missing_parameters:
        raise ValueError(
            "OE Input Template is missing OE parameter rows: "
            f"{missing_parameters}"
        )

    return result
# =============================================================================
# 0. USER CONFIGURATION
# =============================================================================

# Set to a specific file path if desired. Leave as None to let the program
# search the current folder for the expected workbook.
WORKBOOK_PATH: Optional[str] = None

WORKBOOK_CANDIDATES = [
    "Wildfire_Capability_OE_Dictionary_09.27.26.xlsx",
    "Wildfire_Capability_OE_Dictionary_Expanded_09.25.26.xlsx",
    "Wildfire_Capability_OE_Dictionary_Expanded_09.25.26 (1).xlsx",
]

# True = analyst confirmation/completion is requested in the terminal.
# This is the intended mode for the current methodology.
INTERACTIVE = True

# If True, show OE operational definitions and selection rules when the analyst
# must choose a state. This is useful during testing but produces more output.
SHOW_OE_SELECTION_GUIDANCE = True


# =============================================================================
# 1. STABLE WORKBOOK INTERFACE
# =============================================================================

SHEET_MISSION_CLASSES = "Mission Class Definitions"
SHEET_MISSION_INPUT = "Mission Input Template"
SHEET_BASELINE_MAPPING = "Baseline Mapping"
SHEET_OE_STATES = "OE State Definitions"
SHEET_OE_INPUT = "OE Input Template"
SHEET_OE_COMPATIBILITY = "OE Compatibility"

REQUIRED_SHEETS = [
    SHEET_MISSION_CLASSES,
    SHEET_MISSION_INPUT,
    SHEET_BASELINE_MAPPING,
    SHEET_OE_STATES,
    SHEET_OE_INPUT,
    SHEET_OE_COMPATIBILITY,
]

# Stable workbook Field IDs -> internal code keys.
# The display wording in the workbook may be refined without changing these IDs.
MISSION_FIELD_MAP = {
    "MI-01": "mission_id",
    "MI-02": "mission_statement",
    "MI-03": "mission_class_explicit",
    "MI-04": "incident_response_status",
    "MI-05": "mission_effect",
    "MI-06": "area_of_operations",
    "MI-07": "primary_protected_values",
    "MI-08": "required_operational_effect",
    "MI-09": "time_objective",
    "MI-10": "operating_period",
    "MI-11": "airspace_constraint",
    "MI-12": "access_constraint",
    "MI-13": "visibility_constraint",
    "MI-14": "operating_site_constraint",
}

# Mission-input constraint fields mapped to OE parameters.
MISSION_CONSTRAINT_TO_OE = {
    "airspace_constraint": "Airspace complexity",
    "access_constraint": "Access/infrastructure",
    "visibility_constraint": "Environmental visibility",
    "operating_site_constraint": "Feasible operating-site availability",
}


# =============================================================================
# 2. EXECUTABLE METHODOLOGY RULES
# =============================================================================

# Mission -> functions remains coded because it is structural methodology logic.
MISSION_TO_FUNCTIONS = {
    "IA": ["Detection", "Monitoring", "Suppression", "Confinement"],
    "EA": ["Detection", "Monitoring", "Suppression", "Point Protection", "Confinement"],
    "LFO": ["Detection", "Monitoring", "Suppression", "Point Protection", "Confinement"],
    "WSP": ["Detection", "Monitoring", "Suppression", "Point Protection"],
    "FRM": ["Detection", "Monitoring"],
}


# Mission-class rules remain executable Python logic.
# Weights organize evidence; they are NOT probabilities.
MISSION_CLASS_RULES = {
    "IA": [
        {
            "rule_id": "MC-IA-STATUS",
            "field": "incident_response_status",
            "terms": [
                "new incident",
                "initial response",
                "initial-response",
                "initial attack",
            ],
            "weight": 5,
            "basis": (
                "Incident remains in the initial-response/initial-attack stage."
            ),
        },
        {
            "rule_id": "MC-IA-EFFECT",
            "field": "required_operational_effect",
            "terms": [
                "rapid containment",
                "extinguishment",
                "stop fire growth",
            ],
            "weight": 2,
            "basis": (
                "Mission effect is consistent with rapid early suppression."
            ),
        },
    ],
    "EA": [
        {
            "rule_id": "MC-EA-STATUS",
            "field": "incident_response_status",
            "terms": [
                "exceeded initial response",
                "extended attack",
                "beyond initial attack",
            ],
            "weight": 6,
            "basis": (
                "Incident has exceeded the initial-response stage."
            ),
        },
    ],
    "LFO": [
        {
            "rule_id": "MC-LFO-STATUS",
            "field": "incident_response_status",
            "terms": [
                "multi-operational-period",
                "multiple operational periods",
                "complex incident",
                "sustained incident",
                "large fire",
            ],
            "weight": 6,
            "basis": (
                "Incident status indicates sustained/complex wildfire operations."
            ),
        },
        {
            "rule_id": "MC-LFO-EFFECT",
            "field": "required_operational_effect",
            "terms": [
                "confinement",
                "spread limitation",
                "sustained suppression",
            ],
            "weight": 3,
            "basis": (
                "Mission effect is consistent with sustained control of fire spread."
            ),
        },
    ],
    "WSP": [
        {
            "rule_id": "MC-WSP-EFFECT",
            "field": "mission_effect",
            "terms": [
                "protect structures",
                "structure protection",
                "protect community",
                "protect wui",
                "asset protection",
            ],
            "weight": 6,
            "basis": (
                "Protection of built assets is explicitly the principal mission effect."
            ),
        },
        {
            "rule_id": "MC-WSP-VALUES",
            "field": "primary_protected_values",
            "terms": [
                "wui",
                "residential",
                "structures",
                "community",
                "critical infrastructure",
            ],
            "weight": 2,
            "basis": (
                "Protected values support WSP as a plausible embedded or governing mission."
            ),
        },
    ],
    "FRM": [
        {
            "rule_id": "MC-FRM-EFFECT",
            "field": "mission_effect",
            "terms": [
                "detect",
                "reconnaissance",
                "observe",
                "monitor",
                "locate",
                "characterize",
                "track",
            ],
            "weight": 6,
            "basis": (
                "Primary mission effect concerns information acquisition or updating."
            ),
        },
        {
            "rule_id": "MC-FRM-INFO",
            "field": "required_operational_effect",
            "terms": [
                "situational awareness",
                "fire-state update",
                "information collection",
            ],
            "weight": 4,
            "basis": (
                "Required effect is information-centered."
            ),
        },
    ],
}


# =============================================================================
# 3. GENERAL UTILITIES
# =============================================================================

def clean_cell(value: Any) -> Optional[str]:
    """Normalize a workbook cell value to stripped text or None."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    return text if text else None


def normalize_text(value: Any) -> str:
    """Normalize strings/lists/dicts for transparent phrase matching."""
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(str(item) for item in value).lower()

    if isinstance(value, dict):
        return " ".join(
            str(item)
            for item in value.values()
            if item is not None
        ).lower()

    return str(value).lower()


def ordered_unique(items) -> List[str]:
    """
    Remove duplicates while preserving original order.

    This intentionally replaces the original implementation:
        list(set(...))

    set() is useful for membership tests but should not be used to construct an
    ordered analytical output.
    """
    return list(dict.fromkeys(items))


def make_trace_record(
    value: str,
    source: str,
    evidence: Any,
    status: str = "accepted",
    rule_id: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a standardized traceability record."""
    return {
        "value": value,
        "source": source,
        "status": status,
        "evidence": evidence,
        "rule_id": rule_id,
        "history": [] if history is None else history,
    }


def resolve_workbook_path() -> Path:
    """Resolve the workbook path for local VS Code execution."""
    if WORKBOOK_PATH:
        path = Path(WORKBOOK_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Configured WORKBOOK_PATH does not exist:\n{path}"
            )
        return path

    for candidate in WORKBOOK_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path

    matches = sorted(
        Path(".").glob(
            "Wildfire_Capability_OE_Dictionary_Expanded_*.xlsx"
        ),
        reverse=True,
    )
    if matches:
        return matches[0]

    raise FileNotFoundError(
        "No Phase 1 workbook was found in the current folder.\n"
        "Place the workbook next to the Python script or set WORKBOOK_PATH."
    )


def validate_workbook_sheets(workbook_path: Path) -> None:
    """Fail early if the expected workbook interface is incomplete."""
    xl = pd.ExcelFile(workbook_path)
    missing = [
        sheet for sheet in REQUIRED_SHEETS
        if sheet not in xl.sheet_names
    ]

    if missing:
        raise ValueError(
            "Workbook is missing required sheet(s):\n  - "
            + "\n  - ".join(missing)
        )


# =============================================================================
# 4. WORKBOOK LOADERS
# =============================================================================

def load_mission_class_definitions(
    workbook_path: Path,
) -> Dict[str, Dict[str, Any]]:
    """
    Load human-readable mission-class definitions from the workbook.

    Sheet:
        Mission Class Definitions
    Header:
        Excel row 4 -> pandas header=3
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_MISSION_CLASSES,
        header=3,
    )

    required = [
        "Mission Class Code",
        "Mission Class",
        "Methodology Definition",
        "Definition Status",
        "Recognizable Operational/Doctrinal Basis",
        "Primary Source URL",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_MISSION_CLASSES}' is missing columns: {missing}"
        )

    df = df.dropna(subset=["Mission Class Code"])

    definitions = {}

    for _, row in df.iterrows():
        code = clean_cell(row["Mission Class Code"])
        if code is None:
            continue

        code = code.upper()

        definitions[code] = {
            "name": clean_cell(row["Mission Class"]),
            "definition": clean_cell(row["Methodology Definition"]),
            "definition_status": clean_cell(row["Definition Status"]),
            "source_basis": clean_cell(
                row["Recognizable Operational/Doctrinal Basis"]
            ),
            "primary_source_url": clean_cell(row["Primary Source URL"]),
            "secondary_note": clean_cell(
                row.get("Secondary Source / Note")
            ),
            "coding_note": clean_cell(row.get("Coding Note")),
        }

    required_codes = set(MISSION_TO_FUNCTIONS)
    missing_codes = required_codes - set(definitions)

    if missing_codes:
        raise ValueError(
            "Mission Class Definitions is missing required class codes: "
            f"{sorted(missing_codes)}"
        )

    return definitions


def load_mission_input(
    workbook_path: Path,
) -> Dict[str, Any]:
    """
    Load the current mission/tasking input from the workbook.

    Sheet:
        Mission Input Template
    Header:
        Excel row 4 -> pandas header=3

    Stable Field IDs are used as the workbook-code interface.
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_MISSION_INPUT,
        header=3,
    )

    required = [
        "Field ID",
        "Input Field",
        "Current Scenario Value",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_MISSION_INPUT}' is missing columns: {missing}"
        )

    df = df.dropna(subset=["Field ID"])

    raw_by_id = {}

    for _, row in df.iterrows():
        field_id = clean_cell(row["Field ID"])
        if field_id:
            raw_by_id[field_id] = clean_cell(
                row["Current Scenario Value"]
            )

    missing_ids = [
        field_id
        for field_id in MISSION_FIELD_MAP
        if field_id not in raw_by_id
    ]

    if missing_ids:
        raise ValueError(
            "Mission Input Template is missing required Field IDs: "
            f"{missing_ids}"
        )

    mission_input: Dict[str, Any] = {}

    for field_id, code_key in MISSION_FIELD_MAP.items():
        mission_input[code_key] = raw_by_id.get(field_id)

    # Convert protected values from semicolon-delimited workbook text to a list.
    values = mission_input.get("primary_protected_values")
    if values:
        mission_input["primary_protected_values"] = [
            item.strip()
            for item in str(values).split(";")
            if item.strip()
        ]
    else:
        mission_input["primary_protected_values"] = []

    # Normalize explicit mission-class code.
    explicit_class = mission_input.get("mission_class_explicit")
    if explicit_class:
        mission_input["mission_class_explicit"] = (
            str(explicit_class).strip().upper()
        )

    return mission_input


def load_function_to_dimensions(
    workbook_path: Path,
) -> Dict[str, List[str]]:
    """
    Load Step 2 function -> linked capability-dimension mapping.

    Sheet:
        Baseline Mapping
    Header:
        Excel row 7 -> pandas header=6
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_BASELINE_MAPPING,
        header=6,
    )

    required = [
        "Canonical Operational Function",
        "Linked Capability Dimensions",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_BASELINE_MAPPING}' Step 2 table is missing columns: "
            f"{missing}"
        )

    df = df.dropna(
        subset=[
            "Canonical Operational Function",
            "Linked Capability Dimensions",
        ]
    )

    mapping = {}

    for _, row in df.iterrows():
        function = clean_cell(
            row["Canonical Operational Function"]
        )
        raw_dimensions = clean_cell(
            row["Linked Capability Dimensions"]
        )

        if function is None or raw_dimensions is None:
            continue

        dimensions = [
            item.strip()
            for item in raw_dimensions.splitlines()
            if item.strip()
        ]

        mapping[function] = dimensions

    return mapping


def load_baseline_mapping(
    workbook_path: Path,
) -> Dict[str, Dict[str, Any]]:
    """
    Load Step 3 baseline capability requirements.

    Sheet:
        Baseline Mapping
    Header:
        Excel row 16 -> pandas header=15
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_BASELINE_MAPPING,
        header=15,
    )

    required = [
        "Baseline ID",
        "Baseline Capability Requirement",
        "Linked Phase 1 Step 2 Capability Dimensions",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_BASELINE_MAPPING}' Step 3 table is missing columns: "
            f"{missing}"
        )

    df = df.dropna(
        subset=[
            "Baseline ID",
            "Baseline Capability Requirement",
            "Linked Phase 1 Step 2 Capability Dimensions",
        ]
    )

    mapping = {}

    for _, row in df.iterrows():
        baseline_id = clean_cell(row["Baseline ID"])
        name = clean_cell(row["Baseline Capability Requirement"])
        raw_dimensions = clean_cell(
            row["Linked Phase 1 Step 2 Capability Dimensions"]
        )

        if (
            baseline_id is None
            or name is None
            or raw_dimensions is None
        ):
            continue

        dimensions = [
            item.strip()
            for item in raw_dimensions.splitlines()
            if item.strip()
        ]

        mapping[baseline_id] = {
            "name": name,
            "dimensions": dimensions,
            "primary_function_traceability": clean_cell(
                row.get("Primary Function Traceability")
            ),
            "status_note": clean_cell(row.get("Status / Note")),
        }

    return mapping


def load_oe_catalog(
    workbook_path: Path,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load valid OE parameters/states and analyst guidance.

    Sheet:
        OE State Definitions
    Header:
        Excel row 5 -> pandas header=4
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_OE_STATES,
        header=4,
    )

    required = [
        "State ID",
        "OE Parameter",
        "OE State",
        "Operational state definition",
        "Selection rule",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_OE_STATES}' is missing columns: {missing}"
        )

    df = df.dropna(
        subset=["State ID", "OE Parameter", "OE State"]
    )

    catalog: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df.iterrows():
        state_id = clean_cell(row["State ID"])
        parameter = clean_cell(row["OE Parameter"])
        state = clean_cell(row["OE State"])

        if state_id is None or parameter is None or state is None:
            continue

        catalog.setdefault(parameter, []).append({
            "state_id": state_id,
            "state": state,
            "parameter_definition": clean_cell(
                row.get("Parameter definition")
            ),
            "definition": clean_cell(
                row.get("Operational state definition")
            ),
            "selection_rule": clean_cell(
                row.get("Selection rule")
            ),
            "boundary_note": clean_cell(
                row.get("Boundary or modeling note")
            ),
        })

    return catalog


def load_oe_input_template(
    workbook_path: Path,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Load optional explicit Step 4.1 inputs from 'OE Input Template'.

    The workbook may supply:
        - Structured Planning State ID
        - Mission/Tasking State ID
        - Analyst-Selected State ID

    Blank cells remain None.

    Only rows whose OE Parameter matches one of the valid parameters
    in 'OE State Definitions' are treated as executable input rows.
    Explanatory/documentation rows in the worksheet are ignored.

    Final State ID / Final Source / Final Status are currently treated
    as documentation/output placeholders and are not executable inputs.
    """

    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_OE_INPUT,
        header=3,
    )

    required = [
        "OE Parameter",
        "Structured Planning State ID",
        "Mission/Tasking State ID",
        "Analyst-Selected State ID",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"'{SHEET_OE_INPUT}' is missing columns: {missing}"
        )

    # -------------------------------------------------------------
    # Valid OE parameters come from the authoritative OE catalog.
    # This prevents notes or documentation text elsewhere in the
    # worksheet from being interpreted as executable input rows.
    # -------------------------------------------------------------

    valid_parameters = set(oe_catalog.keys())

    result: Dict[str, Dict[str, Optional[str]]] = {}

    for _, row in df.iterrows():

        parameter = clean_cell(
            row["OE Parameter"]
        )

        # Ignore blank rows.
        if parameter is None:
            continue

        # Ignore explanatory/documentation rows.
        if parameter not in valid_parameters:
            continue

        result[parameter] = {
            "structured_planning_state_id":
                clean_cell(
                    row["Structured Planning State ID"]
                ),

            "mission_tasking_state_id":
                clean_cell(
                    row["Mission/Tasking State ID"]
                ),

            "analyst_selected_state_id":
                clean_cell(
                    row["Analyst-Selected State ID"]
                ),

            "planning_context_evidence":
                clean_cell(
                    row.get("Planning-Context Evidence")
                ),
        }

    # -------------------------------------------------------------
    # Confirm that all OE parameters are actually represented in
    # the input template.
    # -------------------------------------------------------------

    missing_parameters = [
        parameter
        for parameter in oe_catalog
        if parameter not in result
    ]

    if missing_parameters:
        raise ValueError(
            "OE Input Template is missing OE parameter rows: "
            f"{missing_parameters}"
        )

    return result


def load_compatibility_matrix(
    workbook_path: Path,
) -> Dict[str, Dict[str, str]]:
    """
    Load Step 4.2 C/K/X matrix.

    Sheet:
        OE Compatibility
    Header:
        Excel row 8 -> pandas header=7
    """
    df = pd.read_excel(
        workbook_path,
        sheet_name=SHEET_OE_COMPATIBILITY,
        header=7,
    )

    required = ["State ID"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"'{SHEET_OE_COMPATIBILITY}' is missing columns: {missing}"
        )

    df = df.dropna(subset=["State ID"])

    compatibility: Dict[str, Dict[str, str]] = {}

    for _, row in df.iterrows():
        row_state = clean_cell(row["State ID"])
        if row_state is None:
            continue

        compatibility[row_state] = {}

        # Current workbook: first three columns are State ID, OE Parameter, OE State.
        for column in df.columns[3:]:
            column_state = clean_cell(column)
            if column_state is None:
                continue

            value = clean_cell(row[column])
            if value is None:
                continue

            compatibility[row_state][column_state] = value

    return compatibility


# =============================================================================
# 5. VALIDATION HELPERS
# =============================================================================

def validate_mission_class_interface(
    mission_definitions: Dict[str, Dict[str, Any]],
) -> None:
    """
    Ensure executable mission rules and workbook mission definitions share the
    same class-code interface.
    """
    rule_codes = set(MISSION_CLASS_RULES)
    function_codes = set(MISSION_TO_FUNCTIONS)
    definition_codes = set(mission_definitions)

    if rule_codes != function_codes:
        raise ValueError(
            "Mission-class rule codes do not match mission-to-function codes.\n"
            f"Rules: {sorted(rule_codes)}\n"
            f"Functions: {sorted(function_codes)}"
        )

    missing_definitions = function_codes - definition_codes
    if missing_definitions:
        raise ValueError(
            "Workbook lacks Mission Class Definitions for: "
            f"{sorted(missing_definitions)}"
        )


def state_lookup_for_parameter(
    parameter: str,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Create a State ID -> state record lookup for one OE parameter."""
    if parameter not in oe_catalog:
        raise KeyError(
            f"Unknown OE parameter: {parameter}"
        )

    return {
        item["state_id"]: item
        for item in oe_catalog[parameter]
    }


def validate_state_id(
    parameter: str,
    state_id: str,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Validate one State ID against its OE parameter."""
    lookup = state_lookup_for_parameter(
        parameter, oe_catalog
    )

    if state_id not in lookup:
        raise ValueError(
            f"State ID '{state_id}' is not valid for '{parameter}'. "
            f"Valid IDs: {list(lookup)}"
        )

    return lookup[state_id]


def validate_oe_input_state_ids(
    oe_input: Dict[str, Dict[str, Optional[str]]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Validate every nonblank State ID already entered in OE Input Template."""
    fields = [
        "structured_planning_state_id",
        "mission_tasking_state_id",
        "analyst_selected_state_id",
    ]

    for parameter, record in oe_input.items():
        for field in fields:
            state_id = record.get(field)
            if state_id:
                validate_state_id(
                    parameter,
                    state_id,
                    oe_catalog,
                )


# =============================================================================
# 6. STEP 1 - MISSION-CLASS ASSESSMENT
# =============================================================================

def assess_mission_classes(
    mission_input: Dict[str, Any],
    mission_definitions: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Apply transparent coded rules to the mission input.

    Each rule contributes its weight at most once, even if multiple synonyms
    from that rule match the same field.
    """
    assessments: Dict[str, Dict[str, Any]] = {}

    for code, rules in MISSION_CLASS_RULES.items():
        evidence = []
        score = 0

        for rule in rules:
            field_value = mission_input.get(rule["field"])
            field_text = normalize_text(field_value)

            matched_terms = [
                term
                for term in rule["terms"]
                if term.lower() in field_text
            ]

            if matched_terms:
                score += rule["weight"]

                evidence.append({
                    "rule_id": rule["rule_id"],
                    "field": rule["field"],
                    "matched_terms": matched_terms,
                    "observed_value": field_value,
                    "weight": rule["weight"],
                    "basis": rule["basis"],
                })

        definition = mission_definitions[code]

        assessments[code] = {
            "mission_name": definition["name"],
            "definition": definition["definition"],
            "definition_status": definition["definition_status"],
            "score": score,
            "evidence": evidence,
            "source_basis": definition["source_basis"],
            "primary_source_url": definition["primary_source_url"],
        }

    return assessments


def classify_mission_candidates(
    assessments: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Assign descriptive candidate categories.

    These are heuristic evidence categories, NOT calibrated confidence levels.
    """
    classified = deepcopy(assessments)
    max_score = max(
        data["score"]
        for data in classified.values()
    )

    for data in classified.values():
        score = data["score"]

        if max_score == 0 or score == 0:
            category = "Weak / no match"
        elif score == max_score:
            category = "Primary candidate"
        elif score >= 0.30 * max_score:
            category = "Secondary candidate"
        else:
            category = "Weak / no match"

        data["candidate_category"] = category

    return classified


def display_mission_class_assessment(
    classified: Dict[str, Dict[str, Any]],
) -> None:
    """Print candidate classes, evidence, and workbook definitions."""
    print("\n" + "=" * 78)
    print("STEP 1 - MISSION-CLASS ASSESSMENT")
    print("=" * 78)

    order = {
        "Primary candidate": 0,
        "Secondary candidate": 1,
        "Weak / no match": 2,
    }

    ordered = sorted(
        classified.items(),
        key=lambda item: (
            order[item[1]["candidate_category"]],
            -item[1]["score"],
            item[0],
        ),
    )

    for code, data in ordered:
        print(
            f"\n{data['candidate_category']}: "
            f"{code} - {data['mission_name']}"
        )
        print(f"Definition: {data['definition']}")

        if data["evidence"]:
            print("Supporting evidence:")
            for item in data["evidence"]:
                print(
                    f"  - {item['rule_id']} | "
                    f"{item['field']} | "
                    f"matched: {', '.join(item['matched_terms'])}"
                )
                print(
                    f"    Rationale: {item['basis']}"
                )
        else:
            print(
                "Supporting evidence: none identified by the current rule set."
            )

    print(
        "\nNOTE: Candidate categories organize transparent rule evidence. "
        "They are not probabilities."
    )


def resolve_mission_class(
    mission_input: Dict[str, Any],
    classified: Dict[str, Dict[str, Any]],
    mission_definitions: Dict[str, Dict[str, Any]],
    interactive: bool = True,
) -> Dict[str, Any]:
    """
    Resolve final mission class.

    Precedence:
        1. Explicit class supplied by mission/tasking.
        2. Analyst-confirmed primary inference.
        3. Analyst-selected alternative.
    """
    explicit = mission_input.get(
        "mission_class_explicit"
    )

    if explicit:
        code = str(explicit).strip().upper()

        if code not in mission_definitions:
            raise ValueError(
                f"Explicit mission class '{code}' is not valid. "
                f"Valid codes: {sorted(mission_definitions)}"
            )

        return make_trace_record(
            value=code,
            source="explicit",
            status="accepted",
            evidence=(
                "Mission class explicitly supplied in the Mission Input Template."
            ),
            rule_id="MC-EXPLICIT",
        )

    primary = [
        code
        for code, data in classified.items()
        if data["candidate_category"] == "Primary candidate"
    ]

    if not primary:
        recommended = None
    else:
        # If several classes tie, list them; do not silently pretend ambiguity
        # does not exist.
        recommended = primary[0]

    if not interactive:
        if recommended is None:
            raise RuntimeError(
                "No mission-class evidence was found and INTERACTIVE=False."
            )

        return make_trace_record(
            value=recommended,
            source="inferred",
            status="unconfirmed",
            evidence=classified[recommended]["evidence"],
            rule_id=f"MC-{recommended}",
        )

    if len(primary) > 1:
        print(
            "\nIMPORTANT: More than one class shares the highest evidence score:"
        )
        for code in primary:
            print(
                f"  - {code}: {mission_definitions[code]['name']}"
            )

    if recommended:
        print(
            f"\nRecommended mission class: "
            f"{recommended} - {mission_definitions[recommended]['name']}"
        )

        answer = input(
            "Accept this recommendation? [Y/n]: "
        ).strip().lower()

        if answer in ("", "y", "yes"):
            return make_trace_record(
                value=recommended,
                source="inferred",
                status="confirmed",
                evidence=classified[recommended]["evidence"],
                rule_id=f"MC-{recommended}",
            )

    print("\nAvailable mission classes:")
    for code in MISSION_TO_FUNCTIONS:
        print(
            f"  {code}: {mission_definitions[code]['name']}"
        )

    while True:
        selected = input(
            "Select final mission-class code: "
        ).strip().upper()

        if selected in mission_definitions:
            return make_trace_record(
                value=selected,
                source="user_selected",
                status="confirmed",
                evidence=(
                    "Analyst selected the mission class after reviewing "
                    "the rule-based candidate assessment."
                ),
                rule_id=None,
            )

        print("Invalid mission-class code.")


# =============================================================================
# 7. STEPS 2 AND 3 - MISSION CLASS OBJECT
# =============================================================================

class Mission:
    """
    Phase 1 Steps 1-3.

    Original conceptual logic retained:
        mission class
          -> operational functions
          -> linked capability dimensions
          -> applicable baseline capability requirements

    Improvements:
        - human-readable mission definitions come from the workbook;
        - linked dimensions and baseline requirements come from the workbook;
        - ordered_unique() prevents the original set-based order loss;
        - mission-class provenance remains attached to the mission object.
    """

    def __init__(
        self,
        mission_class_decision: Dict[str, Any],
        mission_definitions: Dict[str, Dict[str, Any]],
        function_to_dimensions: Dict[str, List[str]],
        baseline_mapping: Dict[str, Dict[str, Any]],
    ):
        mission_code = mission_class_decision["value"]

        if mission_code not in mission_definitions:
            raise ValueError(
                f"Unknown mission class: {mission_code}"
            )

        self.mc = mission_code
        self.name = mission_definitions[mission_code]["name"]
        self.intent = mission_definitions[mission_code]["definition"]
        self.definition_status = (
            mission_definitions[mission_code]["definition_status"]
        )
        self.mission_class_trace = mission_class_decision

        self.functions = MISSION_TO_FUNCTIONS[mission_code]

        missing_functions = [
            function
            for function in self.functions
            if function not in function_to_dimensions
        ]

        if missing_functions:
            raise KeyError(
                "Selected operational functions are missing from "
                f"'{SHEET_BASELINE_MAPPING}': {missing_functions}"
            )

        # Original list-of-lists idea retained.
        nested_dimensions = [
            function_to_dimensions[function]
            for function in self.functions
        ]

        # Modification explicitly agreed with the user:
        # flatten and deduplicate WITHOUT losing order.
        self.capability_dims = ordered_unique(
            item
            for sublist in nested_dimensions
            for item in sublist
        )

        cap_set = set(self.capability_dims)

        self.BL_capability: Dict[str, Dict[str, Any]] = {}

        for baseline_id, baseline in baseline_mapping.items():
            dimensions = baseline["dimensions"]

            if any(
                dimension in cap_set
                for dimension in dimensions
            ):
                missing_dimensions = [
                    dimension
                    for dimension in dimensions
                    if dimension not in cap_set
                ]

                self.BL_capability[baseline_id] = {
                    "name": baseline["name"],
                    "missing_dimensions": missing_dimensions,
                    "primary_function_traceability": baseline.get(
                        "primary_function_traceability"
                    ),
                    "status_note": baseline.get(
                        "status_note"
                    ),
                }

    def summary(self) -> None:
        """Print Steps 1-3."""
        print("\n" + "=" * 78)
        print("PHASE 1 - STEPS 1 THROUGH 3")
        print("=" * 78)

        print(
            f"\nMission class: {self.mc} - {self.name}"
        )
        print(
            f"Source: {self.mission_class_trace['source']} | "
            f"Status: {self.mission_class_trace['status']}"
        )
        print(f"Definition: {self.intent}")

        print("\nOperational functions:")
        for function in self.functions:
            print(f"  - {function}")

        print("\nLinked capability dimensions:")
        for dimension in self.capability_dims:
            print(f"  - {dimension}")

        print("\nBaseline capability requirements:")
        for baseline_id, data in self.BL_capability.items():
            print(
                f"  - {baseline_id}: {data['name']}",
                end="",
            )

            if data["missing_dimensions"]:
                print(" | Partial capability requirement")
                print(
                    "      Missing dimensions: "
                    + "; ".join(data["missing_dimensions"])
                )
            else:
                print(" | Full capability requirement")


# =============================================================================
# 8. STEP 4.1 - MISSION-DERIVED OE INFERENCE
# =============================================================================

def infer_mission_based_oe_states(
    mission_input: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Infer only OE states defensibly supported by mission/tasking information.

    Environmental states such as terrain, fuel structure, wind regime,
    atmospheric stability, and fire-spread regime are NOT guessed here.
    """
    inferred: Dict[str, Dict[str, Any]] = {}

    mission_statement = normalize_text(
        mission_input.get("mission_statement")
    )
    mission_effect = normalize_text(
        mission_input.get("mission_effect")
    )
    protected_values = normalize_text(
        mission_input.get("primary_protected_values")
    )
    required_effect = normalize_text(
        mission_input.get("required_operational_effect")
    )
    operating_period = normalize_text(
        mission_input.get("operating_period")
    )

    # ---- Land use / exposure -----------------------------------------------
    if (
        "wui" in mission_effect
        or "wui" in mission_statement
        or "wui" in protected_values
    ):
        inferred["Land use/exposure"] = make_trace_record(
            value="LU-2",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Mission/tasking explicitly identifies WUI exposure; "
                "LU-2 is proposed as the dominant land-use/exposure state."
            ),
            rule_id="OE-LU-01",
        )

    elif "critical infrastructure" in protected_values:
        inferred["Land use/exposure"] = make_trace_record(
            value="LU-3",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Critical infrastructure is the explicit dominant protected "
                "built-asset context and no WUI condition was identified."
            ),
            rule_id="OE-LU-02",
        )

    # ---- Management objective ----------------------------------------------
    if (
        "confinement" in required_effect
        or "spread limitation" in required_effect
    ):
        inferred["Management objective"] = make_trace_record(
            value="MO-2",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Required operational effect explicitly states confinement "
                "or spread limitation."
            ),
            rule_id="OE-MO-01",
        )

    elif "point protection" in required_effect:
        inferred["Management objective"] = make_trace_record(
            value="MO-3",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Required operational effect explicitly states point protection."
            ),
            rule_id="OE-MO-02",
        )

    elif (
        "monitor" in required_effect
        or "observe" in required_effect
    ):
        inferred["Management objective"] = make_trace_record(
            value="MO-4",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Required operational effect explicitly states monitoring/observation."
            ),
            rule_id="OE-MO-03",
        )

    elif (
        "full suppression" in required_effect
        or "extinguish" in required_effect
    ):
        inferred["Management objective"] = make_trace_record(
            value="MO-1",
            source="inferred",
            status="unconfirmed",
            evidence=(
                "Required operational effect explicitly states full "
                "suppression/extinguishment."
            ),
            rule_id="OE-MO-04",
        )

    # ---- Time of day --------------------------------------------------------
    if operating_period:
        state_id = None

        if operating_period == "day":
            state_id = "TD-1"
        elif operating_period == "night":
            state_id = "TD-2"
        elif (
            "dawn" in operating_period
            or "dusk" in operating_period
            or "transition" in operating_period
        ):
            state_id = "TD-3"

        if state_id:
            inferred["Time of day"] = make_trace_record(
                value=state_id,
                source="explicit",
                status="accepted",
                evidence=(
                    "Operating period explicitly provided in the "
                    "Mission Input Template."
                ),
                rule_id="OE-TD-EXPLICIT",
            )

    return inferred


def extract_mission_constraint_states(
    mission_input: Dict[str, Any],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """
    Translate nonblank mission-input constraint fields into explicit OE records.

    These workbook cells must contain State IDs, not free-form prose.
    """
    records: Dict[str, Dict[str, Any]] = {}

    for mission_key, parameter in MISSION_CONSTRAINT_TO_OE.items():
        state_id = mission_input.get(mission_key)

        if not state_id:
            continue

        state_id = str(state_id).strip()

        validate_state_id(
            parameter,
            state_id,
            oe_catalog,
        )

        records[parameter] = make_trace_record(
            value=state_id,
            source="explicit",
            status="accepted",
            evidence=(
                f"State ID {state_id} explicitly provided in "
                f"Mission Input Template field '{mission_key}'."
            ),
            rule_id="OE-MISSION-EXPLICIT",
        )

    return records


# =============================================================================
# 9. STEP 4.1 - INPUT PRECEDENCE AND ANALYST COMPLETION
# =============================================================================

def display_oe_options(
    parameter: str,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Display valid OE states for analyst completion/reselection."""
    print(f"\nOE parameter: {parameter}")

    for item in oe_catalog[parameter]:
        print(
            f"  {item['state_id']}: {item['state']}"
        )

        if SHOW_OE_SELECTION_GUIDANCE:
            if item["definition"]:
                print(
                    f"      Definition: {item['definition']}"
                )
            if item["selection_rule"]:
                print(
                    f"      Selection rule: {item['selection_rule']}"
                )


def analyst_select_oe_state(
    parameter: str,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
    reason: str,
) -> Dict[str, Any]:
    """Obtain one valid state from the analyst."""
    display_oe_options(
        parameter,
        oe_catalog,
    )

    while True:
        state_id = input(
            "Select State ID: "
        ).strip().upper()

        try:
            validate_state_id(
                parameter,
                state_id,
                oe_catalog,
            )

            return make_trace_record(
                value=state_id,
                source="user_selected",
                status="confirmed",
                evidence=reason,
                rule_id=None,
            )

        except ValueError as exc:
            print(exc)


def confirm_inferred_oe_state(
    parameter: str,
    record: Dict[str, Any],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
    interactive: bool,
) -> Dict[str, Any]:
    """Ask analyst to confirm or replace an inferred OE state."""
    option = validate_state_id(
        parameter,
        record["value"],
        oe_catalog,
    )

    if not interactive:
        result = deepcopy(record)
        result["status"] = "unconfirmed"
        return result

    print(
        f"\nProposed from mission input: "
        f"{parameter} -> {option['state_id']} - {option['state']}"
    )
    print(f"Evidence: {record['evidence']}")

    answer = input(
        "Accept proposed state? [Y/n]: "
    ).strip().lower()

    if answer in ("", "y", "yes"):
        result = deepcopy(record)

        if result["source"] == "inferred":
            result["status"] = "confirmed"

        return result

    replacement = analyst_select_oe_state(
        parameter,
        oe_catalog,
        reason=(
            "Analyst overrode the mission-based OE proposal after "
            "reviewing the available OE states."
        ),
    )

    replacement["history"] = [deepcopy(record)]
    return replacement


def make_explicit_oe_record(
    parameter: str,
    state_id: str,
    evidence: str,
    rule_id: str,
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Validate and package a workbook-supplied explicit OE State ID."""
    validate_state_id(
        parameter,
        state_id,
        oe_catalog,
    )

    return make_trace_record(
        value=state_id,
        source="explicit",
        status="accepted",
        evidence=evidence,
        rule_id=rule_id,
    )


def build_oe_vector(
    mission_input: Dict[str, Any],
    oe_input: Dict[str, Dict[str, Optional[str]]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
    interactive: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Select exactly one state for every OE parameter.

    Source hierarchy:
        mission/tasking explicit State ID
        + structured planning State ID
        + mission-derived inference
        + pre-entered analyst State ID
        + interactive analyst completion

    IMPORTANT:
    Explicit mission/tasking and explicit structured-planning values are not
    silently ranked if they conflict. A conflict raises an error for review.
    """
    mission_constraint_states = extract_mission_constraint_states(
        mission_input,
        oe_catalog,
    )

    mission_inferred = infer_mission_based_oe_states(
        mission_input
    )

    selected: Dict[str, Dict[str, Any]] = {}

    for parameter in oe_catalog.keys():
        workbook_row = oe_input[parameter]

        sheet_mission_state = workbook_row.get(
            "mission_tasking_state_id"
        )
        structured_state = workbook_row.get(
            "structured_planning_state_id"
        )
        preselected_analyst_state = workbook_row.get(
            "analyst_selected_state_id"
        )

        # Mission/tasking explicit state can come from:
        #   a) MI-11..MI-14, or
        #   b) OE Input Template Mission/Tasking State ID.
        field_mission_record = mission_constraint_states.get(
            parameter
        )

        sheet_mission_record = None

        if sheet_mission_state:
            sheet_mission_record = make_explicit_oe_record(
                parameter=parameter,
                state_id=sheet_mission_state,
                evidence=(
                    "Explicit Mission/Tasking State ID supplied in "
                    "OE Input Template."
                ),
                rule_id="OE-MISSION-EXPLICIT",
                oe_catalog=oe_catalog,
            )

        # Check for two conflicting explicit mission/tasking sources.
        if (
            field_mission_record
            and sheet_mission_record
            and field_mission_record["value"]
            != sheet_mission_record["value"]
        ):
            raise ValueError(
                f"Conflicting explicit mission/tasking State IDs for "
                f"'{parameter}': "
                f"{field_mission_record['value']} vs "
                f"{sheet_mission_record['value']}."
            )

        explicit_mission_record = (
            field_mission_record
            or sheet_mission_record
        )

        # Structured planning record.
        structured_record = None

        if structured_state:
            structured_record = make_explicit_oe_record(
                parameter=parameter,
                state_id=structured_state,
                evidence=(
                    workbook_row.get("planning_context_evidence")
                    or "State ID supplied in OE Input Template "
                       "Structured Planning State ID column."
                ),
                rule_id="OE-STRUCTURED-CONTEXT",
                oe_catalog=oe_catalog,
            )

        # Do not silently choose between conflicting explicit sources.
        if (
            explicit_mission_record
            and structured_record
            and explicit_mission_record["value"]
            != structured_record["value"]
        ):
            raise ValueError(
                f"Conflicting explicit inputs for '{parameter}': "
                f"mission/tasking={explicit_mission_record['value']} vs "
                f"structured planning={structured_record['value']}.\n"
                "Resolve the conflict in the workbook before rerunning."
            )

        # 1. Explicit mission/tasking state.
        if explicit_mission_record:
            selected[parameter] = explicit_mission_record
            continue

        # 2. Explicit structured-planning state.
        if structured_record:
            selected[parameter] = structured_record
            continue

        # 3. Mission-based inference.
        if parameter in mission_inferred:
            selected[parameter] = confirm_inferred_oe_state(
                parameter,
                mission_inferred[parameter],
                oe_catalog,
                interactive,
            )
            continue

        # 4. Analyst preselection stored in workbook.
        if preselected_analyst_state:
            validate_state_id(
                parameter,
                preselected_analyst_state,
                oe_catalog,
            )

            selected[parameter] = make_trace_record(
                value=preselected_analyst_state,
                source="user_selected",
                status="confirmed",
                evidence=(
                    "Analyst-Selected State ID was pre-entered in "
                    "OE Input Template."
                ),
                rule_id=None,
            )
            continue

        # 5. Interactive analyst completion.
        if not interactive:
            raise RuntimeError(
                f"No OE state is available for '{parameter}' "
                "and INTERACTIVE=False."
            )

        selected[parameter] = analyst_select_oe_state(
            parameter,
            oe_catalog,
            reason=(
                "Mission/tasking and structured planning context did not "
                "uniquely establish this OE state; analyst completion was required."
            ),
        )

    return selected


# =============================================================================
# 10. STEP 4.2 - OE CROSS-COMPATIBILITY
# =============================================================================

def evaluate_oe_compatibility(
    selected_oe: Dict[str, Dict[str, Any]],
    compatibility: Dict[str, Dict[str, str]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """
    Evaluate every unique pair of selected OE states.

    With 14 parameters:
        C(14, 2) = 91 pairwise checks.
    """
    items = list(selected_oe.items())

    incompatible_pairs = []
    conditional_pairs = []
    compatible_pairs = []

    for i in range(len(items)):
        parameter_1, record_1 = items[i]
        state_1 = record_1["value"]

        state_1_info = validate_state_id(
            parameter_1,
            state_1,
            oe_catalog,
        )

        for j in range(i + 1, len(items)):
            parameter_2, record_2 = items[j]
            state_2 = record_2["value"]

            state_2_info = validate_state_id(
                parameter_2,
                state_2,
                oe_catalog,
            )

            code = compatibility.get(
                state_1, {}
            ).get(state_2)

            # Defensive symmetric lookup.
            if code is None:
                code = compatibility.get(
                    state_2, {}
                ).get(state_1)

            if code is None:
                raise KeyError(
                    f"No compatibility code found for "
                    f"{state_1} <-> {state_2}."
                )

            code = code.strip().upper()

            pair = {
                "parameter_1": parameter_1,
                "state_1": state_1,
                "state_name_1": state_1_info["state"],
                "parameter_2": parameter_2,
                "state_2": state_2,
                "state_name_2": state_2_info["state"],
                "compatibility": code,
            }

            if code == "X":
                incompatible_pairs.append(pair)

            elif code == "K":
                conditional_pairs.append(pair)

            elif code == "C":
                compatible_pairs.append(pair)

            else:
                raise ValueError(
                    f"Unexpected compatibility code '{code}' for "
                    f"{state_1} <-> {state_2}."
                )

    return (
        incompatible_pairs,
        conditional_pairs,
        compatible_pairs,
    )


def print_oe_vector(
    selected_oe: Dict[str, Dict[str, Any]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Print selected Step 4.1 vector with provenance."""
    print("\n" + "=" * 78)
    print("STEP 4.1 - SELECTED OPERATIONAL-ENVIRONMENT VECTOR")
    print("=" * 78)

    for parameter, record in selected_oe.items():
        state = validate_state_id(
            parameter,
            record["value"],
            oe_catalog,
        )

        print(
            f"\n{parameter}: "
            f"{record['value']} - {state['state']}"
        )
        print(
            f"  source={record['source']} | "
            f"status={record['status']}"
        )
        print(
            f"  evidence={record['evidence']}"
        )


def print_compatibility_results(
    incompatible_pairs: List[Dict[str, Any]],
    conditional_pairs: List[Dict[str, Any]],
    compatible_pairs: List[Dict[str, Any]],
) -> None:
    """Print Step 4.2 screening results."""
    total = (
        len(incompatible_pairs)
        + len(conditional_pairs)
        + len(compatible_pairs)
    )

    print("\n" + "=" * 78)
    print("STEP 4.2 - OE CROSS-COMPATIBILITY SCREEN")
    print("=" * 78)

    print(
        f"\nUnique cross-parameter comparisons evaluated: {total}"
    )

    if total != 91:
        print(
            "WARNING: Expected 91 comparisons for a 14-parameter "
            f"OE vector, but evaluated {total}."
        )

    if incompatible_pairs:
        print("\nINCOMPATIBLE PAIRS (X):")

        for pair in incompatible_pairs:
            print(
                f"  {pair['state_1']} ({pair['state_name_1']}) "
                f"<-> "
                f"{pair['state_2']} ({pair['state_name_2']})"
            )

        print(
            "\nRESULT: Current OE vector is NOT admissible."
        )

    else:
        print("\nNo incompatible (X) pairs identified.")
        print(
            "RESULT: OE vector passes the incompatibility screen."
        )

    if conditional_pairs:
        print("\nCONDITIONALLY COMPATIBLE PAIRS (K):")

        for pair in conditional_pairs:
            print(
                f"  {pair['state_1']} ({pair['state_name_1']}) "
                f"<-> "
                f"{pair['state_2']} ({pair['state_name_2']})"
            )

        print(
            "\nK pairs remain in the scenario and are explicitly "
            "carried forward for later analysis."
        )

    else:
        print(
            "\nNo conditionally compatible (K) pairs identified."
        )


def revise_conflicting_state(
    selected_oe: Dict[str, Dict[str, Any]],
    incompatible_pairs: List[Dict[str, Any]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    """
    Resolve one X incompatibility through analyst intervention.

    The program NEVER decides which state is 'wrong' and never deletes a state
    automatically.
    """
    pair = incompatible_pairs[0]

    print(
        "\nThe program will not arbitrarily eliminate either state."
    )
    print("\nFirst unresolved incompatibility:")
    print(
        f"  1. {pair['parameter_1']}: "
        f"{pair['state_1']} - {pair['state_name_1']}"
    )
    print(
        f"  2. {pair['parameter_2']}: "
        f"{pair['state_2']} - {pair['state_name_2']}"
    )
    print(
        "  3. Stop and review the scenario / compatibility rule"
    )

    while True:
        choice = input(
            "Which parameter should be reconsidered? [1/2/3]: "
        ).strip()

        if choice == "3":
            return selected_oe, False

        if choice not in ("1", "2"):
            print("Enter 1, 2, or 3.")
            continue

        parameter = (
            pair["parameter_1"]
            if choice == "1"
            else pair["parameter_2"]
        )

        old_record = deepcopy(
            selected_oe[parameter]
        )

        new_record = analyst_select_oe_state(
            parameter,
            oe_catalog,
            reason=(
                "Analyst reselected this OE state to resolve a Step 4.2 "
                "X incompatibility."
            ),
        )

        new_record["status"] = "overridden"
        new_record["history"] = (
            old_record.get("history", [])
            + [old_record]
        )

        selected_oe[parameter] = new_record

        return selected_oe, True


def resolve_oe_compatibility(
    selected_oe: Dict[str, Dict[str, Any]],
    compatibility: Dict[str, Dict[str, str]],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
    interactive: bool = True,
) -> Dict[str, Any]:
    """
    Repeat Step 4.2 until:
        - no X pairs remain, or
        - analyst stops for scenario review.
    """
    while True:
        (
            incompatible_pairs,
            conditional_pairs,
            compatible_pairs,
        ) = evaluate_oe_compatibility(
            selected_oe,
            compatibility,
            oe_catalog,
        )

        print_compatibility_results(
            incompatible_pairs,
            conditional_pairs,
            compatible_pairs,
        )

        if not incompatible_pairs:
            return {
                "admissible": True,
                "selected_oe": selected_oe,
                "incompatible_pairs": [],
                "conditional_pairs": conditional_pairs,
                "compatible_pairs": compatible_pairs,
            }

        if not interactive:
            return {
                "admissible": False,
                "selected_oe": selected_oe,
                "incompatible_pairs": incompatible_pairs,
                "conditional_pairs": conditional_pairs,
                "compatible_pairs": compatible_pairs,
            }

        selected_oe, continue_screening = revise_conflicting_state(
            selected_oe,
            incompatible_pairs,
            oe_catalog,
        )

        if not continue_screening:
            return {
                "admissible": False,
                "selected_oe": selected_oe,
                "incompatible_pairs": incompatible_pairs,
                "conditional_pairs": conditional_pairs,
                "compatible_pairs": compatible_pairs,
            }


# =============================================================================
# 11. TRACEABILITY SUMMARY
# =============================================================================

def print_mission_input_summary(
    mission_input: Dict[str, Any],
) -> None:
    """Show exactly what the program extracted from Mission Input Template."""
    print("\n" + "=" * 78)
    print("MISSION INPUT EXTRACTED FROM WORKBOOK")
    print("=" * 78)

    for field_id, key in MISSION_FIELD_MAP.items():
        print(
            f"{field_id} | {key}: "
            f"{mission_input.get(key)}"
        )


def print_traceability_summary(
    mission_class_decision: Dict[str, Any],
    mission: Mission,
    step42_result: Dict[str, Any],
    oe_catalog: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Print compact end-to-end traceability through Step 4.2."""
    print("\n" + "=" * 78)
    print("PHASE 1 TRACEABILITY SUMMARY THROUGH STEP 4.2")
    print("=" * 78)

    print("\nMission-class decision:")
    print(
        f"  value={mission_class_decision['value']}"
    )
    print(
        f"  source={mission_class_decision['source']}"
    )
    print(
        f"  status={mission_class_decision['status']}"
    )
    print(
        f"  rule_id={mission_class_decision['rule_id']}"
    )

    print("\nSteps 2-3:")
    print(
        f"  Operational functions: "
        f"{len(mission.functions)}"
    )
    print(
        f"  Linked capability dimensions: "
        f"{len(mission.capability_dims)}"
    )
    print(
        f"  Applicable baseline capability requirements: "
        f"{len(mission.BL_capability)}"
    )

    print("\nStep 4.1 OE state provenance:")

    for parameter, record in step42_result[
        "selected_oe"
    ].items():
        state = validate_state_id(
            parameter,
            record["value"],
            oe_catalog,
        )

        print(
            f"  {parameter}: "
            f"{record['value']} - {state['state']} | "
            f"source={record['source']} | "
            f"status={record['status']}"
        )

    print("\nStep 4.2:")
    print(
        f"  Admissible OE vector: "
        f"{step42_result['admissible']}"
    )
    print(
        f"  X pairs remaining: "
        f"{len(step42_result['incompatible_pairs'])}"
    )
    print(
        f"  K pairs retained: "
        f"{len(step42_result['conditional_pairs'])}"
    )


# =============================================================================
# 12. MAIN PIPELINE
# =============================================================================

def main() -> Dict[str, Any]:
    """Execute Phase 1 through Step 4.2."""
    workbook_path = resolve_workbook_path()

    print("=" * 78)
    print("PHASE 1 - OPERATIONAL SCENARIO DEVELOPMENT")
    print("Workbook-driven reference data + coded decision rules")
    print("Implemented through Step 4.2")
    print("=" * 78)

    print(
        f"\nWorkbook: {workbook_path.resolve()}"
    )

    # -------------------------------------------------------------------------
    # A. Validate workbook and load reference/input data
    # -------------------------------------------------------------------------
    validate_workbook_sheets(
        workbook_path
    )

    mission_definitions = load_mission_class_definitions(
        workbook_path
    )

    validate_mission_class_interface(
        mission_definitions
    )

    mission_input = load_mission_input(
        workbook_path
    )

    function_to_dimensions = load_function_to_dimensions(
        workbook_path
    )

    baseline_mapping = load_baseline_mapping(
        workbook_path
    )

    oe_catalog = load_oe_catalog(
        workbook_path
    )

    oe_input = load_oe_input_template(
        workbook_path,
        oe_catalog,
    )

    validate_oe_input_state_ids(
        oe_input,
        oe_catalog,
    )

    compatibility = load_compatibility_matrix(
        workbook_path
    )

    print_mission_input_summary(
        mission_input
    )

    # -------------------------------------------------------------------------
    # STEP 1 - Mission-class assessment and confirmation
    # -------------------------------------------------------------------------
    assessments = assess_mission_classes(
        mission_input,
        mission_definitions,
    )

    classified = classify_mission_candidates(
        assessments
    )

    display_mission_class_assessment(
        classified
    )

    mission_class_decision = resolve_mission_class(
        mission_input,
        classified,
        mission_definitions,
        interactive=INTERACTIVE,
    )

    # -------------------------------------------------------------------------
    # STEPS 2-3 - Functions, linked dimensions, baseline requirements
    # -------------------------------------------------------------------------
    mission = Mission(
        mission_class_decision,
        mission_definitions,
        function_to_dimensions,
        baseline_mapping,
    )

    mission.summary()

    # -------------------------------------------------------------------------
    # STEP 4.1 - OE vector
    # -------------------------------------------------------------------------
    selected_oe = build_oe_vector(
        mission_input,
        oe_input,
        oe_catalog,
        interactive=INTERACTIVE,
    )

    print_oe_vector(
        selected_oe,
        oe_catalog,
    )

    # -------------------------------------------------------------------------
    # STEP 4.2 - C/K/X screening
    # -------------------------------------------------------------------------
    step42_result = resolve_oe_compatibility(
        selected_oe,
        compatibility,
        oe_catalog,
        interactive=INTERACTIVE,
    )

    # -------------------------------------------------------------------------
    # Final traceability output
    # -------------------------------------------------------------------------
    print_traceability_summary(
        mission_class_decision,
        mission,
        step42_result,
        oe_catalog,
    )

    return {
        "workbook_path": workbook_path,
        "mission_definitions": mission_definitions,
        "mission_input": mission_input,
        "mission_class_assessment": classified,
        "mission_class_decision": mission_class_decision,
        "mission": mission,
        "oe_catalog": oe_catalog,
        "oe_input": oe_input,
        "step42_result": step42_result,
    }


if __name__ == "__main__":
    phase1_results = main()
