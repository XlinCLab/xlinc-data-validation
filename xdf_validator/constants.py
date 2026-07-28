# Top-level keys of a single stream dict, as returned by pyxdf.load_xdf()
STREAM_TIME_SERIES = "time_series"
STREAM_TIME_STAMPS = "time_stamps"
STREAM_INFO = "info"

# Raw clock-offset calibration measurements
STREAM_CLOCK_TIMES = "clock_times"
STREAM_CLOCK_VALUES = "clock_values"

# Keys within a stream's "info" metadata dict
INFO_NAME = "name"
INFO_TYPE = "type"
INFO_HOSTNAME = "hostname"
INFO_NOMINAL_SRATE = "nominal_srate"
INFO_DESC = "desc"

# Nested keys under info.desc.channels.channel[] describing each channel
INFO_CHANNELS = "channels"
INFO_CHANNEL = "channel"
INFO_LABEL = "label"
INFO_UNIT = "unit"

# Mapping of stream unit labels to abbreviations
UNIT_ABBREVIATIONS = {
    "microvolts": "μV",
    "millivolts": "mV",
    "volts": "V",
    "kohms": "kΩ",
    "ohms": "Ω",
    "hertz": "Hz",
    "millimeters": "mm",
    "pixels": "px",
}
