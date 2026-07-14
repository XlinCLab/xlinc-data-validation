"""GUI-specific constants (window sizing, labels, colors), kept separate from the XDF
field-label constants in the project-level constants.py."""

WINDOW_TITLE = "XDF Validator"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 650

XDF_FILE_FILTER = "XDF files (*.xdf);;All files (*)"

# QTreeWidget column order/labels for the per-stream validation results. The verdict is
# always the last column; code that styles/locates it uses len(RESULT_COLUMNS) - 1 rather
# than a hardcoded index, so reordering/adding columns here doesn't require other changes.
RESULT_COLUMNS = [
    "Stream / File",
    "Type",
    "Hostname",
    "Samples",
    "Duration (s)",
    "Eff. Rate (Hz)",
    "Gaps",
    "Missing",
    "Jitter (%)",
    "Verdict",
]

VERDICT_COLOR_FAIL = "#c0392b"
VERDICT_COLOR_WARN = "#b8860b"
VERDICT_COLOR_OK = "#1e7e34"

# Verdict substrings shown in the "warn" color even though the overall file still passes
# (see xdf_utils.FAIL_PREFIXES for the actual pass/fail cutoff).
WARN_SUBSTRINGS = ("SUSTAINED RATE MISMATCH", "HIGH JITTER", "salvageable")

DEFAULT_REPORT_FILENAME = "xdf_validation_report.txt"
