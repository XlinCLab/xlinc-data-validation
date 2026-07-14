import numpy as np
from pyxdf import load_xdf

from constants import (INFO_HOSTNAME, INFO_NAME, INFO_NOMINAL_SRATE, INFO_TYPE,
                       STREAM_INFO, STREAM_TIME_STAMPS)

FAIL_PREFIXES = ("SEVERE", "CORRUPT", "NO DATA", "FAILED")


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

    def summarize_gaps(self) -> dict:
        """Summarize sample-timing quality (gaps, effective vs. nominal rate)."""
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
            }

        effective_srate = (n_samples - 1) / duration if duration > 0 else 0.0
        nominal_period = 1.0 / nominal_srate

        intervals = np.diff(timestamps)
        outlier_mask = intervals > (1.5 * nominal_period)
        outlier_gaps = intervals[outlier_mask]
        implied_missing = np.round(outlier_gaps / nominal_period).astype(int) - 1
        implied_missing = implied_missing[implied_missing > 0]

        return {
            "n_samples": n_samples,
            "duration": duration,
            "effective_srate": effective_srate,
            "nominal_srate": nominal_srate,
            "n_gaps": len(implied_missing),
            "total_missing": int(implied_missing.sum()) if len(implied_missing) else 0,
            "max_gap_missing": int(implied_missing.max()) if len(implied_missing) else 0,
        }

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
            return "ok"
        missing_fraction = summary["total_missing"] / summary["n_samples"]
        if missing_fraction < 0.005:
            return "ok (negligible gaps)"
        if summary["n_gaps"] <= 3 and missing_fraction < 0.15:
            return "salvageable (few concentrated gaps)"
        return "SEVERE (many/large gaps)"

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
                "verdict": verdict,
            }

        summary = self.summarize_gaps()
        verdict = self.classify_gaps(expected_duration=expected_duration)
        return {
            "name": self.name,
            "type": self.type,
            "hostname": self.hostname,
            "verdict": verdict,
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

    def streams_by_type(self, stream_type: str, exclude_name_substring: str = None) -> list[XDFStream]:
        """Return streams matching a given type, optionally excluding streams whose name
        contains a given substring (e.g. to exclude impedance-check streams which otherwise
        share the same type as the real data stream)."""
        matches = []
        for stream in self.streams:
            if stream.type.lower() != str(stream_type).lower():
                continue
            if exclude_name_substring is not None and exclude_name_substring.lower() in stream.name.lower():
                continue
            matches.append(stream)
        return matches

    def validate(self, stream_type: str = None, exclude_name_substring: str = None) -> dict:
        """Run sample-timing validation checks across this file's streams (optionally
        filtered by type). Returns a result dict describing each stream's validation
        outcome and an overall pass/fail status."""
        result = {
            "file": self.path,
            "error": None,
            "streams": [],
            "passed": False,
        }

        if stream_type is not None:
            streams = self.streams_by_type(
                stream_type=stream_type,
                exclude_name_substring=exclude_name_substring
            )
        else:
            streams = self.streams

        if not streams:
            result["error"] = "No matching streams found in file"
            return result

        expected_duration = max((s.duration for s in streams), default=0.0)
        result["streams"] = [s.validate(expected_duration) for s in streams]
        result["passed"] = not any(row["verdict"].startswith(FAIL_PREFIXES) for row in result["streams"])
        return result

    def __repr__(self):
        return f"XDFFile(path={self.path!r}, n_streams={len(self.streams)})"
