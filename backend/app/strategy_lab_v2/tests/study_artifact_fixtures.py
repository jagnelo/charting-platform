"""Representative immutable payloads emitted by TC's accepted Study adapters."""

STUDY_ARTIFACT_OUTPUT_CASES = (
    ("scalar", 2.5),
    ("series", [2.5, 3.0]),
    ("boolean", True),
    ("table", {"columns": ["time", "value"], "rows": [["t1", 4.0]]}),
    ("bar", {"labels": ["A", "B"], "values": [1.0, 2.0]}),
    (
        "histogram",
        {
            "bins": [{"start": 1.0, "end": 2.0, "count": 2}],
            "sample_size": 2,
            "min": 1.0,
            "max": 2.0,
            "current": 2.0,
        },
    ),
    (
        "range",
        {
            "timestamps": ["0", "1"],
            "lower": [1.25, 1.5],
            "upper": [3.75, 4.0],
            "center": None,
        },
    ),
    ("scatter", {"x": [1.0, 2.0], "y": [2.0, 4.0]}),
    (
        "heatmap",
        {"rows": ["A", "B"], "columns": ["X", "Y"], "values": [[1.0, 2.0], [3.0, 4.0]]},
    ),
    ("dashboard", {"panels": [{"artifact": "equity", "title": "Equity", "span": 4}]}),
    ("events", [{"event_id": "event-1", "timestamp": "2026-10-23T00:00:00Z", "symbol": "US.AAPL"}]),
)
