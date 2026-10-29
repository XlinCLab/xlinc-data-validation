#!/usr/bin/env python3
"""Validate one or more XDF recordings.

For each file, loads all (or a filtered subset of) streams and checks each regularly-sampled
stream's timing for gaps, dropped samples, and effective-vs-nominal sampling rate deviations.

Usage:
    python3 -m xdf_validator.validate_xdf recording1.xdf recording2.xdf
    python3 -m xdf_validator.validate_xdf recording.xdf --stream-type EEG --output report.txt
"""

import argparse
import logging
import os
import sys

from xdf_tools.timing import format_report, validate_xdf_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one or more XDF files by checking each stream's sample timing "
                     "for gaps, dropped samples, and rate deviations from nominal."
    )
    parser.add_argument("xdf_files", nargs="+", help="Path(s) to one or more .xdf files to validate")
    parser.add_argument("-o", "--output", help="Path to write the validation summary to (in addition to stdout)")
    parser.add_argument("--stream-type", default=None,
                         help="Only validate streams of this type (e.g. EEG). Default: all streams")
    parser.add_argument("--exclude-name-substring", default=None,
                         help="Exclude streams whose name contains this substring (e.g. impedance checks)")
    args = parser.parse_args()

    # Filter to existing file paths
    xdf_files = [
        os.path.abspath(xdf_file) for xdf_file in args.xdf_files
        if os.path.exists(os.path.abspath(xdf_file)) and xdf_file.endswith(".xdf")
    ]
    if len(xdf_files) > 0:
        logger.info(f"Validating {len(xdf_files)} XDF files...")
    else:
        logger.error("No matching XDF files found.")
        return

    results = [
        validate_xdf_file(f, stream_type=args.stream_type, exclude_name_substring=args.exclude_name_substring)
        for f in xdf_files
    ]
    report = format_report(results)
    print(report)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report + "\n")
        print(f"\nValidation summary written to {args.output}")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
