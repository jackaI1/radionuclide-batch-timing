"""Exercise installed commands and generated files, including failure and HTML boundaries."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "batch_timing", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_run_exports_consistent_json_markdown_and_safe_offline_html(tmp_path):
    source = json.loads((ROOT / "examples/f18.json").read_text())
    source["title"] = '<script>alert("title")</script>'
    source["steps"][0]["name"] = "<img src=x onerror=alert(1)>"
    config = tmp_path / "input.json"
    config.write_text(json.dumps(source))
    result = run_cli(
        "run",
        config,
        "--samples",
        1000,
        "--seed",
        23,
        "--json",
        tmp_path / "out.json",
        "--html",
        tmp_path / "out.html",
        "--markdown",
        tmp_path / "out.md",
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / "out.json").read_text())
    assert data["scenario"] == source
    assert data["model"]["educational_only"] is True
    assert data["result"]["parent"] == "F-18"
    assert data["monte_carlo"]["samples"] == 1000
    html = (tmp_path / "out.html").read_text()
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "https://fonts." not in html
    assert f"{data['monte_carlo']['probability_miss'] * 100:.2f}%" in html
    assert "not for dose or production decisions" in html
    assert "Latest nominal start" in (tmp_path / "out.md").read_text()


def test_data_command_lists_pinned_sources_and_no_network_is_needed():
    result = run_cli("data")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["ground_states"]["18F"]["halflife"]["inSeconds"]["value"] == 6584.04
    assert data["source"].startswith("https://www.nndc.bnl.gov/")
    assert len(data["ground_states"]) == 12


@pytest.mark.parametrize("content", ["not json", "{}", "[]"])
def test_bad_cli_input_has_readable_error_and_no_outputs(tmp_path, content):
    config = tmp_path / "bad.json"
    config.write_text(content)
    result = run_cli("run", config, "--html", tmp_path / "absent.html")
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "absent.html").exists()


def test_missing_input_and_invalid_sample_count_are_clear(tmp_path):
    result = run_cli("run", tmp_path / "missing.json")
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    result = run_cli("run", ROOT / "examples/f18.json", "--samples", 0)
    assert result.returncode == 2
    assert "Samples" in result.stderr


def test_every_saved_example_runs(tmp_path):
    for example in sorted((ROOT / "examples").glob("*.json")):
        result = run_cli(
            "run", example, "--samples", 200, "--json", tmp_path / f"{example.stem}.json"
        )
        assert result.returncode == 0, result.stderr
        document = json.loads((tmp_path / f"{example.stem}.json").read_text())
        assert document["result"]["timeline"][-1]["activities_mbq"]
        assert 0 <= document["monte_carlo"]["probability_miss"] <= 1


def test_nudat_extraction_preserves_ground_state_and_hash():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("fetch_nudat", ROOT / "scripts/fetch_nudat.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    pinned = json.loads((ROOT / "src/batch_timing/data/nudat_snapshot.json").read_text())
    raw = json.dumps(
        {
            "nuclides": [
                {
                    "name": name,
                    "levels": [state, {**state, "energy": {"value": 970, "unit": "keV"}}],
                }
                for name, state in pinned["ground_states"].items()
            ]
        }
    ).encode()
    extracted = module.extract(raw, "test-fixture")
    assert extracted["ground_states"] == pinned["ground_states"]
    assert len(extracted["source_sha256"]) == 64
    bad = json.loads(raw)
    bad["nuclides"][0]["levels"][0]["energy"]["value"] = 10
    with pytest.raises(ValueError, match="ground state"):
        module.extract(json.dumps(bad).encode(), "test-fixture")


def test_report_regeneration_checks_real_outputs_and_detects_drift(tmp_path):
    command = [
        sys.executable,
        str(ROOT / "scripts/regenerate_reports.py"),
        "--output-dir",
        str(tmp_path),
    ]
    generated = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert generated.returncode == 0, generated.stderr
    verified = subprocess.run(
        command + ["--check"], capture_output=True, text=True, timeout=30, check=False
    )
    assert verified.returncode == 0, verified.stderr
    assert len(list(tmp_path.iterdir())) == 6
    (tmp_path / "f18.json").write_text("{}")
    stale = subprocess.run(
        command + ["--check"], capture_output=True, text=True, timeout=30, check=False
    )
    assert stale.returncode == 1
    assert "f18.json" in stale.stderr


def test_cli_does_not_overwrite_scenario_or_conflicting_outputs(tmp_path):
    config = tmp_path / "input.json"
    original = (ROOT / "examples/f18.json").read_text()
    config.write_text(original)
    result = run_cli("run", config, "--json", config)
    assert result.returncode == 2
    assert config.read_text() == original
    result = run_cli("run", config, "--json", tmp_path / "x", "--html", tmp_path / "x")
    assert result.returncode == 2
    assert not (tmp_path / "x").exists()


@pytest.mark.parametrize("text", ["1 (s", "1 / 0 s"])
def test_cli_handles_malformed_quantity_expressions_without_traceback(tmp_path, text):
    source = json.loads((ROOT / "examples/f18.json").read_text())
    source["steps"][0]["mean_duration"] = text
    config = tmp_path / "input.json"
    config.write_text(json.dumps(source))
    result = run_cli("run", config)
    assert result.returncode == 2
    assert "Invalid quantity" in result.stderr
    assert "Traceback" not in result.stderr


def test_report_keeps_exact_supplied_inputs_for_rerunning():
    from batch_timing.report import build_document

    source = json.loads((ROOT / "examples/f18.json").read_text())
    source["steps"][0]["retention"] = 0.9512345678912345
    document = build_document(source, samples=100, seed=23)
    assert document["scenario"] == source
    again = build_document(document["scenario"], samples=100, seed=23)
    assert again == document
