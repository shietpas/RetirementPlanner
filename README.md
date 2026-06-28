# RetirementCalc

Local Python desktop app for retirement withdrawal planning with tax-aware account handling.

## Overview

RetirementCalc helps compare withdrawal strategies across different account types to better understand tax efficiency over time. The main goal is to think through when to draw from taxable accounts, traditional pre-tax accounts, and Roth accounts so the plan reflects the different tax treatment of capital gains, ordinary income, and tax-free withdrawals.

The app is intentionally narrow in scope. It does not currently model Roth conversion strategies or detailed household expense tracking. Instead, it focuses on a target annual net spending amount and estimates how that spending can be funded from salary, Social Security, pension income, and account withdrawals. That makes it useful as a planning aid for exploring tax tradeoffs, even though it is not yet a full retirement budgeting engine.

The practical value is in showing how different accounts can be used at different points in time, what taxes are triggered, and how much of the desired spending target is actually funded after taxes.

## Market Return Scenario Logic

The stock projection model uses one long-run reference return for the market and then layers scenario-specific adjustments and annual randomness on top of it.

- The likely scenario is centered on a long-run stock return of about 10%, which is intended to roughly match the S&P 500's total-return behavior over the last 20 years.
- The pessimistic and optimistic scenarios are percentage-point adjustments around that baseline. Negative values move the expected return below the long-run reference, and positive values move it above the reference.
- Each projected year still includes randomness. The model draws a yearly stock shock from a normal distribution, then adds that shock to the scenario target return. That means the same scenario can produce different year-to-year outcomes while still converging to the requested statistical expectation over many runs.
- Bond returns are modeled separately with a smaller baseline and a partial offset against the stock shock so the overall portfolio is not forced to move in lockstep with the stock leg.

Parameters that control this behavior in the app:

- `Stock Shock Volatility %`: the size of the random annual stock shock. Higher values produce a wider distribution of yearly outcomes.
- `Pessimistic Return Delta %`: percentage-point adjustment below the long-run reference return.
- `Likely Return Delta %`: percentage-point adjustment around the long-run reference return. The default is `0`, which keeps the likely case aligned with the baseline reference.
- `Optimistic Return Delta %`: percentage-point adjustment above the long-run reference return.

If you want the likely case to be closer to or farther from the S&P 500 reference, change the likely delta. If you want the whole projection to be more or less volatile, adjust the shock volatility.

## Inflation Adjustment

The spending target is inflation-adjusted each projection year so the plan keeps aiming at the same purchasing power over time.

- The first projection year uses the spending target you enter.
- Each later year increases that target by the configured annual inflation rate.
- For example, a $15,000 target with 2.5% inflation becomes $15,375 in year two and $15,759.38 in year three.

Parameters that control this behavior in the app:

- `Inflation Rate % (annual)`: the annual increase applied to the spending target. The default is `2.5`.
- `Household Spending Target (annual)`: the base target used for the first projection year.

This is a nominal adjustment. It does not alter tax tables or market returns; it only raises the spending target so later years compare against the same approximate buying power.

## Prerequisites

If you are new to Python, install these first:

- Python 3.12 or newer
- Visual Studio Code, if you want an editor and easy access to the workspace
- The Python extension for VS Code, if you want syntax highlighting, linting, and launch support

On Windows, make sure Python is available in your PATH or know the full path to the Python executable. During installation, the "Add Python to PATH" option is usually the easiest choice. If you already installed Python, you can check that it is available by opening PowerShell and running `python --version`.

If `python` is not recognized, reinstall Python and enable PATH integration, or use the full path to the interpreter when running commands.

## Features in current scaffold
- Explicit account types with separate Roth and Non-Roth variants (for example, 401k and 401k Roth)
- Basic withdrawal tax classification helpers
- IRS federal tax bracket table stored separately in `src/retirement_calc/config/tax_tables.json`
- IRS capital gains tax table stored separately in `src/retirement_calc/config/capital_gains_tax_tables.json`
- Deterministic account growth with configurable annual return rates
- Starter tkinter desktop UI shell

## Run

```powershell
python -m venv .venv
# If activation is blocked by execution policy, use a temporary bypass:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

The app loads federal income tax brackets and capital gains thresholds from the bundled IRS configuration files. Use the "Refresh IRS Tax Tables" button in the app to update those files from the latest IRS sources.

If you are using VS Code, you can also open the project folder and run the app from the integrated terminal after creating the virtual environment.

If your machine policy still prevents activation, run without activating:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Test

```powershell
python -m unittest discover -s tests
```

If you prefer, you can also run tests with the virtual environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
