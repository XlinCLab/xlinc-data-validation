import numpy as np
from pyxdf import load_xdf

from xdf_validator.constants import (INFO_CHANNEL, INFO_CHANNELS, INFO_DESC,
                                     INFO_HOSTNAME, INFO_LABEL, INFO_NAME,
                                     INFO_NOMINAL_SRATE, INFO_TYPE, INFO_UNIT,
                                     STREAM_CLOCK_TIMES, STREAM_CLOCK_VALUES,
                                     STREAM_INFO, STREAM_TIME_SERIES,
                                     STREAM_TIME_STAMPS)

FAIL_PREFIXES = ("SEVERE", "CORRUPT", "NO DATA", "FAILED")

# An inter-sample interval must exceed this multiple of the nominal period to count as a
# discrete gap (dropped sample(s)) rather than normal jitter.
GAP_OUTLIER_FACTOR = 1.5
# Sample-to-sample interval std (excluding discrete gaps), as a percentage of the nominal
# period, above which timing is flagged as jittery even though no gaps were detected.
JITTER_THRESHOLD_PCT = 15.0


class XDFStream:
    """Wraps a single stream dict as returned by pyxdf.load_xdf(), exposing its metadata
    and sample-timing quality checks as attributes/methods."""

    def __init__(self, stream: dict):
        self._stream = stream

    def get_metadata(self, field: str, result_type=None):
        """Extract a field from the stream's info metadata."""
        result = self._stream.get(STREAM_INFO, {}).get(field, [""])
        if isinstance(result, list):
            result = result[0] if result else ""
        if result_type is not None:
            return result_type(result)
        return result

    @property
    def name(self) -> str:
        return self.get_metadata(INFO_NAME, str)

    @property
    def type(self) -> str:
        return self.get_metadata(INFO_TYPE, str)

    @property
    def hostname(self) -> str:
        return self.get_metadata(INFO_HOSTNAME, str)

    @property
    def nominal_srate(self) -> float:
        return self.get_metadata(INFO_NOMINAL_SRATE, float)

    @property
    def is_regular(self) -> bool:
        """Whether this stream has a fixed nominal sampling rate, as opposed to an
        irregular/event stream (e.g. markers) sampled asynchronously."""
        return self.nominal_srate > 0

    @property
    def time_stamps(self) -> np.ndarray:
        return np.asarray(self._stream.get(STREAM_TIME_STAMPS, []), dtype=np.float64)

    @property
    def n_samples(self) -> int:
        return len(self.time_stamps)

    @property
    def duration(self) -> float:
        """Time span in seconds from the first to the last sample."""
        timestamps = self.time_stamps
        if len(timestamps) < 2:
            return 0.0
        return float(timestamps[-1] - timestamps[0])

    @property
    def clock_times(self) -> np.ndarray:
        """Local times (on this stream's own local clock) at which a clock-offset calibration
        measurement was taken during recording (periodic LSL clock-sync pings)."""
        return np.asarray(self._stream.get(STREAM_CLOCK_TIMES, []), dtype=np.float64)

    @property
    def clock_values(self) -> np.ndarray:
        """Measured clock offset at each of clock_times: the correction pyxdf applies
        (when loaded with synchronize_clocks=True) to map this stream's local clock onto
        the file's shared clock."""
        return np.asarray(self._stream.get(STREAM_CLOCK_VALUES, []), dtype=np.float64)

    def summarize_clock_offsets(self) -> dict:
        """Summarize this stream's clock-offset calibration measurements."""
        values = self.clock_values
        n = len(values)
        if n == 0:
            return {
                "n_measurements": 0,
                "mean_offset": 0.0,
                "drift": 0.0,
            }
        return {
            "n_measurements": n,
            "mean_offset": float(np.mean(values)),
            "drift": float(values[-1] - values[0]) if n > 1 else 0.0,
        }

    def _raw_channel_field(self, field: str) -> list[str]:
        """
        Per-channel string field extraction from info.desc.channels.channel[]
        (e.g. "label" or "unit"), with no fallback -- used internally both 
        to disambiguate time_series orientation and to look up channel labels/units.
        Returns [] if the metadata is absent or malformed (e.g. irregular
        streams typically don't declare per-channel metadata at all).
        """
        desc = self._stream.get(STREAM_INFO, {}).get(INFO_DESC, [])
        if isinstance(desc, list) and len(desc) > 0:
            desc = desc[0]
        channels = desc.get(INFO_CHANNELS, {}) if isinstance(desc, dict) else {}
        if isinstance(channels, list) and len(channels) > 0:
            channels = channels[0]
        channels = channels.get(INFO_CHANNEL, []) if isinstance(channels, dict) else []

        values = []
        for channel in channels:
            value = channel.get(field) if isinstance(channel, dict) else None
            if isinstance(value, list):
                value = value[0] if value else ""
            values.append(str(value) if value else "")
        return values

    def _raw_channel_labels(self) -> list[str]:
        return self._raw_channel_field(INFO_LABEL)

    @property
    def time_series(self) -> np.ndarray:
        """
        Sample data as a (n_samples, n_channels) array.
        pyxdf normally already returns this shape;
        the channel-label count (when available) is used to catch the rare
        case where it comes back transposed.
        """
        samples = np.asarray(self._stream.get(STREAM_TIME_SERIES, []))
        if samples.ndim == 1:
            samples = samples[:, None]
        labels = self._raw_channel_labels()
        if len(labels) and len(labels) == samples.shape[0] and len(labels) != samples.shape[1]:
            samples = samples.T
        return samples

    @property
    def n_channels(self) -> int:
        time_series = self.time_series
        return time_series.shape[1] if time_series.ndim == 2 else 1

    @property
    def channel_labels(self) -> list[str]:
        """Per-channel labels, falling back to "Ch 0", "Ch 1", ... if the stream's
        metadata doesn't declare a usable label for every channel."""
        labels = self._raw_channel_labels()
        n_channels = self.n_channels
        if len(labels) == n_channels and all(labels):
            return labels
        return [f"Ch {i}" for i in range(n_channels)]

    @property
    def channel_units(self) -> list[str]:
        """
        Per-channel unit strings (e.g. "microvolts", "kohms").
        Returns empty strings for channels without a declared unit.
        """
        units = self._raw_channel_field(INFO_UNIT)
        n_channels = self.n_channels
        if len(units) == n_channels:
            return units
        return [""] * n_channels

    def summarize_gaps(self) -> dict:
        """Summarize sample-timing quality: gap count/size, effective vs. nominal rate, and
        jitter (sample-to-sample interval variability among non-gap intervals)."""
        timestamps = self.time_stamps
        nominal_srate = self.nominal_srate
        n_samples = len(timestamps)
        duration = self.duration

        if n_samples < 2 or nominal_srate <= 0:
            return {
                "n_samples": n_samples,
                "duration": duration,
                "effective_srate": 0.0,
                "nominal_srate": nominal_srate,
                "n_gaps": 0,
                "total_missing": 0,
                "max_gap_missing": 0,
                "jitter_std": 0.0,
                "jitter_pct": 0.0,
            }

        effective_srate = (n_samples - 1) / duration if duration > 0 else 0.0
        nominal_period = 1.0 / nominal_srate

        intervals = np.abs(np.diff(timestamps))
        outlier_mask = intervals > (GAP_OUTLIER_FACTOR * nominal_period)
        outlier_gaps = intervals[outlier_mask]
        implied_missing = np.round(outlier_gaps / nominal_period).astype(int) - 1
        implied_missing = implied_missing[implied_missing > 0]

        regular_intervals = intervals[~outlier_mask]
        jitter_std = float(regular_intervals.std()) if len(regular_intervals) > 0 else 0.0
        jitter_pct = jitter_std / nominal_period * 100

        return {
            "n_samples": n_samples,
            "duration": duration,
            "effective_srate": effective_srate,
            "nominal_srate": nominal_srate,
            "n_gaps": len(implied_missing),
            "total_missing": int(implied_missing.sum()) if len(implied_missing) else 0,
            "max_gap_missing": int(implied_missing.max()) if len(implied_missing) else 0,
            "jitter_std": jitter_std,
            "jitter_pct": jitter_pct,
        }

    def locate_gaps(self) -> list[dict]:
        """Return the time range and size of each detected gap (dropped-sample interval),
        in seconds relative to this stream's own start time. Empty for irregular streams
        or streams without any detected gaps."""
        timestamps = self.time_stamps
        nominal_srate = self.nominal_srate
        if len(timestamps) < 2 or nominal_srate <= 0:
            return []

        nominal_period = 1.0 / nominal_srate
        t0 = timestamps[0]
        intervals = np.abs(np.diff(timestamps))
        outlier_mask = intervals > (GAP_OUTLIER_FACTOR * nominal_period)

        gaps = []
        for idx in np.flatnonzero(outlier_mask):
            n_missing = int(round(intervals[idx] / nominal_period)) - 1
            if n_missing <= 0:
                continue
            gaps.append({
                "start": float(timestamps[idx] - t0),
                "end": float(timestamps[idx + 1] - t0),
                "n_missing": n_missing,
            })
        return gaps

    def gap_distribution(self, gap_concentration_threshold: float = 0.7) -> str:
        """Describe where detected gaps fall within the recording: whether the missing
        samples are concentrated within one portion of the stream or spread throughout.
        Distinguishes a stream that's fine except for one bad stretch from one with
        pervasive dropouts, which have the same gap count/fraction but very different
        implications for salvageability.
        
        gap_concentration_threshold (float): Fraction of a stream's missing samples 
            that must fall within one third of the recording for its gaps to be 
            described as "concentrated" rather than "spread throughout".
        """
        gaps = self.locate_gaps()
        duration = self.duration
        if not gaps or duration <= 0:
            return "n/a"

        thirds = [0, 0, 0]
        labels = ("first third", "middle third", "last third")
        for gap in gaps:
            midpoint = (gap["start"] + gap["end"]) / 2
            idx = min(int((midpoint / duration) * 3), 2)
            thirds[idx] += gap["n_missing"]

        total_missing = sum(thirds)
        if total_missing == 0:
            return "n/a"
        dominant_idx = max(range(3), key=lambda i: thirds[i])
        if thirds[dominant_idx] / total_missing >= gap_concentration_threshold:
            return f"concentrated in {labels[dominant_idx]} of recording"
        return "spread throughout recording"

    def classify_gaps(self, expected_duration: float = None) -> str:
        """Classify this stream's gap summary into a human-readable verdict, optionally
        comparing its time span against an expected value (e.g. the max duration across
        streams in the file, to flag streams that cut off early). Duration is used rather
        than raw sample count so streams with different sampling rates can be compared directly."""
        summary = self.summarize_gaps()
        if summary["n_samples"] < 2:
            return "NO DATA"
        if expected_duration is not None and expected_duration > 0 and summary["duration"] < 0.5 * expected_duration:
            return "CORRUPT / TOO SHORT"
        # Sustained rate mismatch with no discrete gaps: every interval is a bit off nominal,
        # rather than a few isolated dropouts -- treat separately from the "ok" case since it
        # usually indicates a real clock deviation rather than dropped samples.
        if summary["n_gaps"] == 0:
            if summary["nominal_srate"] > 0:
                rate_ratio = summary["effective_srate"] / summary["nominal_srate"]
                if abs(1 - rate_ratio) > 0.02:
                    return "SUSTAINED RATE MISMATCH (no discrete gaps, likely real clock deviation)"
            if summary["jitter_pct"] > JITTER_THRESHOLD_PCT:
                return f"HIGH JITTER (std={summary['jitter_pct']:.1f}% of nominal period, no discrete gaps)"
            return "ok"
        missing_fraction = summary["total_missing"] / summary["n_samples"]
        if missing_fraction < 0.005:
            return "ok (negligible gaps)"
        location = self.gap_distribution()
        if summary["n_gaps"] <= 3 and missing_fraction < 0.15:
            return f"salvageable (few concentrated gaps, {location})"
        return f"SEVERE (many/large gaps, {location})"

    def validate(self, expected_duration: float = None) -> dict:
        """Run the sample-timing checks on this stream and return its result row."""
        if not self.is_regular:
            duration = self.duration
            if expected_duration is not None and expected_duration > 0 and duration < 0.5 * expected_duration:
                verdict = "CORRUPT / TOO SHORT"
            else:
                verdict = "irregular stream (skipped gap check)"
            return {
                "name": self.name,
                "type": self.type,
                "hostname": self.hostname,
                "n_samples": self.n_samples,
                "duration": duration,
                "effective_srate": 0.0,
                "nominal_srate": 0.0,
                "n_gaps": 0,
                "total_missing": 0,
                "jitter_std": 0.0,
                "jitter_pct": 0.0,
                "gaps": [],
                "verdict": verdict,
            }

        summary = self.summarize_gaps()
        verdict = self.classify_gaps(expected_duration=expected_duration)
        return {
            "name": self.name,
            "type": self.type,
            "hostname": self.hostname,
            "verdict": verdict,
            "gaps": self.locate_gaps(),
            **summary
        }

    def __repr__(self):
        return f"XDFStream(name={self.name!r}, type={self.type!r}, hostname={self.hostname!r})"


class XDFFile:
    """Wraps the streams loaded from a single .xdf file via pyxdf.load_xdf()."""

    def __init__(self, path: str, **load_kwargs):
        self.path = path
        raw_streams, self.header = load_xdf(path, **load_kwargs)
        self.streams = [XDFStream(s) for s in raw_streams]

    def streams_by_type(self, stream_type: str = None, exclude_name_substring: str = None) -> list[XDFStream]:
        """Return streams matching a given type (all types if None), optionally excluding
        streams whose name contains a given substring (e.g. to exclude impedance-check
        streams which otherwise share the same type as the real data stream)."""
        matches = []
        for stream in self.streams:
            if stream_type is not None and stream.type.lower() != str(stream_type).lower():
                continue
            if exclude_name_substring is not None and exclude_name_substring.lower() in stream.name.lower():
                continue
            matches.append(stream)
        return matches

    def validate(self, stream_type: str = None, exclude_name_substring: str = None) -> dict:
        """Run sample-timing validation checks across this file's streams (optionally
        filtered by type and/or excluded by name substring). Returns a result dict
        describing each stream's validation outcome and an overall pass/fail status."""
        result = {
            "file": self.path,
            "error": None,
            "streams": [],
            "passed": False,
        }

        streams = self.streams_by_type(stream_type=stream_type, exclude_name_substring=exclude_name_substring)

        if not streams:
            result["error"] = "No matching streams found in file"
            return result

        expected_duration = max((s.duration for s in streams), default=0.0)
        result["streams"] = [s.validate(expected_duration) for s in streams]
        result["passed"] = not any(row["verdict"].startswith(FAIL_PREFIXES) for row in result["streams"])
        return result

    def __repr__(self):
        return f"XDFFile(path={self.path!r}, n_streams={len(self.streams)})"
