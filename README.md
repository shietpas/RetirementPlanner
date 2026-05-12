# RetirementCalc

Local Python desktop app for retirement withdrawal planning with tax-aware account handling.

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

If your machine policy still prevents activation, run without activating:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Test

```powershell
python -m unittest discover -s tests
```
