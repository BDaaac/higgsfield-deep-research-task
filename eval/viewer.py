"""Generate a self-contained HTML trace viewer from a RunReport."""

from __future__ import annotations

import json
from pathlib import Path

from eval.models import RunReport

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "viewer.html"
_REPORTS_DIR = Path("reports")


def build_viewer(report: RunReport, run_id: str) -> Path:
    """Render the HTML viewer and write it to reports/view_{run_id}.html."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # Load full traces for the viewer.
    enriched_cases = []
    for case_result in report.cases:
        case_dict = case_result.model_dump()
        trace_path = Path(case_result.trace_path)
        if trace_path.exists():
            with trace_path.open(encoding="utf-8") as f:
                case_dict["full_trace"] = json.load(f)
        else:
            case_dict["full_trace"] = None
        enriched_cases.append(case_dict)

    report_dict = report.to_dict()
    report_dict["cases"] = enriched_cases

    payload = json.dumps(report_dict, indent=2, default=str)
    html = template.replace("__RUN_DATA_PLACEHOLDER__", payload)

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _REPORTS_DIR / f"view_{run_id}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
