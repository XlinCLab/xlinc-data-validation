"""GUI-specific constants (window sizing, labels, colors) for the LSL monitor desktop app."""

import logging

from shared.colors import COLOR_FAIL, COLOR_WARN

WINDOW_TITLE = "LSL Monitor"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 650

# Console text color per log level, keyed by logging levelno.
LEVEL_COLORS = {
    logging.DEBUG: "#888888",
    logging.INFO: "#d0d0d0",
    logging.WARNING: COLOR_WARN,
    logging.ERROR: COLOR_FAIL,
    logging.CRITICAL: COLOR_FAIL,
}
DEFAULT_LEVEL_COLOR = LEVEL_COLORS[logging.INFO]

CONSOLE_BACKGROUND = "#1e1e1e"
