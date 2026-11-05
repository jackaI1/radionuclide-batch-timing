"""Fixed-reference scheduling and independent positive step-time variation."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from .decay import DecayNetwork, load_network
from .units import magnitude, quantity


def _keys(data: dict, required: set[str], optional: set[str] = frozenset()):
    if (
        not isinstance(data, dict)
        or not required <= data.keys()
        or data.keys() - required - optional
    ):
        raise ValueError(f"Expected fields {sorted(required)}; optional {sorted(optional)}")


def _clock(text: str) -> datetime:
    if not isinstance(text, str):
        raise ValueError("Clock times must be ISO strings with a timezone")
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Clock times must include a timezone, for example +00:00")
    return result.astimezone(UTC)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


@dataclass(frozen=True)
class Step:
    name: str
    mean_seconds: float
    std_seconds: float
    retention: float


@dataclass(frozen=True)
class Scenario:
    title: str
    parent: str
    network: DecayNetwork
    reference: datetime
    start: datetime
    calibration: datetime
    initial_bq: dict[str, float]
    target_bq: float
    steps: tuple[Step, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "Scenario":
        _keys(
            data,
            {
                "title",
                "parent",
                "reference_time",
                "start_time",
                "calibration_time",
                "initial_activities",
                "target_activity",
                "steps",
            },
        )
        network = load_network(data["parent"])
        reference, start, calibration = (
            _clock(data[key]) for key in ("reference_time", "start_time", "calibration_time")
        )
        if not reference <= start <= calibration:
            raise ValueError("Times must satisfy reference <= start <= calibration")
        initial = data["initial_activities"]
        if not isinstance(initial, dict) or set(initial) - set(network.names):
            raise ValueError("Initial activities must name members of the selected decay network")
        initial_bq = {name: magnitude(quantity(value), "Bq") for name, value in initial.items()}
        if initial_bq.get(data["parent"], 0) <= 0:
            raise ValueError("The selected parent needs a positive starting activity")
        target = magnitude(quantity(data["target_activity"]), "Bq", positive=True)
        if not isinstance(data["steps"], list) or not data["steps"]:
            raise ValueError("At least one step is required")
        steps = []
        for row in data["steps"]:
            _keys(row, {"name", "mean_duration", "std_duration", "retention"})
            mean = magnitude(quantity(row["mean_duration"]), "s")
            std = magnitude(quantity(row["std_duration"]), "s")
            retention = row["retention"]
            if isinstance(retention, bool) or not isinstance(retention, (int, float)):
                raise ValueError("Retention must be a number between zero and one")
            if not math.isfinite(retention) or not 0 <= retention <= 1:
                raise ValueError("Retention must be finite and between zero and one")
            if mean == 0 and std != 0:
                raise ValueError("An instantaneous step cannot have positive time variation")
            steps.append(Step(_text(row["name"], "Step name"), mean, std, retention))
        return cls(
            _text(data["title"], "Title"),
            data["parent"],
            network,
            reference,
            start,
            calibration,
            initial_bq,
            target,
            tuple(steps),
        )

    @property
    def retention(self) -> float:
        return math.prod(step.retention for step in self.steps)


def _latest(scenario: Scenario, duration: float) -> str | None:
    candidate = scenario.calibration - timedelta(seconds=duration)
    return candidate.isoformat() if candidate >= scenario.reference else None


def evaluate(scenario: Scenario) -> dict:
    activities = {name: quantity(f"{value} Bq") for name, value in scenario.initial_bq.items()}
    activities = scenario.network.activities(activities, quantity("0 s"))
    timeline = []

    def record(label, clock, retention=1.0):
        timeline.append(
            {
                "step": label,
                "time": clock.isoformat(),
                "retention": retention,
                "activities_mbq": {
                    name: float(value.to("MBq").magnitude) for name, value in activities.items()
                },
            }
        )

    record("Activity reference", scenario.reference)
    hold = (scenario.start - scenario.reference).total_seconds()
    activities = scenario.network.activities(activities, quantity(f"{hold} s"))
    record("Process start", scenario.start)
    clock = scenario.start
    for step in scenario.steps:
        activities = scenario.network.activities(activities, quantity(f"{step.mean_seconds} s"))
        activities = {name: value * step.retention for name, value in activities.items()}
        clock += timedelta(seconds=step.mean_seconds)
        record(step.name, clock, step.retention)
    completion = clock
    assessment = max(scenario.calibration, completion)
    activities = scenario.network.activities(
        activities, quantity(f"{(assessment - clock).total_seconds()} s")
    )
    record("Activity assessment", assessment)
    target_met = magnitude(activities[scenario.parent], "Bq") >= scenario.target_bq * (1 - 1e-12)
    duration = sum(step.mean_seconds for step in scenario.steps)
    latest_start = _latest(scenario, duration)
    initial_after_yield = scenario.initial_bq[scenario.parent] * scenario.retention
    expiry = None
    if initial_after_yield >= scenario.target_bq:
        max_age = (
            math.log(initial_after_yield / scenario.target_bq)
            / scenario.network.rates[scenario.parent]
        )
        expiry = (scenario.reference + timedelta(seconds=max_age)).isoformat()
    planned_bq = initial_after_yield * math.exp(
        -scenario.network.rates[scenario.parent]
        * (scenario.calibration - scenario.reference).total_seconds()
    )
    deadline_met = completion <= scenario.calibration
    return {
        "title": scenario.title,
        "parent": scenario.parent,
        "reference_time": scenario.reference.isoformat(),
        "start_time": scenario.start.isoformat(),
        "planned_calibration_time": scenario.calibration.isoformat(),
        "completion_time": completion.isoformat(),
        "assessment_time": assessment.isoformat(),
        "latest_start": latest_start,
        "schedule_possible_from_reference": latest_start is not None,
        "activity_expiry_time": expiry,
        "nominal_duration_minutes": duration / 60,
        "deadline_slack_minutes": (scenario.calibration - completion).total_seconds() / 60,
        "target_activity_mbq": scenario.target_bq / 1e6,
        "planned_calibration_activity_mbq": planned_bq / 1e6,
        "assessment_activity_mbq": magnitude(activities[scenario.parent], "MBq"),
        "activity_target_met": target_met,
        "deadline_met": deadline_met,
        "feasible": target_met and deadline_met and latest_start is not None,
        "timeline": timeline,
    }


def monte_carlo(scenario: Scenario, *, samples: int, seed: int) -> dict:
    if type(samples) is not int or not 1 <= samples <= 1_000_000:
        raise ValueError("Samples must be an integer from 1 to 1000000")
    if type(seed) is not int or seed < 0:
        raise ValueError("Seed must be a nonnegative integer")
    rng = np.random.default_rng(seed)
    total = np.zeros(samples)
    for step in scenario.steps:
        if step.std_seconds == 0:
            total += step.mean_seconds
        else:
            sigma2 = math.log1p((step.std_seconds / step.mean_seconds) ** 2)
            mu = math.log(step.mean_seconds) - sigma2 / 2
            total += rng.lognormal(mu, math.sqrt(sigma2), samples)
    available = (scenario.calibration - scenario.start).total_seconds()
    reference_age = (scenario.start - scenario.reference).total_seconds()
    assessment_age = reference_age + np.maximum(total, available)
    activity = (
        scenario.initial_bq[scenario.parent]
        * scenario.retention
        * np.exp(-scenario.network.rates[scenario.parent] * assessment_age)
    )
    late = total > available + 1e-9
    short = activity < scenario.target_bq * (1 - 1e-12)
    misses = int(np.count_nonzero(late | short))
    p = misses / samples
    # Wilson score interval, with z = Phi^-1(.975).
    z = 1.959963984540054
    denominator = 1 + z * z / samples
    center = (p + z * z / (2 * samples)) / denominator
    radius = z * math.sqrt(p * (1 - p) / samples + z * z / (4 * samples * samples)) / denominator
    p95 = float(np.quantile(total, 0.95))
    return {
        "samples": samples,
        "seed": seed,
        "distribution": "independent lognormal step durations",
        "misses": misses,
        "probability_miss": p,
        "probability_deadline_miss": float(np.mean(late)),
        "probability_activity_shortfall": float(np.mean(short)),
        "wilson_95_interval": [max(0.0, center - radius), min(1.0, center + radius)],
        "total_duration_p50_minutes": float(np.quantile(total, 0.5)) / 60,
        "total_duration_p95_minutes": p95 / 60,
        "latest_start_for_p95_duration": _latest(scenario, p95),
        "assessment_activity_p05_mbq": float(np.quantile(activity, 0.05)) / 1e6,
    }
