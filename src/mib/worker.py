from __future__ import annotations

from pathlib import Path

from mib.pipeline import predict_pdf
from mib.schema import validate_prediction


def predict_one(pdf: Path) -> dict[str, object]:
    """Picklable worker entrypoint for process pools."""
    try:
        prediction = predict_pdf(pdf)
    except Exception:
        from mib.cli import baseline_prediction

        prediction = baseline_prediction(pdf)
    errors = validate_prediction(prediction)
    if errors:
        from mib.cli import baseline_prediction

        prediction = baseline_prediction(pdf)
    return prediction
