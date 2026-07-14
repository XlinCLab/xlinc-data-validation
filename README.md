# xlinc-data-validation

Tools for validating data collected in a laboratory setting via LabStreamingLayer (LSL) and
recorded to `.xdf` files.

## Table of Contents
* [Setup](#setup)
* [XDF Validation](#xdf-validation)
  * [Validation App](#running-the-desktop-app)
  * [Running manually](#running-the-script-manually)

## Setup

Requires Python 3.11+.

```bash
git clone <repo-url>
cd xlinc-data-validation
./setup.sh
```

`setup.sh` creates a `.venv`, activates it, and installs everything in `requirements.txt`.
To do it manually instead:

```bash
python3.11 -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Activate the virtual environment (`source .venv/bin/activate`) in any new terminal session
before running either tool below.


## XDF Validation

XDF streams are validated by checking for potential data issues.  For each stream in an `.xdf` file:

- **Gaps** — inter-sample intervals much larger than the stream's nominal period are
  treated as dropped sample(s); the total/largest gap size and how many samples are
  implied missing are reported.
- **Rate mismatch** — whether the stream's effective sampling rate (computed from its
  actual timestamps) deviates from its nominal rate even when there are no discrete gaps,
  which usually points to real clock drift in the recording device.
- **Jitter** — how evenly spaced the samples are, excluding discrete gaps. High jitter with
  no gaps can indicate unstable timestamping/buffering even though the average rate is
  correct.
- **Gap location** — when a stream does have gaps, whether they're concentrated in one part
  of the recording or spread throughout, since that changes whether the recording is
  salvageable.
- **Truncation** — a stream that's much shorter (in duration, not raw sample count, so
  streams sampled at different rates can be compared fairly) than the other streams in the
  same file is flagged as truncated/corrupt.

Irregularly-sampled streams (e.g. marker/event streams with no fixed rate) are exempted
from the gap/rate/jitter checks but are still checked for truncation.

### Running the desktop app

```bash
python xdf_validator_app.py
```

1. **Add XDF Files...** to pick one or more `.xdf` files.
2. Optionally set a **stream type filter** (e.g. `EEG`, to only check that type) and/or
   **exclude stream name containing** (e.g. `Impedance`, to skip streams by name
   regardless of type) — leave both blank to check every stream in each file.
3. Click **Validate**. Results stream in per file as they complete.
4. **Save Report...** writes a plain-text report to a specified output file.

### Running the script manually

```bash
python validate_xdf.py recording1.xdf recording2.xdf
python validate_xdf.py recording.xdf --stream-type EEG --exclude-name-substring Impedance -o report.txt
```

```
usage: validate_xdf.py [-h] [-o OUTPUT] [--stream-type STREAM_TYPE]
                       [--exclude-name-substring EXCLUDE_NAME_SUBSTRING]
                       xdf_files [xdf_files ...]

positional arguments:
  xdf_files             Path(s) to one or more .xdf files to validate

options:
  -o OUTPUT, --output OUTPUT
                        Path to write the validation summary to (in addition to stdout)
  --stream-type STREAM_TYPE
                        Only validate streams of this type (e.g. EEG). Default: all streams
  --exclude-name-substring EXCLUDE_NAME_SUBSTRING
                        Exclude streams whose name contains this substring (e.g. impedance checks)
```

The report prints to stdout and, if `-o/--output` is given, is also written to that file.
The process exits `0` if every file passed validation and `1` otherwise (including load
failures), so it can be used as a pass/fail gate in a script.

