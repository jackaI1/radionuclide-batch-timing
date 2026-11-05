"""Analytic fixtures catch wrong units, decay constants, feeding, and numerical instability."""

import math

import pytest

from batch_timing.decay import DecayNetwork, Nuclide, load_network
from batch_timing.units import quantity


def test_halving_and_cross_unit_inputs():
    network = DecayNetwork({"P": Nuclide(quantity("2 h"), {})})
    result = network.activities({"P": quantity("1 GBq")}, quantity("120 min"))
    assert result["P"].to("MBq").magnitude == pytest.approx(500)


def test_two_member_bateman_with_initial_daughter():
    network = DecayNetwork(
        {"P": Nuclide(quantity("10 s"), {"D": 0.75}), "D": Nuclide(quantity("5 s"), {})}
    )
    # Np(10)=50, Nd(10)=20/4 + .75*100*(.5-.25) = 23.75 atoms.
    result = network.atoms({"P": 100, "D": 20}, quantity("10 s"))
    assert result == pytest.approx({"P": 50, "D": 23.75}, rel=1e-12)


def test_equal_half_lives_uses_bateman_limit():
    network = DecayNetwork(
        {"P": Nuclide(quantity("10 s"), {"D": 1}), "D": Nuclide(quantity("10 s"), {})}
    )
    assert network.atoms({"P": 100}, quantity("10 s"))["D"] == pytest.approx(50 * math.log(2))


def test_branching_recombination_conserves_atoms():
    network = DecayNetwork(
        {
            "P": Nuclide(quantity("1 s"), {"L": 0.3, "R": 0.7}),
            "L": Nuclide(quantity("2 s"), {"S": 1}),
            "R": Nuclide(quantity("3 s"), {"S": 1}),
            "S": Nuclide(None, {}),
        }
    )
    result = network.atoms({"P": 100}, quantity("20 s"))
    assert sum(result.values()) == pytest.approx(100, rel=1e-12)
    assert all(x >= 0 for x in result.values())
    assert result["S"] > 98


def test_zero_time_and_semigroup_for_stiff_public_chain():
    network = load_network("Ac-225")
    initial = {"Ac-225": 1e12}
    assert network.atoms(initial, quantity("0 s"))["Ac-225"] == 1e12
    direct = network.atoms(initial, quantity("2 h"))
    split = network.atoms(network.atoms(initial, quantity("1 h")), quantity("1 h"))
    assert split == pytest.approx(direct, rel=1e-12, abs=1e-12)
    expected = 1e12 * math.exp(-math.log(2) * 7200 / 857001.6)
    assert direct["Ac-225"] == pytest.approx(expected, rel=1e-13)
    assert direct["Po-213"] > 0


@pytest.mark.parametrize("bad", ["3 MBq", "-1 s", "nan s", "inf s", 60])
def test_invalid_time_is_rejected(bad):
    network = DecayNetwork({"P": Nuclide(quantity("1 s"), {})})
    with pytest.raises((ValueError, TypeError)):
        network.atoms({"P": 100}, quantity(bad) if isinstance(bad, str) else bad)


@pytest.mark.parametrize("initial", [{"P": -1}, {"P": float("nan")}, {"unknown": 10}])
def test_invalid_populations_are_rejected(initial):
    with pytest.raises(ValueError):
        DecayNetwork({"P": Nuclide(quantity("1 s"), {})}).atoms(initial, quantity("1 s"))


@pytest.mark.parametrize(
    "half,branches",
    [
        ("0 s", {}),
        ("-1 s", {}),
        ("1 kg", {}),
        ("1 s", {"X": 1}),
        ("1 s", {"P": 1.1}),
        ("1 s", {"P": -0.1}),
    ],
)
def test_invalid_network_is_rejected(half, branches):
    with pytest.raises(ValueError):
        DecayNetwork({"P": Nuclide(quantity(half), branches)})


@pytest.mark.parametrize(
    "nuclide,half_seconds",
    [
        ("F-18", 6584.04),
        ("Ga-68", 4070.58),
        ("Cu-64", 45722.52),
        ("Lu-177", 574318.08),
        ("Ac-225", 857001.6),
    ],
)
def test_pinned_nuclides_halve_at_public_half_life(nuclide, half_seconds):
    result = load_network(nuclide).activities(
        {nuclide: quantity("80 MBq")}, quantity(f"{half_seconds} s")
    )
    assert result[nuclide].to("MBq").magnitude == pytest.approx(40, rel=1e-12)


def test_activity_rejects_dimensionless_and_stable_initial_inventory():
    net = DecayNetwork({"S": Nuclide(None, {})})
    with pytest.raises(ValueError):
        net.activities({"S": quantity("1 MBq")}, quantity("1 s"))
    with pytest.raises((TypeError, ValueError)):
        load_network("F-18").activities({"F-18": quantity("1 kg")}, quantity("1 s"))


@pytest.mark.parametrize("text", ["1 (s", "1 / 0 s", "1 ** s", "1 @ s", "1 unknownunit"])
def test_malformed_quantity_expressions_become_validation_errors(text):
    with pytest.raises(ValueError, match="Invalid quantity"):
        quantity(text)
