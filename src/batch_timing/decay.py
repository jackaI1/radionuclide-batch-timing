"""Bateman equations as a high-precision matrix exponential, including branches.

N'(t) = M N(t), M_ii = -lambda_i, M_ji = branch_ij * lambda_i.
N(t) = exp(M t) N(0). This also handles equal half-lives without singular sums.
"""

import json
import math
from dataclasses import dataclass
from importlib.resources import files

import mpmath as mp

from .units import Quantity, magnitude, quantity


@dataclass(frozen=True)
class Nuclide:
    half_life: Quantity | None
    branches: dict[str, float]


class DecayNetwork:
    def __init__(self, nuclides: dict[str, Nuclide]):
        if not nuclides:
            raise ValueError("A decay network cannot be empty")
        self.nuclides = dict(nuclides)
        self.names = tuple(nuclides)
        self.rates = {}
        with mp.workdps(50):
            self.generator = mp.zeros(len(self.names))
            for i, name in enumerate(self.names):
                nuclide = nuclides[name]
                half = (
                    magnitude(nuclide.half_life, "s", positive=True)
                    if nuclide.half_life is not None
                    else None
                )
                rate = mp.log(2) / mp.mpf(str(half)) if half is not None else mp.mpf(0)
                self.rates[name] = float(rate)
                self.generator[i, i] = -rate
                total = 0.0
                for target, fraction in nuclide.branches.items():
                    if target not in nuclides:
                        raise ValueError(f"Unknown daughter {target}")
                    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                        raise ValueError("Branch fractions must be finite and between zero and one")
                    total += fraction
                    self.generator[self.names.index(target), i] += mp.mpf(str(fraction)) * rate
                if total > 1 + 1e-12:
                    raise ValueError("Branch fractions cannot sum to more than one")
                if half is None and nuclide.branches:
                    raise ValueError("Stable nuclides cannot feed daughters")

    def atoms(self, initial: dict[str, float], elapsed: Quantity) -> dict[str, float]:
        seconds = magnitude(elapsed, "s")
        if set(initial) - set(self.names):
            raise ValueError("Initial inventory contains an unknown nuclide")
        if any(not math.isfinite(v) or v < 0 for v in initial.values()):
            raise ValueError("Atom populations must be finite and nonnegative")
        if seconds == 0:
            return {name: float(initial.get(name, 0)) for name in self.names}
        with mp.workdps(50):
            vector = mp.matrix([initial.get(name, 0) for name in self.names])
            evolved = mp.expm(self.generator * mp.mpf(str(seconds))) * vector
            return {name: max(0.0, float(evolved[i])) for i, name in enumerate(self.names)}

    def activities(self, initial: dict[str, Quantity], elapsed: Quantity) -> dict[str, Quantity]:
        atoms = {}
        for name, activity in initial.items():
            if name not in self.nuclides:
                raise ValueError(f"Unknown initial nuclide: {name}")
            bq = magnitude(activity, "Bq")
            if self.rates[name] == 0:
                if bq:
                    raise ValueError("Use atoms() for an initial stable inventory")
                atoms[name] = 0
            else:
                atoms[name] = bq / self.rates[name]
        evolved = self.atoms(atoms, elapsed)
        return {
            name: quantity(f"{population * self.rates[name]} Bq")
            for name, population in evolved.items()
        }


def snapshot() -> dict:
    return json.loads(files("batch_timing").joinpath("data/nudat_snapshot.json").read_text())


# Omitted rare modes leave the tracked network. Fractions are not renormalized.
# Bi-209 retains its evaluated extremely long half-life; its daughter is untracked.
TOPOLOGY = {
    "Ac-225": {"a": "Fr-221"},
    "Fr-221": {"a": "At-217"},
    "At-217": {"a": "Bi-213"},
    "Bi-213": {"B-": "Po-213", "a": "Tl-209"},
    "Po-213": {"a": "Pb-209"},
    "Tl-209": {"B-": "Pb-209"},
    "Pb-209": {"B-": "Bi-209"},
    "Bi-209": {},
}
SINGLES = ("F-18", "Ga-68", "Cu-64", "Lu-177")


def load_network(parent: str) -> DecayNetwork:
    if parent not in (*SINGLES, "Ac-225"):
        raise ValueError(f"Unsupported parent {parent}; choose {', '.join((*SINGLES, 'Ac-225'))}")
    raw = snapshot()["ground_states"]
    names = TOPOLOGY if parent == "Ac-225" else {parent: {}}
    nuclides = {}
    for name in names:
        element, mass = name.split("-")
        ground = raw[mass + element]
        seconds = ground["halflife"]["inSeconds"]["value"]
        observed = {item["mode"]: item["value"] / 100 for item in ground["decayModes"]["observed"]}
        branches = {daughter: observed[mode] for mode, daughter in names[name].items()}
        nuclides[name] = Nuclide(quantity(f"{seconds} s"), branches)
    return DecayNetwork(nuclides)
