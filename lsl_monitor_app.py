#!/usr/bin/env python3
"""Desktop GUI for monitoring live LSL streams while recording.

Usage:
    python lsl_monitor_app.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from lsl_monitor.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
