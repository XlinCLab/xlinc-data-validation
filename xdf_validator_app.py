#!/usr/bin/env python3
"""Desktop GUI for validating XDF recordings.

Usage:
    python xdf_validator_app.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
