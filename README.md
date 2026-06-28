# RetirementCalc

Local Python desktop app for retirement withdrawal planning with tax-aware account handling.

## Overview

RetirementCalc helps compare withdrawal strategies across different account types to better understand tax efficiency over time. The main goal is to think through when to draw from taxable accounts, traditional pre-tax accounts, and Roth accounts so the plan reflects the different tax treatment of capital gains, ordinary income, and tax-free withdrawals.

The app is intentionally narrow in scope. It does not currently model Roth conversion strategies, inflation, or detailed household expense tracking. Instead, it focuses on a target monthly or annual net spending amount and estimates how that spending can be funded from salary, Social Security, pension income, and account withdrawals. That makes it useful as a planning aid for exploring tax tradeoffs, even though it is not yet a full retirement budgeting engine.

The practical value is in showing how different accounts can be used at different points in time, what taxes are triggered, and how much of the desired spending target is actually funded after taxes.

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
