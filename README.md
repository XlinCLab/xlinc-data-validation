# xlinc-data-validation

Tools for working with laboratory data collected via LabStreamingLayer (LSL):
* Live monitoring of LSL streams while recording to flag potential streaming issues.
* Validation of recorded `.xdf` files to check for potential data collection issues post-recording.

## Table of Contents
* [Setup](#setup)
* [XDF Validator](#xdf-validator)
  * [Desktop app](#running-the-xdf-validator-desktop-app)
  * [Running manually](#running-the-xdf-validator-script-manually)
  * [Plotting streams](#plotting-xdf-streams)
* [LSL Monitor](#lsl-monitor)
  * [Desktop app](#running-the-lsl-monitor-desktop-app)
  * [Running manually](#running-the-lsl-monitor-script-manually)
  * [Mock testing](#mock-testing)

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
before running any of the tools below.


## XDF Validator

XDF streams are validated by checking for potential data issues. For each stream in an `.xdf` file:

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

### Running the XDF validator desktop app

```bash
python xdf_validator_app.py
```

1. **Add XDF Files...** to pick one or more `.xdf` files.
2. Optionally set a **stream type filter** (e.g. `EEG`, to only check that type) and/or
   **exclude stream name containing** (e.g. `Impedance`, to skip streams by name
   regardless of type) — leave both blank to check every stream in each file.
3. Click **Validate**. Results stream in per file as they complete.
4. **Save Report...** writes a plain-text report to a specified output file.
5. **Plot Streams...** opens a separate window (seeded with the files already added
   above, or **Browse...** for another one) to visually inspect a file's streams.
   See [Plotting XDF streams](#plotting-xdf-streams) below for further details.

### Running the XDF validator script manually

```bash
python3 -m xdf_validator.validate_xdf recording1.xdf recording2.xdf
python3 -m xdf_validator.validate_xdf recording.xdf --stream-type EEG --exclude-name-substring Impedance -o report.txt
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

### Plotting XDF streams

All streams in a file are plotted on one synchronized time axis (streams within a file
are already on a common clock, so gaps/misalignments between them stay visible) but each
keeps its own independent, labeled Y-axis. Multi-channel streams (e.g. a 128-channel EEG
montage) are drawn as stacked, vertically-offset traces so a dropout affecting only some
channels stays visible; irregularly-sampled streams (e.g. markers) are drawn as event
ticks rather than a continuous waveform. Any gaps detected by the validation checks above
are shaded directly on the plot.

```bash
python3 -m xdf_validator.plot_xdf_streams recording.xdf
python3 -m xdf_validator.plot_xdf_streams recording.xdf --streams "CGX Mobile-128 M128-DEMO" audio
python3 -m xdf_validator.plot_xdf_streams recording.xdf --stream-type EEG --exclude-name-substring Impedance
```

```
usage: plot_xdf_streams.py [-h] [--streams STREAMS [STREAMS ...]]
                           [--stream-type STREAM_TYPE]
                           [--exclude-name-substring EXCLUDE_NAME_SUBSTRING]
                           xdf_file

positional arguments:
  xdf_file              Path to a single .xdf file to plot

options:
  --streams STREAMS [STREAMS ...]
                        Only plot streams with these exact names. Default: all matching streams
  --stream-type STREAM_TYPE
                        Only plot streams of this type (e.g. EEG). Default: all types
  --exclude-name-substring EXCLUDE_NAME_SUBSTRING
                        Exclude streams whose name contains this substring (e.g. impedance checks)
```

The desktop app's **Plot Streams...** button does the same thing interactively: pick a
file, check which streams to plot from a list populated by a quick metadata-only scan
(no sample data is loaded until you actually plot), then click **Plot**.


## LSL Monitor

Unlike the XDF validator, which checks a recording after the fact, the LSL monitor runs
*during* a recording: it discovers whatever LSL streams are on the network, and once per
interval logs each stream's sample count, pull lag, and clock offset. It is meant to run
alongside your recording software so problems can be caught while
the session is still in progress rather than discovered afterward.

- **Lag warnings** — for regularly-sampled streams, a tick whose lag (time since the last
  received sample) exceeds a configurable number of nominal sample periods is logged as a
  warning, since it suggests a stall or dropout. Irregularly-sampled streams (e.g. markers)
  are exempt, since gaps between events are expected.
- **Startup grace period** — a stream's first clock-sync call, and any high lag shortly
  after it's attached, are expected artifacts of LSL's handshake and of catching up on
  buffered backlog. These are logged separately and don't count as real issues, so only
  genuine mid-session problems get flagged as warnings.
- **Stream loss** — if a stream disconnects outright, this is logged as an error and the
  stream stops being monitored for the rest of the session, without crashing monitoring of
  the other streams.
- **Session summary** — on exit (including `Ctrl+C`), a per-stream summary is logged: total
  samples, effective vs. nominal rate, and any issues encountered.

All of this is logged to a timestamped file under the `logs/` directory by default.

### Running the LSL monitor desktop app

```bash
python lsl_monitor_app.py
```

Configure the log file (leave blank for the default timestamped path) and any of the
options below, then **Start**/**Stop** monitoring. Log output is shown live in the console pane, color-coded by severity.

### Running the LSL monitor script manually

```bash
python3 -m lsl_monitor.lsl_monitor
python3 -m lsl_monitor.lsl_monitor --logfile session1_watchdog.log --interval 0.5
```

```
usage: lsl_monitor.py [-h] [-o LOGFILE] [--interval INTERVAL]
                      [--wait-time WAIT_TIME] [--max-buflen MAX_BUFLEN]
                      [--recover]
                      [--time-correction-timeout TIME_CORRECTION_TIMEOUT]
                      [--lag-threshold-periods LAG_THRESHOLD_PERIODS]
                      [--startup-grace-period STARTUP_GRACE_PERIOD]

options:
  -o LOGFILE, --logfile LOGFILE
                        Path to write the monitoring log to. Default:
                        logs/lsl_watchdog_<timestamp>.log
  --interval INTERVAL   Seconds between log ticks. Default: 1.0
  --wait-time WAIT_TIME
                        Seconds to wait when resolving streams at startup. Default: 2.0
  --max-buflen MAX_BUFLEN
                        Max buffer length (seconds) for each stream inlet. Default: 360
  --recover             Attempt to recover an inlet if its stream is lost. Default: off
  --time-correction-timeout TIME_CORRECTION_TIMEOUT
                        Timeout (seconds) for each stream's time_correction() call. Default: 0.5
  --lag-threshold-periods LAG_THRESHOLD_PERIODS
                        Flag a regularly-sampled stream's tick as a warning when its lag
                        exceeds this many nominal sample periods (irregularly-sampled
                        streams, e.g. markers, are exempt). Default: 10
  --startup-grace-period STARTUP_GRACE_PERIOD
                        Seconds after each stream is attached during which time-correction
                        failures and high lag are treated as expected startup noise rather
                        than warnings. Default: 5.0
```

Runs until interrupted (`Ctrl+C`), logging a session summary on exit.

### Mock testing

`lsl_monitor/mock_lsl_stream.py` emits fake LSL streams over loopback, so the monitor can
be tested without any real streaming devices attached:

```bash
# plain, well-behaved stream
python3 -m lsl_monitor.mock_lsl_stream

# inject dropouts and jitter to see the monitor react to bad data
python3 -m lsl_monitor.mock_lsl_stream --srate 500 --n-channels 16 --dropout-prob 0.01 --jitter 0.01
```

By default it streams a regularly-sampled `MockEEG` stream alongside an irregularly-sampled
`MockMarkers` stream (pass `--no-markers` to omit the latter). `--dropout-prob`/`--gap-size`
simulate dropped-sample gaps; `--jitter` adds random timing noise to each sample. Run this
in one terminal and the monitor (script or desktop app) in another to see it work end to end.
