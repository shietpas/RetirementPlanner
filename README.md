# RetirementCalc

Local Python desktop app for retirement withdrawal planning with tax-aware account handling.

## Features in current scaffold
- Explicit account types with separate Roth and Non-Roth variants (for example, 401k and 401k Roth)
- Basic withdrawal tax classification helpers
- Deterministic account growth with configurable annual return rates
- Starter tkinter desktop UI shell

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Test

```powershell
python -m unittest discover -s tests
```
