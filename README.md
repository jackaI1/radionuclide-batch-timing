# Radionuclide batch timing

I built a radioactive batch timing simulator because I wanted to see how much activity is left after preparation and waiting, and whether a plan still works when a step runs late.

Activity means the rate of radioactive decay. A batch keeps losing activity while it waits, moves, and gets checked. I enter its starting activity, the time that activity refers to, a list of steps, and the activity I want at calibration, the planned check time. The simulator shows what remains after each step, the latest start that fits the deadline, and how often variable step times would miss the plan. It also follows the radioactive daughters produced as Ac-225 decays.

**This is an educational model, not for dose or production decisions.** The example schedules and retention fractions are made-up study inputs. They are not measurements or operating instructions.

[Read the F-18 study without installing anything](reports/f18.md), or [see Ac-225 and its daughters](reports/ac225.md). The [F-18 HTML report](reports/f18.html) and [Ac-225 HTML report](reports/ac225.html) can be downloaded and opened in a browser offline. Each includes the inputs, step activities, timing risk, assumptions, and decay-data provenance.

## Run my example

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), which manages Python and dependencies, then run:

```sh
git clone https://github.com/jackaI1/radionuclide-batch-timing.git
cd radionuclide-batch-timing
uv sync --locked --extra dev
uv run radionuclide-batch run examples/f18.json \
  --samples 20000 --seed 2026 \
  --json reports/f18.json --markdown reports/f18.md --html reports/f18.html
```

Open `reports/f18.html`, or read `reports/f18.md` directly on GitHub. Running without export options prints the whole result as JSON. `uv run radionuclide-batch --help` lists the commands.

In that saved F-18 example, the parent activity at calibration is **431.909 MBq** against a **430 MBq** target. MBq means a million decays per second. The latest nominal start is **08:40 UTC**; the example starts at **08:30 UTC**. With the supplied step-time variation, **3,771 of 20,000 trials miss the activity target or deadline, or 18.855%**. The sampling interval is **18.32% to 19.40%**. These results come from the command above; they describe this invented scenario, not a real facility.

The nominal plan passes, but its timing margin is small. That is the part I wanted to make visible: a plan that works at the average step durations can still miss fairly often.

## Change the batch

Copy [examples/f18.json](examples/f18.json) and edit it. [examples/ac225.json](examples/ac225.json) starts with only Ac-225, so the report shows daughter activity growing in after an ideal separation.

- Choose `F-18`, `Ga-68`, `Cu-64`, `Lu-177`, or `Ac-225` as `parent`.
- Give `initial_activities` at `reference_time`. For Ac-225, this can include any tracked daughters already present.
- Set `start_time`, `calibration_time`, and `target_activity`. The target always applies to the selected parent, not the sum of parent and daughter activities.
- For each step, supply `mean_duration`, `std_duration`, and `retention`. The standard deviation describes how much its duration varies. Retention is the fraction left after a transfer or other loss; it applies equally to every tracked nuclide.
- Use strings with units, such as `"1000 MBq"`, `"1 GBq"`, `"35 min"`, or `"2 h"`. Bare numbers and incompatible units are rejected at the physical input boundaries. Clock times need a timezone.

For example, replace the parent and initial-activity key in a copy with `Ga-68`, then run the same command with that file path. The supported parents all use the same scheduling and reporting code. The full [input and modelling guide](docs/model.md) explains the fields and limitations.

## What “latest start” means

I keep the source's activity reference time fixed. Starting work later does not give the source its original activity back.

The latest nominal start is calibration time minus the total mean process duration. I separately check whether the parent activity survives until calibration after the specified losses. If the target is already impossible, the report says so even when the steps fit the clock. `activity_expiry_time` gives the last clock time the retained parent could meet the target; it is not a process start recommendation.

For a late batch, activity is assessed at completion, since the steps were not finished at the planned calibration. A Monte Carlo trial, a randomly sampled schedule, counts as a miss if it finishes late **or** lacks the target activity. I report those risks separately as well as together. The sampled start allowance based on a longer-duration percentile addresses deadline risk only; it cannot fix an activity shortfall.

## Where I got the decay data

I downloaded the public [NNDC NuDat chart dataset](https://www.nndc.bnl.gov/nudat3/data/output.json) and kept just the ground-state half-lives, uncertainties, and observed decay modes I use in [nudat_snapshot.json](src/batch_timing/data/nudat_snapshot.json). A ground state is the nucleus's lowest-energy state. NuDat's [user guide](https://www.nndc.bnl.gov/nudat3/guide/) explains the underlying evaluated nuclear databases. No substitute data source was needed.

The snapshot records the retrieval time and the full download's SHA-256 fingerprint. The table below comes from `uv run radionuclide-batch data`, which prints the pinned data and provenance. The linked NuDat pages are per-nuclide references; their live values can change after this snapshot.

| Nuclide | Pinned ground-state half-life | NuDat reference |
| --- | --- | --- |
| F-18 | 109.734 min | [F-18](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=18F&unc=NDS) |
| Ga-68 | 67.843 min | [Ga-68](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=68GA&unc=NDS) |
| Cu-64 | 12.7007 h | [Cu-64](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=64CU&unc=NDS) |
| Lu-177 | 6.6472 d | [Lu-177](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=177LU&unc=NDS) |
| Ac-225 | 9.919 d | [Ac-225](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=225AC&unc=NDS) |
| Fr-221 | 4.801 min | [Fr-221](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=221FR&unc=NDS) |
| At-217 | 32.6 ms | [At-217](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=217AT&unc=NDS) |
| Bi-213 | 45.607 min | [Bi-213](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=213BI&unc=NDS) |
| Po-213 | 3.706 µs | [Po-213](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=213PO&unc=NDS) |
| Tl-209 | 2.162 min | [Tl-209](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=209TL&unc=NDS) |
| Pb-209 | 3.235 h | [Pb-209](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=209PB&unc=NDS) |
| Bi-209 | 2.01 × 10¹⁹ y | [Bi-209](https://www.nndc.bnl.gov/nudat3/getdataset.jsp?nucleus=209BI&unc=NDS) |

The tracked Ac-225 path goes through Fr-221 and At-217 to Bi-213. Bi-213 splits into Po-213 and Tl-209, which both lead to Pb-209 and then Bi-209. The branch fractions come directly from the pinned observed modes. Small alternative modes from Ac-225, Fr-221, and At-217 leave the tracked network. I do not renormalize the remaining paths. Bi-209 keeps its evaluated long half-life, but its daughter is outside the model. For the other selectable parents I track parent activity only.

To deliberately refresh the public data and rebuild the studies:

```sh
uv run python scripts/fetch_nudat.py
uv run python scripts/regenerate_reports.py
uv run pytest -q
```

The simulator runs offline after dependencies are installed. CI uses the pinned snapshot and never depends on the live nuclear database being available.

## How I calculate it

I convert activity into atom populations, propagate those populations through Bateman equations, the coupled equations for radioactive parents feeding daughters, then convert back to activity. I solve their matrix form with a high-precision matrix exponential. This handles branches, initial daughter inventories, and identical half-lives without dividing by the difference between decay rates. The [model notes](docs/model.md) give the equations and exact approximations.

For the timing study I sample positive, independent lognormal step durations using the supplied mean and standard deviation. I use the parent’s analytic exponential decay for each trial, since no tracked daughter feeds back into a selectable parent. Daughter inventories in the nominal timeline use the full chain solver. The reported interval describes random sampling error; it does not cover uncertainty in half-lives, activity measurements, yields, or the distribution choice. I have not modelled dose, chemistry, equipment, staffing, biological clearance, or daughter recoil and escape.

## Code and checks

- `src/batch_timing/decay.py`: decay networks and Bateman propagation.
- `src/batch_timing/schedule.py`: clock planning, losses, and Monte Carlo timing.
- `src/batch_timing/units.py`: physical quantity validation.
- `src/batch_timing/report.py`: saved HTML, Markdown, and structured results.
- `examples/` and `reports/`: reproducible study inputs and outputs.

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/regenerate_reports.py --check
uv build
```

The tests cover analytic single decay, parent–daughter feeding, equal half-lives, branch recombination, the short-lived Ac-225 daughters, mixed units, retention, fixed reference times, impossible plans, reproducible sampling, and an independently calculated lognormal tail. Command-line tests exercise exports and invalid input. CI runs these checks and verifies that every saved report reproduces, on each pull request and on `main`.
