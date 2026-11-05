# Model and reproducibility notes

This is an educational model, not for dose or production decisions. The example inputs are hypothetical. No private measurements, operating procedures, or customer data are used.

## Decay inventory

For each nuclide i, the decay constant is λᵢ = ln(2)/Tᵢ, where Tᵢ is its half-life in seconds. Activity Aᵢ = λᵢNᵢ is in becquerels, or decays per second; Nᵢ is the expected atom population, which can be fractional in this deterministic model.

The Bateman system is:

```text
dNᵢ/dt = -λᵢ Nᵢ + Σⱼ bⱼᵢ λⱼ Nⱼ
Mᵢᵢ = -λᵢ; Mᵢⱼ = bⱼᵢ λⱼ for i != j
N(t) = exp(M t) N(0)
```

Here bⱼᵢ is the fraction of parent j decays that feed daughter i. This matrix exponential is the constant-coefficient Bateman solution. For a parent P feeding a daughter D with branch b and distinct rates:

```text
N_P(t) = N_P(0) exp(-λ_P t)
N_D(t) = N_D(0) exp(-λ_D t)
       + b λ_P N_P(0) [exp(-λ_P t) - exp(-λ_D t)] / (λ_D - λ_P)
```

When the rates are equal, the feeding term becomes `b λ t N_P(0) exp(-λ t)`. Tests compare the solver with both independent analytic forms. Matrix propagation also supports merging branches and avoids the cancellation and singular denominators in direct multi-member Bateman sums.

I use mpmath at 50 decimal digits internally. The Ac-225 network combines microsecond and day time scales, so a naive floating-point matrix exponential can lose accuracy. Internal inventories return ordinary floats for later unit conversion; exported numbers have ten significant digits for reproducible files. The display uses fewer digits for readability; those are not claims of measurement precision. A synthetic closed chain tests atom conservation; real Ac-225 has tracked-network leakage and is not assumed closed.

## Public source selection

`scripts/fetch_nudat.py` downloads the NuDat chart JSON served by NNDC, selects energy-zero levels by nuclide, and preserves each selected half-life, its uncertainty, and observed decay modes. It rejects missing or ambiguous ground states. It records the retrieval clock and SHA-256 of the complete downloaded bytes. The full external download is not committed; the small extracted subset is. `--source <downloaded-json>` can extract from a previously saved full source. A future refresh may change evaluated values and should be reviewed as a data change.

All per-nuclide references are in the README. The same snapshot drives single decay, daughter feeding, and parent-only Monte Carlo evaluation. Retained branches are looked up by observed decay mode, rather than transcribing rounded percentages into the solver. Rare cluster decays and the minor beta branches of Fr-221 and At-217 leave the tracked network. Their descendants are not simulated. NuDat quotes rounded central branch values; they are not a perfect unrounded probability distribution, and I do not rescale them. The Bi-213 split is retained on both sides through Pb-209. Bi-209 is included with its evaluated extremely long half-life and no tracked descendants. No emitted particles, photon energies, dose factors, or isomer populations are simulated.

For F-18, Ga-68, Cu-64, and Lu-177 only the ground-state parent is tracked. This is enough to evaluate that parent's remaining activity; it is not a complete radiation inventory. The source retrieval timestamp and fingerprint are also saved inside every report.

## Timing, retentions, and target

All clocks must have timezones and are converted to UTC before arithmetic, including across daylight-saving changes. The input order must satisfy `reference_time <= start_time <= calibration_time`. Finishing later than calibration is allowed as an input outcome and is explicitly marked late.

The initial inventory exists at the reference clock. It decays while waiting to start, during each step, and while waiting for calibration. At the end of a step, every nuclide's inventory is multiplied by that step's retention fraction. This makes retention an idealized removal of well-mixed material. It is not selective chemistry and does not simulate a real daughter separation during the workflow. The Ac-225 example assumes an ideal parent-only initial inventory; users can instead supply initial daughter activities.

The selected parent has no upstream feeder in this network, so its final activity after all losses is:

```text
A_parent(t) = A_reference × product(retentions) × exp(-λ_parent × age)
age = assessment_time - reference_time
assessment_time = max(planned_calibration_time, completion_time)
```

The latest nominal process start is `planned_calibration_time - sum(mean_durations)`. If this precedes the reference, no start is available. This clock calculation does not imply the activity target is achievable. `feasible` requires the nominal process to fit the deadline and meet the parent target. Reports retain the latest clock start even when activity is impossible, and show the failure separately.

For a positive retained activity sufficient at the reference, the activity expiry is `reference + ln(A_reference × product(retentions) / target)/λ`. If already below target, expiry is absent. This describes the activity budget with the specified losses applied, not a latest workflow start. At fixed reference and calibration times, moving an on-time workflow later cannot change its parent activity at calibration. Tests protect this distinction.

Timeline activity at a process step is the activity immediately after that step's retention. The first rows show the reference and the process start; the final row shows the assessment. JSON keys ending in `_mbq` use MBq, those ending in `_minutes` use minutes. Atom-population APIs use dimensionless expected atom counts. All API duration and activity arguments require Pint quantities; the JSON interface requires unit-bearing strings. Retentions and branch probabilities are dimensionless fractions.

## Monte Carlo model

Each uncertain step duration is independent and lognormal, so it is always positive. A step with supplied arithmetic mean m and standard deviation s uses:

```text
sigma² = ln(1 + (s/m)²)
mu = ln(m) - sigma²/2
duration = exp(Normal(mu, sigma))
```

Zero variation gives an exact fixed duration. Zero duration is allowed only with zero variation. The seed is explicit and the lockfile pins dependency versions. Samples are bounded to avoid accidental large memory allocations. Each step's samples are accumulated into a single total-duration array; no array of all steps and all samples is retained.

A trial is a deadline miss if completion is after the planned calibration, and an activity shortfall if assessed parent activity is below target. The combined miss is the union of those events, not the sum of their probabilities. Half-life, retention and measurement uncertainty are held fixed. For efficiency, trials use the parent's analytic exponential; the nominal daughter timeline uses matrix propagation. The standard deviation inputs are assumptions about process times, not measured isotope uncertainties.

The report gives a Wilson score sampling interval around the combined Bernoulli miss fraction. With no observed misses, its upper bound is still positive. The duration percentiles and implied earlier start are empirical estimates, not guarantees. A different duration distribution or correlations could change the result substantially. The suite checks a one-step lognormal deadline probability against SciPy's independently evaluated distribution tail.

## Reproduce or modify the saved studies

From the repository root:

```sh
uv sync --locked --extra dev
uv run python scripts/regenerate_reports.py
uv run python scripts/regenerate_reports.py --check
```

The generator uses the committed examples, pinned snapshot, explicit sample count, and seed. It writes HTML, Markdown, and JSON for each example. `--check` compares all saved files to a fresh run and returns a failing exit code for drift. It does not fetch new data. After editing a scenario, regenerate the reports deliberately. The source provenance can be read with `uv run radionuclide-batch data`.
