"""GUI-specific constants (window sizing, labels, colors) for the LSL monitor desktop app."""

import logging

WINDOW_TITLE = "LSL Monitor"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 650

# Console text color per log level, keyed by logging levelno.
LEVEL_COLORS = {
    logging.DEBUG: "#888888",
    logging.INFO: "#d0d0d0",
    logging.WARNING: "#b8860b",
    logging.ERROR: "#c0392b",
    logging.CRITICAL: "#c0392b",
}
DEFAULT_LEVEL_COLOR = LEVEL_COLORS[logging.INFO]

CONSOLE_BACKGROUND = "#1e1e1e"
