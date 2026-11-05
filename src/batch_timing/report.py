"""Portable, script-free reports with complete inputs and data provenance."""

import json
from copy import deepcopy
from html import escape

from .decay import snapshot
from .schedule import Scenario, evaluate, monte_carlo

DISCLAIMER = "Educational model only, not for dose or production decisions."
ASSUMPTIONS = (
    "Activity is referenced to a fixed clock time. Moving the process start does not reset decay. "
    "The target is the selected parent activity, not total daughter activity. "
    "A trial misses if it finishes after calibration or its parent activity is below target. "
    "Late trials are assessed at completion; other trials are assessed at planned calibration. "
    "Step times are independent lognormal samples with the supplied means and standard deviations. "
    "Each retention fraction removes the same fraction of every nuclide at the step end. "
    "Example timings, retentions and activities are invented study inputs, not measured process data. "
    "Only public decay data are used. Half-life, retention and measurement uncertainties are not sampled."
)


def _portable(value):
    if isinstance(value, float):
        return float(f"{value:.10g}")
    if isinstance(value, dict):
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_portable(item) for item in value]
    return value


def build_document(config: dict, *, samples: int, seed: int) -> dict:
    scenario = Scenario.from_dict(config)
    source = snapshot()
    return {
        "model": {
            "educational_only": True,
            "disclaimer": DISCLAIMER,
            "assumptions": ASSUMPTIONS,
            "solver": "Bateman matrix exponential, 50 decimal digits",
        },
        "data_provenance": {
            key: source[key] for key in ("source", "retrieved_utc", "source_sha256")
        },
        "scenario": deepcopy(config),
        "result": _portable(evaluate(scenario)),
        "monte_carlo": _portable(monte_carlo(scenario, samples=samples, seed=seed)),
    }


def _summary(document):
    result, mc = document["result"], document["monte_carlo"]
    lo, hi = mc["wilson_95_interval"]
    return [
        ("Nominal assessment activity", f"{result['assessment_activity_mbq']:.3f} MBq"),
        ("Parent activity target", f"{result['target_activity_mbq']:.3f} MBq"),
        ("Nominal target and deadline met", str(result["feasible"])),
        (
            "Latest nominal start",
            result["latest_start"] or "No start available after the reference",
        ),
        ("Nominal completion", result["completion_time"]),
        ("Planned calibration", result["planned_calibration_time"]),
        ("Actual nominal assessment", result["assessment_time"]),
        ("Nominal deadline slack", f"{result['deadline_slack_minutes']:.2f} min"),
        (
            "Activity expiry with specified retention",
            result["activity_expiry_time"] or "Target already exceeds retained starting activity",
        ),
        ("Monte Carlo trials / seed", f"{mc['samples']} / {mc['seed']}"),
        (
            "Missed activity target or deadline",
            f"{100 * mc['probability_miss']:.2f}% ({mc['misses']} trials)",
        ),
        ("Missed deadline", f"{100 * mc['probability_deadline_miss']:.2f}%"),
        ("Activity shortfall", f"{100 * mc['probability_activity_shortfall']:.2f}%"),
        (
            "Wilson 95% sampling interval for combined miss probability",
            f"{100 * lo:.2f}% to {100 * hi:.2f}%",
        ),
        ("95th percentile total process duration", f"{mc['total_duration_p95_minutes']:.2f} min"),
        (
            "Latest start allowing that sampled duration",
            mc["latest_start_for_p95_duration"] or "No start available after the reference",
        ),
        ("5th percentile assessed parent activity", f"{mc['assessment_activity_p05_mbq']:.3f} MBq"),
    ]


def _timeline(document):
    timeline = document["result"]["timeline"]
    names = list(timeline[0]["activities_mbq"])
    header = ["Step", "UTC time", "Retained fraction"] + [f"{name} (MBq)" for name in names]
    rows = [
        [row["step"], row["time"], f"{row['retention']:.6g}"]
        + [f"{row['activities_mbq'][name]:.6g}" for name in names]
        for row in timeline
    ]
    return header, rows


def markdown_report(document: dict) -> str:
    def cell(text):
        return escape(str(text)).replace("|", r"\|").replace("\n", " ")

    def table(header, rows):
        return "\n".join(
            [
                "| " + " | ".join(map(cell, header)) + " |",
                "| " + " | ".join("---" for _ in header) + " |",
            ]
            + ["| " + " | ".join(map(cell, row)) + " |" for row in rows]
        )

    header, rows = _timeline(document)
    source = document["data_provenance"]
    config_text = json.dumps(document["scenario"], indent=2).replace("`", "\\u0060")
    return (
        f"# {cell(document['result']['title'])}\n\n{DISCLAIMER}\n\n"
        "This report is generated from the saved scenario and pinned public decay data.\n\n"
        "## Timing and risk\n\n"
        + table(["Measure", "Result"], _summary(document))
        + "\n\nThe sampled start allowance addresses deadline risk only. Check activity feasibility "
        "separately; it is not a guarantee or a validated production recommendation.\n\n"
        "## Activity at each step\n\n"
        + table(header, rows)
        + "\n\n## Assumptions\n\n"
        + ASSUMPTIONS
        + "\n\n## Inputs\n\n```json\n"
        + config_text
        + "\n```\n\n"
        "## Decay data provenance\n\n"
        + f"[NNDC NuDat chart JSON]({source['source']}), retrieved {source['retrieved_utc']}.\n\n"
        f"Full downloaded source SHA-256: `{source['source_sha256']}`. "
        "The README cites every tracked nuclide. Rare omitted branches leave the tracked network.\n"
    )


def html_report(document: dict) -> str:
    def table(header, rows):
        headings = "".join(f'<th scope="col">{escape(str(item))}</th>' for item in header)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(str(item))}</td>" for item in row) + "</tr>"
            for row in rows
        )
        return f'<div class="scroll"><table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></div>'

    title = escape(document["result"]["title"])
    header, rows = _timeline(document)
    source = document["data_provenance"]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | Batch timing study</title>
<style>
body {{ margin: 0 auto; max-width: 1080px; padding: 32px 20px; color: #182a31;
font: 17px/1.55 system-ui, sans-serif; background: #fafbf9; }}
h1 {{ font-size: 2.3rem; line-height: 1.15; }} h2 {{ margin-top: 2.3rem; }}
.notice {{ border-left: 4px solid #985600; padding: 12px 18px; background: #fff4d9; }}
table {{ width: 100%; border-collapse: collapse; font-size: .9rem; background: white; }}
th,td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #d8e0df; }}
th {{ background: #e9efed; }} td {{ font-variant-numeric: tabular-nums; }}
.scroll {{ overflow-x: auto; }} pre {{ white-space: pre-wrap; overflow-wrap: anywhere;
background: #edf1ef; padding: 20px; font-size: .85rem; }} .hash {{ overflow-wrap: anywhere; }}
a {{ color: #075f6b; }} @media print {{ body {{ max-width: none; padding: 0; }} }}
</style></head><body><main>
<p>Reproducible batch timing study</p><h1>{title}</h1>
<p class="notice">{DISCLAIMER}</p>
<p>Activity is the rate of radioactive decays. A half-life is the time for half a nuclide to decay.
Calibration is the planned time at which the batch must meet its parent activity target.</p>
<h2>Timing and risk</h2>{table(["Measure", "Result"], _summary(document))}
<p>The sampled start allowance addresses deadline risk only. Check activity feasibility separately;
it is not a guarantee or a validated production recommendation.</p>
<h2>Activity at each step</h2>{table(header, rows)}
<h2>Assumptions</h2><p>{escape(ASSUMPTIONS)}</p>
<h2>Inputs</h2><pre>{escape(json.dumps(document["scenario"], indent=2))}</pre>
<h2>Decay data provenance</h2><p><a href="{escape(source["source"], quote=True)}">NNDC NuDat chart JSON</a>,
retrieved {escape(source["retrieved_utc"])}.</p><p class="hash">Full downloaded source SHA-256:
{escape(source["source_sha256"])}.</p>
<p>The README cites every tracked nuclide. Rare omitted branches leave the tracked network.
This file is self-contained and needs no connection or installed software to read.</p>
</main></body></html>'''
