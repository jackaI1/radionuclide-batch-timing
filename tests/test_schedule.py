"""Reference clocks, retention and distribution tails have independent expected results."""

import math
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from scipy.stats import lognorm

from batch_timing.schedule import Scenario, evaluate, monte_carlo


@pytest.fixture
def config():
    return {
        "title": "Clock example",
        "parent": "F-18",
        "reference_time": "2026-01-01T08:00:00Z",
        "start_time": "2026-01-01T08:30:00Z",
        "calibration_time": "2026-01-01T10:00:00Z",
        "initial_activities": {"F-18": "1000 MBq"},
        "target_activity": "400 MBq",
        "steps": [
            {"name": "Mix", "mean_duration": "30 min", "std_duration": "0 min", "retention": 0.8},
            {"name": "Check", "mean_duration": "20 min", "std_duration": "0 min", "retention": 1},
        ],
    }


def test_reference_hold_and_fixed_calibration(config):
    result = evaluate(Scenario.from_dict(config))
    expected = 800 * 2 ** (-7200 / 6584.04)
    assert result["assessment_activity_mbq"] == pytest.approx(expected)
    assert result["latest_start"] == "2026-01-01T09:10:00+00:00"
    assert result["completion_time"] == "2026-01-01T09:20:00+00:00"
    assert result["deadline_slack_minutes"] == 40
    assert not result["feasible"]
    assert not result["activity_target_met"]
    assert result["timeline"][1]["activities_mbq"]["F-18"] == pytest.approx(
        1000 * 2 ** (-1800 / 6584.04)
    )
    assert result["timeline"][2]["activities_mbq"]["F-18"] == pytest.approx(
        800 * 2 ** (-3600 / 6584.04)
    )
    assert result["activity_expiry_time"] == "2026-01-01T09:49:44.040000+00:00"


def test_moving_workflow_later_does_not_reset_source_age(config):
    earlier = evaluate(Scenario.from_dict(config))
    config["start_time"] = "2026-01-01T09:10:00Z"
    later = evaluate(Scenario.from_dict(config))
    assert later["assessment_activity_mbq"] == pytest.approx(earlier["assessment_activity_mbq"])
    assert later["deadline_slack_minutes"] == 0


def test_late_completion_is_assessed_after_planned_calibration(config):
    config["start_time"] = "2026-01-01T09:30:00Z"
    result = evaluate(Scenario.from_dict(config))
    assert result["assessment_time"] == "2026-01-01T10:20:00+00:00"
    assert not result["deadline_met"]
    assert result["assessment_activity_mbq"] == pytest.approx(800 * 2 ** (-8400 / 6584.04))


def test_latest_start_can_be_impossible_before_source_exists(config):
    config["steps"][0]["mean_duration"] = "3 h"
    result = evaluate(Scenario.from_dict(config))
    assert result["latest_start"] is None
    assert not result["schedule_possible_from_reference"]


def test_initial_daughters_and_retention_feed_real_step_inventory(config):
    config["parent"] = "Ac-225"
    config["initial_activities"] = {"Ac-225": "1 MBq", "Bi-213": ".5 MBq"}
    config["target_activity"] = ".5 MBq"
    result = evaluate(Scenario.from_dict(config))
    assert result["timeline"][0]["activities_mbq"]["Bi-213"] == 0.5
    assert result["timeline"][2]["activities_mbq"]["Pb-209"] > 0
    assert result["activity_target_met"]


def test_zero_variance_mc_exactly_matches_schedule(config):
    config["target_activity"] = "300 MBq"
    scenario = Scenario.from_dict(config)
    result = monte_carlo(scenario, samples=1000, seed=17)
    assert result["misses"] == 0
    assert result["probability_miss"] == 0
    assert result["probability_activity_shortfall"] == 0
    assert result["probability_deadline_miss"] == 0
    assert result["total_duration_p95_minutes"] == 50
    assert result["latest_start_for_p95_duration"] == "2026-01-01T09:10:00+00:00"
    assert result["wilson_95_interval"][1] > 0  # zero observations is not a zero risk guarantee


def test_seed_and_lognormal_tail_match_independent_analytic_case(config):
    config["start_time"] = config["reference_time"]
    config["steps"] = [
        {"name": "One step", "mean_duration": "100 min", "std_duration": "30 min", "retention": 1}
    ]
    config["target_activity"] = "1 MBq"
    scenario = Scenario.from_dict(config)
    result = monte_carlo(scenario, samples=40000, seed=91)
    assert result == monte_carlo(scenario, samples=40000, seed=91)
    sigma = math.sqrt(math.log1p(0.3**2))
    expected = lognorm.sf(120, s=sigma, scale=100 / math.sqrt(1 + 0.3**2))
    assert result["probability_deadline_miss"] == pytest.approx(expected, abs=0.008)
    assert result["probability_miss"] == result["probability_deadline_miss"]
    lo, hi = result["wilson_95_interval"]
    assert lo < result["probability_miss"] < hi


def test_target_equality_is_success_and_low_activity_can_make_every_trial_miss(config):
    config["initial_activities"] = {"F-18": "1 MBq"}
    config["target_activity"] = "1 MBq"
    config["steps"] = [
        {"name": "Instant", "mean_duration": "0 s", "std_duration": "0 s", "retention": 1}
    ]
    config["start_time"] = config["calibration_time"] = config["reference_time"]
    assert evaluate(Scenario.from_dict(config))["feasible"]
    assert monte_carlo(Scenario.from_dict(config), samples=10, seed=1)["misses"] == 0
    config["target_activity"] = "2 MBq"
    result = monte_carlo(Scenario.from_dict(config), samples=10, seed=1)
    assert result["misses"] == 10
    assert result["probability_activity_shortfall"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("reference_time", "2026-01-01T08:00:00"),
        ("start_time", "2026-01-01T07:00:00Z"),
        ("calibration_time", "2026-01-01T08:15:00Z"),
        ("target_activity", "2 min"),
        ("target_activity", "0 Bq"),
        ("target_activity", 100),
        ("parent", "Unknown"),
        ("initial_activities", {"F-18": "-1 MBq"}),
        ("initial_activities", {"Ga-68": "1 Bq"}),
        ("steps", []),
        ("typo", 1),
    ],
)
def test_invalid_scenario_boundaries(config, field, value):
    config[field] = value
    with pytest.raises((ValueError, TypeError)):
        Scenario.from_dict(config)


@pytest.mark.parametrize(
    "field,value",
    [
        ("retention", 1.1),
        ("retention", -1),
        ("retention", float("nan")),
        ("retention", True),
        ("mean_duration", "-1 min"),
        ("mean_duration", "1 MBq"),
        ("mean_duration", "0 s"),
        ("std_duration", "-1 s"),
        ("name", ""),
        ("unexpected", "hello"),
    ],
)
def test_invalid_steps(config, field, value):
    config["steps"][0][field] = value
    config["steps"][0]["std_duration"] = (
        "1 min" if field == "mean_duration" else config["steps"][0]["std_duration"]
    )
    with pytest.raises((ValueError, TypeError)):
        Scenario.from_dict(config)


def test_timezone_offsets_are_normalized_to_utc(config):
    config["reference_time"] = "2026-01-01T03:00:00-05:00"
    parsed = Scenario.from_dict(config)
    assert parsed.reference == datetime(2026, 1, 1, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    "samples,seed", [(0, 1), (-1, 1), (1.2, 1), (True, 1), (10, -1), (10, True)]
)
def test_invalid_mc_inputs(config, samples, seed):
    with pytest.raises(ValueError):
        monte_carlo(Scenario.from_dict(deepcopy(config)), samples=samples, seed=seed)
