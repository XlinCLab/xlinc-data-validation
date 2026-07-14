#!/usr/bin/env python3
"""Validate one or more XDF recordings.

For each file, loads all (or a filtered subset of) streams and checks each regularly-sampled
stream's timing for gaps, dropped samples, and effective-vs-nominal sampling rate deviations.

Usage:
    python validate_xdf.py recording1.xdf recording2.xdf
    python validate_xdf.py recording.xdf --stream-type EEG --output report.txt
"""

import argparse
import logging
import os
import sys

from xdf_utils import XDFFile

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def validate_xdf_file(
        xdf_file: str,
        stream_type: str = None,
        exclude_name_substring: str = None,
    ) -> dict:
    """Load and validate a single XDF file. Returns a result dict describing each stream's
    validation outcome and an overall pass/fail status."""
    try:
        xdf = XDFFile(
            path=xdf_file,
            synchronize_clocks=True,
            verbose=False
        )
    except Exception as exc:
        return {
            "file": xdf_file,
            "error": f"Failed to load XDF file: {exc}",
            "streams": [],
            "passed": False,
        }

    return xdf.validate(
        stream_type=stream_type,
        exclude_name_substring=exclude_name_substring,
    )


def format_report(results: list[dict]) -> str:
    """Render validation results for one or more files as a human-readable text report."""
    header = (f"{'stream':<24} {'type':<10} {'hostname':<16} {'n_samples':>10} {'dur(s)':>8} "
              f"{'eff_Hz':>8} {'n_gaps':>7} {'missing':>8} {'jitter%':>8}  verdict")
    rule = "-" * len(header)

    lines = []
    n_passed = 0
    for result in results:
        lines.append(f"\n=== {result['file']} ===")
        if result["error"]:
            lines.append(f"  FAILED: {result['error']}")
            continue

        lines.append(header)
        lines.append(rule)
        for row in result["streams"]:
            lines.append(
                f"{row['name']:<24.24} {row['type']:<10.10} {row['hostname']:<16.16} "
                f"{row['n_samples']:>10} {row['duration']:>8.1f} {row['effective_srate']:>8.1f} "
                f"{row['n_gaps']:>7} {row['total_missing']:>8} {row['jitter_pct']:>8.2f}  {row['verdict']}"
            )
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            n_passed += 1
        lines.append(f"  --> {status}")

    lines.append(f"\n{n_passed}/{len(results)} file(s) passed validation")
    return "\n".join(lines)


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
