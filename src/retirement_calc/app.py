from __future__ import annotations

import csv
import json
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .calculations import (
    FLAT_EXPORT_COLUMNS,
    POWER_BI_EXPORT_COLUMNS,
    YearProjection,
    age_on_date,
    flatten_projection_metric_rows,
    flatten_projection_rows,
    simulate_retirement_scenarios,
)
from .capital_gains_tax_tables import (
    FILING_STATUS_MARRIED_JOINT as CG_FILING_STATUS_MARRIED_JOINT,
    FILING_STATUS_SINGLE as CG_FILING_STATUS_SINGLE,
    CONFIG_PATH as CG_CONFIG_PATH,
    capital_gains_brackets_for_status,
    load_capital_gains_config,
    refresh_capital_gains_config,
    save_capital_gains_config,
)
from .models import Account, AccountType
from .tax_tables import (
    FILING_STATUS_MARRIED_JOINT,
    FILING_STATUS_SINGLE,
    CONFIG_PATH,
    load_tax_table_config,
    refresh_tax_table_config,
    save_tax_table_config,
    tax_brackets_for_status,
)


ACCOUNT_TYPE_LABELS = {
    AccountType.K401_NON_ROTH: "401k (Non-Roth)",
    AccountType.K401_ROTH: "401k Roth",
    AccountType.B403_NON_ROTH: "403b (Non-Roth)",
    AccountType.B403_ROTH: "403b Roth",
    AccountType.IRA_TRADITIONAL: "IRA Traditional (Non-Roth)",
    AccountType.IRA_ROTH: "IRA Roth",
    AccountType.TAXABLE_INVESTMENT: "Taxable Investment",
}

LABEL_TO_ACCOUNT_TYPE = {label: account_type for account_type, label in ACCOUNT_TYPE_LABELS.items()}
ACCOUNT_TYPE_EXPORT_COLUMNS = [
    AccountType.K401_NON_ROTH,
    AccountType.K401_ROTH,
    AccountType.B403_NON_ROTH,
    AccountType.B403_ROTH,
    AccountType.IRA_TRADITIONAL,
    AccountType.IRA_ROTH,
    AccountType.TAXABLE_INVESTMENT,
]
SETTINGS_VERSION = 1


def _parse_date(value: str) -> date:
    try:
        year, month, day = value.strip().split("-")
        return date(int(year), int(month), int(day))
    except Exception as exc:
        raise ValueError("Date must be in YYYY-MM-DD format") from exc


class RetirementApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.accounts: list[Account] = []

        self.primary_name_var = tk.StringVar(value="Primary")
        self.primary_birth_var = tk.StringVar(value="1970-01-01")
        self.primary_ret_age_var = tk.StringVar(value="65")
        self.primary_salary_var = tk.StringVar(value="120000")
        self.primary_ss_age_var = tk.StringVar(value="67")
        self.primary_ss_monthly_var = tk.StringVar(value="2500")
        self.primary_has_pension_var = tk.BooleanVar(value=False)
        self.primary_pension_age_var = tk.StringVar(value="65")
        self.primary_pension_monthly_var = tk.StringVar(value="0")

        self.include_spouse_var = tk.BooleanVar(value=False)
        self.spouse_name_var = tk.StringVar(value="Spouse")
        self.spouse_birth_var = tk.StringVar(value="1972-01-01")
        self.spouse_ret_age_var = tk.StringVar(value="65")
        self.spouse_salary_var = tk.StringVar(value="90000")
        self.spouse_ss_age_var = tk.StringVar(value="67")
        self.spouse_ss_monthly_var = tk.StringVar(value="2000")
        self.spouse_has_pension_var = tk.BooleanVar(value=False)
        self.spouse_pension_age_var = tk.StringVar(value="65")
        self.spouse_pension_monthly_var = tk.StringVar(value="0")

        self.account_owner_var = tk.StringVar(value="Primary")
        self.account_name_var = tk.StringVar(value="")
        self.account_type_var = tk.StringVar(value=ACCOUNT_TYPE_LABELS[AccountType.K401_NON_ROTH])
        self.account_balance_var = tk.StringVar(value="0")
        self.account_stock_mix_var = tk.StringVar(value="70")
        self.account_cost_basis_var = tk.StringVar(value="0")
        self.account_capital_gains_var = tk.StringVar(value="0")

        self.withdrawal_mode_var = tk.StringVar(value="flat")
        self.withdrawal_value_var = tk.StringVar(value="60000")
        self.inflation_rate_var = tk.StringVar(value="2.5")
        self.projection_years_var = tk.StringVar(value="30")
        self.return_volatility_var = tk.StringVar(value="12")
        self.pessimistic_bias_var = tk.StringVar(value="-3")
        self.likely_bias_var = tk.StringVar(value="0")
        self.optimistic_bias_var = tk.StringVar(value="3")
        self.tax_table_status_var = tk.StringVar(value="")
        self.cap_gains_table_status_var = tk.StringVar(value="")
        self.last_projection_by_scenario: dict[str, list[YearProjection]] = {}
        self.tax_table_config = load_tax_table_config()
        self.capital_gains_table_config = load_capital_gains_config()
        self.include_spouse_var.trace_add("write", lambda *_: self._update_tax_table_status())
        self.include_spouse_var.trace_add("write", lambda *_: self._update_capital_gains_table_status())
        self.include_spouse_var.trace_add("write", lambda *_: self._toggle_pension_inputs())
        self.primary_has_pension_var.trace_add("write", lambda *_: self._toggle_pension_inputs())
        self.spouse_has_pension_var.trace_add("write", lambda *_: self._toggle_pension_inputs())

        self._build_ui()
        self._update_tax_table_status()
        self._update_capital_gains_table_status()

    def _build_ui(self) -> None:
        self.root.title("RetirementCalc")
        self.root.geometry("1180x760")

        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_container, highlightthickness=0)
        vertical_scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        horizontal_scrollbar = ttk.Scrollbar(main_container, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vertical_scrollbar.set, xscrollcommand=horizontal_scrollbar.set)

        vertical_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        outer = ttk.Frame(canvas, padding=12)
        outer_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _update_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_outer_width(event: tk.Event) -> None:
            required_width = outer.winfo_reqwidth()
            canvas.itemconfigure(outer_window, width=max(event.width, required_width))

        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        outer.bind("<Configure>", _update_scroll_region)
        canvas.bind("<Configure>", _sync_outer_width)
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        title = ttk.Label(outer, text="Retirement Withdrawal Planner", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", pady=(0, 10))

        people_frame = ttk.LabelFrame(outer, text="People")
        people_frame.pack(fill=tk.X, pady=(0, 8))

        self._build_people_section(people_frame)

        accounts_frame = ttk.LabelFrame(outer, text="Accounts")
        accounts_frame.pack(fill=tk.X, pady=(0, 8))
        self._build_accounts_section(accounts_frame)

        plan_frame = ttk.LabelFrame(outer, text="Plan Controls")
        plan_frame.pack(fill=tk.X, pady=(0, 8))
        self._build_plan_section(plan_frame)

        results_frame = ttk.LabelFrame(outer, text="Projection Results")
        results_frame.pack(fill=tk.BOTH, expand=True)
        self.results_text = tk.Text(results_frame, height=18, wrap="none")
        self.results_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _build_people_section(self, frame: ttk.LabelFrame) -> None:
        ttk.Label(frame, text="Primary Name").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_name_var, width=16).grid(row=1, column=0, padx=6, pady=4)
        ttk.Label(frame, text="Primary Birth (YYYY-MM-DD)").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_birth_var, width=16).grid(row=1, column=1, padx=6, pady=4)
        ttk.Label(frame, text="Primary Target Retirement Age").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_ret_age_var, width=8).grid(row=1, column=2, padx=6, pady=4)
        ttk.Label(frame, text="Primary SS Start Age (62/67/70)").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_ss_age_var, width=8).grid(row=1, column=3, padx=6, pady=4)
        ttk.Label(frame, text="Primary SS Monthly").grid(row=0, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_ss_monthly_var, width=10).grid(row=1, column=4, padx=6, pady=4)
        ttk.Label(frame, text="Primary Annual Salary").grid(row=0, column=5, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.primary_salary_var, width=12).grid(row=1, column=5, padx=6, pady=4)

        ttk.Checkbutton(frame, text="Primary Has Pension", variable=self.primary_has_pension_var).grid(
            row=2, column=1, sticky="w", padx=6, pady=(8, 4)
        )
        ttk.Label(frame, text="Primary Pension Start Age").grid(row=2, column=2, sticky="w", padx=6, pady=(8, 4))
        self.primary_pension_age_entry = ttk.Entry(frame, textvariable=self.primary_pension_age_var, width=8)
        self.primary_pension_age_entry.grid(row=2, column=3, padx=6, pady=(8, 4), sticky="w")
        ttk.Label(frame, text="Primary Pension Monthly").grid(row=2, column=4, sticky="w", padx=6, pady=(8, 4))
        self.primary_pension_monthly_entry = ttk.Entry(frame, textvariable=self.primary_pension_monthly_var, width=10)
        self.primary_pension_monthly_entry.grid(row=2, column=5, padx=6, pady=(8, 4), sticky="w")

        ttk.Checkbutton(frame, text="Include Spouse", variable=self.include_spouse_var).grid(
            row=2, column=0, sticky="w", padx=6, pady=(8, 4)
        )

        ttk.Label(frame, text="Spouse Name").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_name_var, width=16).grid(row=4, column=0, padx=6, pady=4)
        ttk.Label(frame, text="Spouse Birth (YYYY-MM-DD)").grid(row=3, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_birth_var, width=16).grid(row=4, column=1, padx=6, pady=4)
        ttk.Label(frame, text="Spouse Target Retirement Age").grid(row=3, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_ret_age_var, width=8).grid(row=4, column=2, padx=6, pady=4)
        ttk.Label(frame, text="Spouse SS Start Age (62/67/70)").grid(row=3, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_ss_age_var, width=8).grid(row=4, column=3, padx=6, pady=4)
        ttk.Label(frame, text="Spouse SS Monthly").grid(row=3, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_ss_monthly_var, width=10).grid(row=4, column=4, padx=6, pady=4)
        ttk.Label(frame, text="Spouse Annual Salary").grid(row=3, column=5, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.spouse_salary_var, width=12).grid(row=4, column=5, padx=6, pady=4)

        ttk.Checkbutton(frame, text="Spouse Has Pension", variable=self.spouse_has_pension_var).grid(
            row=5, column=1, sticky="w", padx=6, pady=(8, 4)
        )
        ttk.Label(frame, text="Spouse Pension Start Age").grid(row=5, column=2, sticky="w", padx=6, pady=(8, 4))
        self.spouse_pension_age_entry = ttk.Entry(frame, textvariable=self.spouse_pension_age_var, width=8)
        self.spouse_pension_age_entry.grid(row=5, column=3, padx=6, pady=(8, 4), sticky="w")
        ttk.Label(frame, text="Spouse Pension Monthly").grid(row=5, column=4, sticky="w", padx=6, pady=(8, 4))
        self.spouse_pension_monthly_entry = ttk.Entry(frame, textvariable=self.spouse_pension_monthly_var, width=10)
        self.spouse_pension_monthly_entry.grid(row=5, column=5, padx=6, pady=(8, 4), sticky="w")
        self._toggle_pension_inputs()

    def _toggle_pension_inputs(self) -> None:
        self.primary_pension_age_entry.configure(state="normal" if self.primary_has_pension_var.get() else "disabled")
        self.primary_pension_monthly_entry.configure(
            state="normal" if self.primary_has_pension_var.get() else "disabled"
        )
        spouse_enabled = self.include_spouse_var.get() and self.spouse_has_pension_var.get()
        self.spouse_pension_age_entry.configure(state="normal" if spouse_enabled else "disabled")
        self.spouse_pension_monthly_entry.configure(state="normal" if spouse_enabled else "disabled")

    def _build_accounts_section(self, frame: ttk.LabelFrame) -> None:
        ttk.Label(frame, text="Owner").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.account_owner_var,
            values=["Primary", "Spouse"],
            state="readonly",
            width=10,
        ).grid(row=1, column=0, padx=6, pady=4)

        ttk.Label(frame, text="Account Name").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_name_var, width=20).grid(row=1, column=1, padx=6, pady=4)

        ttk.Label(frame, text="Account Type").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.account_type_var,
            values=list(LABEL_TO_ACCOUNT_TYPE.keys()),
            state="readonly",
            width=26,
        ).grid(row=1, column=2, padx=6, pady=4)

        ttk.Label(frame, text="Balance").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_balance_var, width=12).grid(row=1, column=3, padx=6, pady=4)

        ttk.Label(frame, text="Stock Mix % (rest bonds)").grid(row=0, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_stock_mix_var, width=14).grid(row=1, column=4, padx=6, pady=4)

        ttk.Label(frame, text="Cost Basis (Taxable only)").grid(row=0, column=5, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_cost_basis_var, width=14).grid(row=1, column=5, padx=6, pady=4)

        ttk.Label(frame, text="Capital Gains Amt (Taxable only)").grid(row=0, column=6, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_capital_gains_var, width=16).grid(row=1, column=6, padx=6, pady=4)

        ttk.Button(frame, text="Add Account", command=self.add_account).grid(row=1, column=7, padx=6, pady=4)
        ttk.Button(frame, text="Update Selected", command=self.update_selected_account).grid(row=1, column=8, padx=6, pady=4)
        ttk.Button(frame, text="Remove Selected", command=self.remove_selected_account).grid(row=1, column=9, padx=6, pady=4)

        self.accounts_tree = ttk.Treeview(
            frame,
            columns=("owner", "name", "type", "balance", "stock_mix", "cost_basis", "capital_gains"),
            show="headings",
            height=7,
        )
        self.accounts_tree.grid(row=2, column=0, columnspan=10, sticky="ew", padx=6, pady=8)

        for col, text, width in [
            ("owner", "Owner", 90),
            ("name", "Name", 160),
            ("type", "Type", 220),
            ("balance", "Balance", 110),
            ("stock_mix", "Stock Mix %", 95),
            ("cost_basis", "Cost Basis", 110),
            ("capital_gains", "Cap Gains Amt", 120),
        ]:
            self.accounts_tree.heading(col, text=text)
            self.accounts_tree.column(col, width=width, anchor="w")

        self.accounts_tree.bind("<<TreeviewSelect>>", self.on_account_selected)

    def _build_plan_section(self, frame: ttk.LabelFrame) -> None:
        plan_canvas = tk.Canvas(frame, highlightthickness=0, height=190)
        plan_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=plan_canvas.xview)
        plan_canvas.configure(xscrollcommand=plan_scrollbar.set)
        plan_canvas.grid(row=0, column=0, sticky="ew")
        plan_scrollbar.grid(row=1, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        plan_content = ttk.Frame(plan_canvas)
        plan_window = plan_canvas.create_window((0, 0), window=plan_content, anchor="nw")

        def _sync_plan_scrollregion(_event: tk.Event | None = None) -> None:
            plan_canvas.configure(scrollregion=plan_canvas.bbox("all"))

        def _sync_plan_width(event: tk.Event) -> None:
            plan_canvas.itemconfigure(plan_window, height=max(event.height, plan_content.winfo_reqheight()))

        plan_content.bind("<Configure>", _sync_plan_scrollregion)
        plan_canvas.bind("<Configure>", _sync_plan_width)

        ttk.Radiobutton(plan_content, text="Flat annual withdrawal", variable=self.withdrawal_mode_var, value="flat").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Radiobutton(
            plan_content,
            text="Distribute across projection years",
            variable=self.withdrawal_mode_var,
            value="distribute_years",
        ).grid(row=1, column=0, sticky="w", padx=6, pady=4)

        ttk.Label(plan_content, text="Household Spending Target (annual)").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.withdrawal_value_var, width=14).grid(row=1, column=1, padx=6, pady=4)

        ttk.Label(plan_content, text="Inflation Rate % (annual)").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.inflation_rate_var, width=8).grid(row=1, column=2, padx=6, pady=4)

        ttk.Label(plan_content, text="Projection Years").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.projection_years_var, width=8).grid(row=1, column=3, padx=6, pady=4)

        ttk.Label(plan_content, text="Stock Shock Volatility %").grid(row=0, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.return_volatility_var, width=10).grid(row=1, column=4, padx=6, pady=4)

        ttk.Label(plan_content, text="Pessimistic Return Delta %").grid(row=0, column=5, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.pessimistic_bias_var, width=10).grid(row=1, column=5, padx=6, pady=4)

        ttk.Label(plan_content, text="Likely Return Delta %").grid(row=0, column=6, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.likely_bias_var, width=10).grid(row=1, column=6, padx=6, pady=4)

        ttk.Label(plan_content, text="Optimistic Return Delta %").grid(row=0, column=7, sticky="w", padx=6, pady=4)
        ttk.Entry(plan_content, textvariable=self.optimistic_bias_var, width=10).grid(row=1, column=7, padx=6, pady=4)

        ttk.Label(plan_content, text="Tax").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(plan_content, textvariable=self.tax_table_status_var).grid(row=2, column=1, columnspan=3, sticky="w", padx=6, pady=4)

        ttk.Label(plan_content, text="Cap Gains").grid(row=2, column=4, sticky="w", padx=6, pady=4)
        ttk.Label(plan_content, textvariable=self.cap_gains_table_status_var).grid(row=2, column=5, columnspan=2, sticky="w", padx=6, pady=4)

        ttk.Button(plan_content, text="Calculate Plan", command=self.calculate_plan).grid(row=3, column=0, padx=10, pady=4, sticky="w")

        ttk.Label(plan_content, text="Settings").grid(row=4, column=0, sticky="w", padx=6, pady=(8, 4))
        ttk.Button(plan_content, text="Import Settings", command=self.import_settings_json).grid(
            row=4, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Export Settings", command=self.export_settings_json).grid(
            row=4, column=2, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Export CSV", command=self.export_projection_csv).grid(
            row=4, column=3, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Export BI CSV", command=self.export_projection_power_bi_csv).grid(
            row=4, column=4, padx=6, pady=4, sticky="w"
        )

        ttk.Button(plan_content, text="Export Income Tax Table", command=self.export_income_tax_table_json).grid(
            row=5, column=0, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Refresh Income Tax Table", command=self.refresh_income_tax_table).grid(
            row=5, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Export Capital Gains Table", command=self.export_capital_gains_table_json).grid(
            row=5, column=2, padx=6, pady=4, sticky="w"
        )
        ttk.Button(plan_content, text="Refresh Capital Gains Table", command=self.refresh_capital_gains_table).grid(
            row=5, column=3, padx=6, pady=4, sticky="w"
        )

    @staticmethod
    def _to_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _collect_settings_snapshot(self) -> dict[str, object]:
        return {
            "settings_version": SETTINGS_VERSION,
            "people": {
                "primary": {
                    "name": self.primary_name_var.get(),
                    "birth_date": self.primary_birth_var.get(),
                    "target_retirement_age": self.primary_ret_age_var.get(),
                    "annual_salary": self.primary_salary_var.get(),
                    "social_security_start_age": self.primary_ss_age_var.get(),
                    "social_security_monthly": self.primary_ss_monthly_var.get(),
                    "has_pension": self.primary_has_pension_var.get(),
                    "pension_start_age": self.primary_pension_age_var.get(),
                    "pension_monthly": self.primary_pension_monthly_var.get(),
                },
                "include_spouse": self.include_spouse_var.get(),
                "spouse": {
                    "name": self.spouse_name_var.get(),
                    "birth_date": self.spouse_birth_var.get(),
                    "target_retirement_age": self.spouse_ret_age_var.get(),
                    "annual_salary": self.spouse_salary_var.get(),
                    "social_security_start_age": self.spouse_ss_age_var.get(),
                    "social_security_monthly": self.spouse_ss_monthly_var.get(),
                    "has_pension": self.spouse_has_pension_var.get(),
                    "pension_start_age": self.spouse_pension_age_var.get(),
                    "pension_monthly": self.spouse_pension_monthly_var.get(),
                },
            },
            "plan": {
                "withdrawal_mode": self.withdrawal_mode_var.get(),
                "withdrawal_value": self.withdrawal_value_var.get(),
                "inflation_rate_percent": self.inflation_rate_var.get(),
                "projection_years": self.projection_years_var.get(),
            },
            "scenario_returns": {
                "annual_volatility_percent": self.return_volatility_var.get(),
                "pessimistic_bias_percent": self.pessimistic_bias_var.get(),
                "likely_bias_percent": self.likely_bias_var.get(),
                "optimistic_bias_percent": self.optimistic_bias_var.get(),
            },
            "accounts": [
                {
                    "owner": account.owner,
                    "name": account.name,
                    "account_type": account.account_type.value,
                    "balance": account.balance,
                    "stock_mix": account.stock_mix,
                    "cost_basis": account.cost_basis,
                    "capital_gains_amount": account.capital_gains_amount,
                }
                for account in self.accounts
            ],
        }

    @staticmethod
    def _account_type_from_settings(value: object) -> AccountType:
        if isinstance(value, str):
            if value in LABEL_TO_ACCOUNT_TYPE:
                return LABEL_TO_ACCOUNT_TYPE[value]
            return AccountType(value)
        raise ValueError("Invalid account type in settings.")

    def _apply_settings_snapshot(self, payload: dict[str, object]) -> None:
        people = payload.get("people", {})
        if not isinstance(people, dict):
            raise ValueError("Invalid settings: people section is missing or invalid.")
        primary = people.get("primary", {})
        spouse = people.get("spouse", {})
        plan = payload.get("plan", {})
        scenario_returns = payload.get("scenario_returns", {})
        accounts_data = payload.get("accounts", [])

        if not isinstance(primary, dict) or not isinstance(spouse, dict):
            raise ValueError("Invalid settings: person details are invalid.")
        if not isinstance(plan, dict):
            raise ValueError("Invalid settings: plan section is invalid.")
        if not isinstance(scenario_returns, dict):
            raise ValueError("Invalid settings: scenario return settings are invalid.")
        if not isinstance(accounts_data, list):
            raise ValueError("Invalid settings: accounts must be an array.")

        self.primary_name_var.set(str(primary.get("name", self.primary_name_var.get())))
        self.primary_birth_var.set(str(primary.get("birth_date", self.primary_birth_var.get())))
        self.primary_ret_age_var.set(str(primary.get("target_retirement_age", self.primary_ret_age_var.get())))
        self.primary_salary_var.set(str(primary.get("annual_salary", self.primary_salary_var.get())))
        self.primary_ss_age_var.set(str(primary.get("social_security_start_age", self.primary_ss_age_var.get())))
        self.primary_ss_monthly_var.set(str(primary.get("social_security_monthly", self.primary_ss_monthly_var.get())))
        self.primary_has_pension_var.set(self._to_bool(primary.get("has_pension", self.primary_has_pension_var.get())))
        self.primary_pension_age_var.set(str(primary.get("pension_start_age", self.primary_pension_age_var.get())))
        self.primary_pension_monthly_var.set(str(primary.get("pension_monthly", self.primary_pension_monthly_var.get())))

        self.include_spouse_var.set(self._to_bool(people.get("include_spouse", self.include_spouse_var.get())))
        self.spouse_name_var.set(str(spouse.get("name", self.spouse_name_var.get())))
        self.spouse_birth_var.set(str(spouse.get("birth_date", self.spouse_birth_var.get())))
        self.spouse_ret_age_var.set(str(spouse.get("target_retirement_age", self.spouse_ret_age_var.get())))
        self.spouse_salary_var.set(str(spouse.get("annual_salary", self.spouse_salary_var.get())))
        self.spouse_ss_age_var.set(str(spouse.get("social_security_start_age", self.spouse_ss_age_var.get())))
        self.spouse_ss_monthly_var.set(str(spouse.get("social_security_monthly", self.spouse_ss_monthly_var.get())))
        self.spouse_has_pension_var.set(self._to_bool(spouse.get("has_pension", self.spouse_has_pension_var.get())))
        self.spouse_pension_age_var.set(str(spouse.get("pension_start_age", self.spouse_pension_age_var.get())))
        self.spouse_pension_monthly_var.set(str(spouse.get("pension_monthly", self.spouse_pension_monthly_var.get())))
        self._toggle_pension_inputs()

        self.withdrawal_mode_var.set(str(plan.get("withdrawal_mode", self.withdrawal_mode_var.get())))
        self.withdrawal_value_var.set(str(plan.get("withdrawal_value", self.withdrawal_value_var.get())))
        self.inflation_rate_var.set(str(plan.get("inflation_rate_percent", self.inflation_rate_var.get())))
        self.projection_years_var.set(str(plan.get("projection_years", self.projection_years_var.get())))
        self.return_volatility_var.set(
            str(scenario_returns.get("annual_volatility_percent", self.return_volatility_var.get()))
        )
        self.pessimistic_bias_var.set(
            str(scenario_returns.get("pessimistic_bias_percent", self.pessimistic_bias_var.get()))
        )
        self.likely_bias_var.set(str(scenario_returns.get("likely_bias_percent", self.likely_bias_var.get())))
        self.optimistic_bias_var.set(
            str(scenario_returns.get("optimistic_bias_percent", self.optimistic_bias_var.get()))
        )

        loaded_accounts: list[Account] = []
        for item in accounts_data:
            if not isinstance(item, dict):
                continue
            account_type = self._account_type_from_settings(
                item.get("account_type", AccountType.K401_NON_ROTH.value)
            )
            stock_mix_value = item.get("stock_mix")
            if stock_mix_value is None:
                # Backward compatibility for legacy settings files.
                legacy_asset = str(item.get("asset_class", "stocks")).strip().lower()
                if legacy_asset == "bonds":
                    stock_mix = 0.0
                elif legacy_asset == "cash":
                    stock_mix = 0.0
                else:
                    stock_mix = 1.0
            else:
                stock_mix = float(stock_mix_value)
                if stock_mix > 1.0:
                    stock_mix /= 100.0
            loaded_accounts.append(
                Account(
                    owner=str(item.get("owner", "Primary")),
                    name=str(item.get("name", ACCOUNT_TYPE_LABELS[account_type])),
                    account_type=account_type,
                    balance=float(item.get("balance", 0.0)),
                    stock_mix=stock_mix,
                    cost_basis=float(item.get("cost_basis", 0.0)),
                    capital_gains_amount=float(
                        item.get(
                            "capital_gains_amount",
                            max(0.0, float(item.get("balance", 0.0)) - float(item.get("cost_basis", 0.0))),
                        )
                    ),
                )
            )

        self.accounts = loaded_accounts
        self.last_projection_by_scenario = {}
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, "Settings imported. Click Calculate Plan to regenerate projection.\n")
        self._refresh_accounts_tree()

    def export_settings_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Export Retirement Settings",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump(self._collect_settings_snapshot(), settings_file, indent=2)
            messagebox.showinfo("Export complete", f"Settings exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def import_settings_json(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            title="Import Retirement Settings",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as settings_file:
                payload = json.load(settings_file)
            if not isinstance(payload, dict):
                raise ValueError("Settings file must contain a JSON object.")
            self._apply_settings_snapshot(payload)
            messagebox.showinfo("Import complete", f"Settings imported from:\n{path}")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_income_tax_table_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Export Income Tax Table",
        )
        if not path:
            return

        try:
            save_tax_table_config(self.tax_table_config, Path(path))
            messagebox.showinfo("Export complete", f"Income tax table exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def export_capital_gains_table_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Export Capital Gains Tax Table",
        )
        if not path:
            return

        try:
            save_capital_gains_config(self.capital_gains_table_config, Path(path))
            messagebox.showinfo("Export complete", f"Capital gains tax table exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def _filing_status(self) -> str:
        return FILING_STATUS_MARRIED_JOINT if self.include_spouse_var.get() else FILING_STATUS_SINGLE

    def _update_tax_table_status(self) -> None:
        tax_year = self.tax_table_config.get("tax_year", "unknown")
        source_url = self.tax_table_config.get("source_url", "IRS").split("/")[-1] if self.tax_table_config.get("source_url") else "IRS"
        filing_status = self._filing_status()
        status_label = "MFJ" if filing_status == FILING_STATUS_MARRIED_JOINT else "S"
        self.tax_table_status_var.set(f"{status_label} {tax_year}")

    def _capital_gains_status_filing(self) -> str:
        return CG_FILING_STATUS_MARRIED_JOINT if self.include_spouse_var.get() else CG_FILING_STATUS_SINGLE

    def _update_capital_gains_table_status(self) -> None:
        tax_year = self.capital_gains_table_config.get("tax_year", "unknown")
        source_url = self.capital_gains_table_config.get("source_url", "IRS").split("/")[-1] if self.capital_gains_table_config.get("source_url") else "IRS"
        filing_status = self._capital_gains_status_filing()
        status_label = "MFJ" if filing_status == CG_FILING_STATUS_MARRIED_JOINT else "S"
        self.cap_gains_table_status_var.set(f"{status_label} {tax_year}")

    def refresh_income_tax_table(self) -> None:
        try:
            self.tax_table_config = refresh_tax_table_config(CONFIG_PATH)
            self._update_tax_table_status()
            messagebox.showinfo("Income tax table refreshed", "IRS income tax table refreshed from source.")
        except Exception as exc:
            messagebox.showerror("Income tax refresh failed", str(exc))

    def refresh_capital_gains_table(self) -> None:
        try:
            self.capital_gains_table_config = refresh_capital_gains_config(CG_CONFIG_PATH)
            self._update_capital_gains_table_status()
            messagebox.showinfo("Capital gains table refreshed", "IRS capital gains table refreshed from source.")
        except Exception as exc:
            messagebox.showerror("Capital gains refresh failed", str(exc))

    def add_account(self) -> None:
        try:
            account_label = self.account_type_var.get()
            account_type = LABEL_TO_ACCOUNT_TYPE[account_label]
            balance = float(self.account_balance_var.get())
            stock_mix = float(self.account_stock_mix_var.get()) / 100.0
            cost_basis = float(self.account_cost_basis_var.get())
            capital_gains_amount = float(self.account_capital_gains_var.get())

            if account_type != AccountType.TAXABLE_INVESTMENT:
                cost_basis = 0.0
                capital_gains_amount = 0.0

            account = Account(
                owner=self.account_owner_var.get(),
                name=self.account_name_var.get().strip() or account_label,
                account_type=account_type,
                balance=balance,
                stock_mix=stock_mix,
                cost_basis=cost_basis,
                capital_gains_amount=capital_gains_amount,
            )
            self.accounts.append(account)
            self._refresh_accounts_tree()
        except Exception as exc:
            messagebox.showerror("Invalid account", str(exc))

    def remove_selected_account(self) -> None:
        selected = self.accounts_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if 0 <= index < len(self.accounts):
            self.accounts.pop(index)
            self._refresh_accounts_tree()

    def on_account_selected(self, _event: tk.Event | None = None) -> None:
        selected = self.accounts_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if not (0 <= index < len(self.accounts)):
            return

        account = self.accounts[index]
        self.account_owner_var.set(account.owner)
        self.account_name_var.set(account.name)
        self.account_type_var.set(ACCOUNT_TYPE_LABELS[account.account_type])
        self.account_balance_var.set(f"{account.balance:.2f}")
        self.account_stock_mix_var.set(f"{account.stock_mix * 100:.2f}")
        self.account_cost_basis_var.set(f"{account.cost_basis:.2f}")
        self.account_capital_gains_var.set(f"{account.capital_gains_amount:.2f}")

    def update_selected_account(self) -> None:
        selected = self.accounts_tree.selection()
        if not selected:
            messagebox.showinfo("No selection", "Select an account row to update.")
            return

        index = int(selected[0])
        if not (0 <= index < len(self.accounts)):
            messagebox.showerror("Update failed", "Selected account is out of range.")
            return

        try:
            account_label = self.account_type_var.get()
            account_type = LABEL_TO_ACCOUNT_TYPE[account_label]
            balance = float(self.account_balance_var.get())
            stock_mix = float(self.account_stock_mix_var.get()) / 100.0
            cost_basis = float(self.account_cost_basis_var.get())
            capital_gains_amount = float(self.account_capital_gains_var.get())

            if account_type != AccountType.TAXABLE_INVESTMENT:
                cost_basis = 0.0
                capital_gains_amount = 0.0

            self.accounts[index] = Account(
                owner=self.account_owner_var.get(),
                name=self.account_name_var.get().strip() or account_label,
                account_type=account_type,
                balance=balance,
                stock_mix=stock_mix,
                cost_basis=cost_basis,
                capital_gains_amount=capital_gains_amount,
            )
            self._refresh_accounts_tree()
            self.accounts_tree.selection_set(str(index))
            self.accounts_tree.focus(str(index))
        except Exception as exc:
            messagebox.showerror("Invalid account", str(exc))

    def _refresh_accounts_tree(self) -> None:
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)

        for index, account in enumerate(self.accounts):
            self.accounts_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    account.owner,
                    account.name,
                    ACCOUNT_TYPE_LABELS[account.account_type],
                    f"{account.balance:,.2f}",
                    f"{account.stock_mix * 100:.2f}",
                    f"{account.cost_basis:,.2f}",
                    f"{account.capital_gains_amount:,.2f}",
                ),
            )

    def _owner_age_by_name(self) -> dict[str, int]:
        today = date.today()
        primary_birth = _parse_date(self.primary_birth_var.get())
        ages = {"Primary": age_on_date(primary_birth, today)}
        if self.include_spouse_var.get():
            spouse_birth = _parse_date(self.spouse_birth_var.get())
            ages["Spouse"] = age_on_date(spouse_birth, today)
        return ages

    def _owner_ss_config(self) -> dict[str, tuple[int | None, float]]:
        primary_start = int(self.primary_ss_age_var.get()) if self.primary_ss_age_var.get().strip() else None
        ss = {
            "Primary": (primary_start, float(self.primary_ss_monthly_var.get())),
        }
        if self.include_spouse_var.get():
            spouse_start = int(self.spouse_ss_age_var.get()) if self.spouse_ss_age_var.get().strip() else None
            ss["Spouse"] = (spouse_start, float(self.spouse_ss_monthly_var.get()))
        return ss

    def _owner_pension_config(self) -> dict[str, tuple[int | None, float]]:
        pension: dict[str, tuple[int | None, float]] = {}
        if self.primary_has_pension_var.get():
            primary_start = int(self.primary_pension_age_var.get()) if self.primary_pension_age_var.get().strip() else None
            pension["Primary"] = (primary_start, float(self.primary_pension_monthly_var.get()))
        if self.include_spouse_var.get() and self.spouse_has_pension_var.get():
            spouse_start = int(self.spouse_pension_age_var.get()) if self.spouse_pension_age_var.get().strip() else None
            pension["Spouse"] = (spouse_start, float(self.spouse_pension_monthly_var.get()))
        return pension

    def _owner_retirement_age_config(self) -> dict[str, int]:
        retirement_ages = {"Primary": int(self.primary_ret_age_var.get())}
        if self.include_spouse_var.get():
            retirement_ages["Spouse"] = int(self.spouse_ret_age_var.get())
        return retirement_ages

    def _owner_salary_config(self) -> dict[str, float]:
        salaries = {"Primary": float(self.primary_salary_var.get())}
        if self.include_spouse_var.get():
            salaries["Spouse"] = float(self.spouse_salary_var.get())
        return salaries

    def calculate_plan(self) -> None:
        try:
            if not self.accounts:
                raise ValueError("Add at least one account before calculating.")

            years = int(self.projection_years_var.get())
            withdrawal_value = float(self.withdrawal_value_var.get())
            inflation_rate = float(self.inflation_rate_var.get()) / 100.0
            annual_return_volatility = float(self.return_volatility_var.get()) / 100.0
            pessimistic_bias = float(self.pessimistic_bias_var.get()) / 100.0
            likely_bias = float(self.likely_bias_var.get()) / 100.0
            optimistic_bias = float(self.optimistic_bias_var.get()) / 100.0
            tax_brackets = tax_brackets_for_status(self.tax_table_config, self._filing_status())
            capital_gains_brackets = capital_gains_brackets_for_status(
                self.capital_gains_table_config,
                self._capital_gains_status_filing(),
            )

            owner_age_by_name = self._owner_age_by_name()
            owner_retirement_age_by_name = self._owner_retirement_age_config()
            owner_salary_by_name = self._owner_salary_config()
            owner_ss_by_name = self._owner_ss_config()
            owner_pension_by_name = self._owner_pension_config()
            projection_by_scenario = simulate_retirement_scenarios(
                accounts=self.accounts,
                years=years,
                annual_withdrawal_value=withdrawal_value,
                withdrawal_mode=self.withdrawal_mode_var.get(),
                owner_age_by_name=owner_age_by_name,
                owner_retirement_age_by_name=owner_retirement_age_by_name,
                owner_salary_by_name=owner_salary_by_name,
                owner_ss_by_name=owner_ss_by_name,
                owner_pension_by_name=owner_pension_by_name,
                tax_brackets=tax_brackets,
                capital_gains_brackets=capital_gains_brackets,
                annual_return_volatility=annual_return_volatility,
                inflation_rate=inflation_rate,
                pessimistic_return_bias=pessimistic_bias,
                likely_return_bias=likely_bias,
                optimistic_return_bias=optimistic_bias,
            )
            self.last_projection_by_scenario = projection_by_scenario
            self._render_projection_scenarios(projection_by_scenario)
        except Exception as exc:
            messagebox.showerror("Calculation error", str(exc))

    def _render_projection_scenarios(self, projection_by_scenario: dict[str, list[YearProjection]]) -> None:
        self.results_text.delete("1.0", tk.END)
        if not projection_by_scenario:
            self.results_text.insert(tk.END, "No projection results generated.\n")
            return

        self.results_text.insert(
            tk.END,
            "Scenario Summary | Final Balance | Avg Return % | Total Taxes | First Year Shortfall\n",
        )
        self.results_text.insert(tk.END, "-" * 108 + "\n")

        for scenario_name, projection in projection_by_scenario.items():
            if not projection:
                self.results_text.insert(
                    tk.END,
                    f"{scenario_name:<16} | {'N/A':>13} | {'N/A':>11} | {'N/A':>11} | {'N/A':>20}\n",
                )
                continue
            total_taxes = sum(item.taxes for item in projection)
            average_return_rate = sum(item.annual_return_rate for item in projection) / len(projection)
            shortfall_year = next((item.calendar_year for item in projection if item.shortfall > 0), None)
            shortfall_label = "None" if shortfall_year is None else str(shortfall_year)
            self.results_text.insert(
                tk.END,
                f"{scenario_name:<16} | {projection[-1].ending_balance:>13,.2f} | {average_return_rate * 100:>11,.2f} | {total_taxes:>11,.2f} | {shortfall_label:>20}\n",
            )

        self.results_text.insert(tk.END, "\n")

        for scenario_name, projection in projection_by_scenario.items():
            self._render_projection(scenario_name, projection)
            self.results_text.insert(tk.END, "\n")

    @staticmethod
    def _funding_summary_values(item: YearProjection) -> tuple[float, float, float, float, float, float]:
        net_by_source_type: dict[str, float] = {}
        for source in item.income_sources:
            net_by_source_type[source.source_type] = net_by_source_type.get(source.source_type, 0.0) + source.net_amount

        net_job = round(net_by_source_type.get("job_income", 0.0), 2)
        net_pension = round(net_by_source_type.get("pension_income", 0.0), 2)
        net_social_security = round(net_by_source_type.get("social_security_income", 0.0), 2)
        net_withdrawals = round(net_by_source_type.get("account_withdrawal", 0.0), 2)
        total_net_available = round(net_job + net_pension + net_social_security + net_withdrawals, 2)
        net_surplus_shortfall = round(total_net_available - item.desired_net_spending, 2)
        return (
            net_job,
            net_pension,
            net_social_security,
            net_withdrawals,
            total_net_available,
            net_surplus_shortfall,
        )

    def _render_account_balance_graph(self, projection: list[YearProjection]) -> None:
        account_keys: set[str] = set()
        for year in projection:
            account_keys.update(year.account_end_balances.keys())

        if not account_keys:
            self.results_text.insert(tk.END, "\nAccount Balance Graph: no account balance points available.\n")
            return

        self.results_text.insert(tk.END, "\nAccount Balance Graph (compact sparkline by account)\n")
        years_axis = " ".join(str(year.calendar_year) for year in projection)
        self.results_text.insert(tk.END, f"Years: {years_axis}\n")

        max_balance = max(
            (balance for year in projection for balance in year.account_end_balances.values()),
            default=0.0,
        )
        spark_chars = " .:-=+*#%@"
        if max_balance <= 0:
            self.results_text.insert(tk.END, "All balances are 0.00 across years.\n")
            return

        self.results_text.insert(
            tk.END,
            "Scale: lowest -> highest (normalized within scenario): ' ' . : - = + * # % @\n",
        )

        for account_key in sorted(account_keys):
            points: list[str] = []
            first_balance = projection[0].account_end_balances.get(account_key, 0.0)
            last_balance = projection[-1].account_end_balances.get(account_key, 0.0)
            for year in projection:
                balance = year.account_end_balances.get(account_key, 0.0)
                ratio = balance / max_balance
                idx = int(round(ratio * (len(spark_chars) - 1)))
                idx = max(0, min(len(spark_chars) - 1, idx))
                points.append(spark_chars[idx])
            sparkline = "".join(points)
            self.results_text.insert(
                tk.END,
                f"{account_key} | {sparkline} | start {first_balance:,.2f} -> end {last_balance:,.2f}\n",
            )

    def _render_projection(self, scenario_name: str, projection: list[YearProjection]) -> None:
        self.results_text.insert(tk.END, f"=== {scenario_name} Scenario ===\n")
        if not projection:
            self.results_text.insert(tk.END, "No projection results generated for this scenario.\n")
            return

        account_type_headers = " | ".join(
            [ACCOUNT_TYPE_LABELS[account_type] for account_type in ACCOUNT_TYPE_EXPORT_COLUMNS]
        )
        self.results_text.insert(
            tk.END,
            "Year | Calendar Year | User Age | Spouse Age | Withdrawn | Salary | SS Income | Pension | Ordinary | "
            "Taxable SS | Cap Gains | Taxes | Eff Tax % | Net Income | Net Target | Gross Wd | Net Wd | Begin Balance | End Balance | Shortfall | Return % | Gain/Loss | Invest Income | Market Adj % | "
            f"{account_type_headers}\n",
        )
        self.results_text.insert(tk.END, "-" * 420 + "\n")

        total_taxes = 0.0
        for item in projection:
            total_taxes += item.taxes
            (
                net_job,
                net_pension,
                net_social_security,
                net_withdrawals,
                total_net_available,
                net_delta,
            ) = self._funding_summary_values(item)
            net_delta_label = "Surplus" if net_delta >= 0 else "Shortfall"

            account_type_values = " | ".join(
                [
                    f"{item.withdrawal_by_account_type.get(account_type.value, 0.0):,.2f}"
                    for account_type in ACCOUNT_TYPE_EXPORT_COLUMNS
                ]
            )
            self.results_text.insert(
                tk.END,
                f"{item.year_index:>4} | "
                f"{item.calendar_year:>13} | "
                f"{item.user_age:>8} | "
                f"{(item.spouse_age if item.spouse_age is not None else 'N/A'):>10} | "
                f"{item.withdrawn_total:>10,.2f} | "
                f"{item.salary_income:>8,.2f} | "
                f"{item.social_security_income:>9,.2f} | "
                f"{item.pension_income:>7,.2f} | "
                f"{item.ordinary_income:>8,.2f} | "
                f"{item.taxable_social_security:>10,.2f} | "
                f"{item.capital_gains:>9,.2f} | "
                f"{item.taxes:>7,.2f} | "
                f"{item.effective_tax_rate * 100:>8,.2f} | "
                f"{item.net_income:>10,.2f} | "
                f"{item.desired_net_spending:>10,.2f} | "
                f"{item.gross_withdrawn_total:>8,.2f} | "
                f"{item.net_withdrawn_total:>6,.2f} | "
                f"{item.beginning_balance:>13,.2f} | "
                f"{item.ending_balance:>11,.2f} | "
                f"{item.shortfall:>8,.2f} | "
                f"{item.annual_return_rate * 100:>8,.2f} | "
                f"{item.annual_gain_loss:>9,.2f} | "
                f"{item.investment_income_earned:>13,.2f} | "
                f"{item.market_return_adjustment * 100:>11,.2f} | "
                f"{account_type_values}\n"
            )
            self.results_text.insert(
                tk.END,
                "      [Funding Summary] "
                f"Net Target {item.desired_net_spending:,.2f} | "
                f"Job Net {net_job:,.2f} | "
                f"Pension Net {net_pension:,.2f} | "
                f"SS Net {net_social_security:,.2f} | "
                f"Withdrawal Net {net_withdrawals:,.2f} | "
                f"Total Net {total_net_available:,.2f} | "
                f"{net_delta_label} {abs(net_delta):,.2f}\n",
            )
            if item.withdrawal_sources:
                for source in item.withdrawal_sources:
                    self.results_text.insert(
                        tk.END,
                        "      -> "
                        f"{source.owner} | {source.account_name} | {source.account_type} | "
                        f"{source.tax_treatment} | gross {source.amount:,.2f} | taxable {source.taxable_amount:,.2f} | "
                        f"cap gains {source.realized_capital_gains:,.2f} | "
                        f"tax {source.allocated_tax:,.2f} | net {source.net_amount:,.2f}\n",
                    )
            if item.income_sources:
                for source in item.income_sources:
                    self.results_text.insert(
                        tk.END,
                        "      => "
                        f"{source.source_type} | {source.owner} | {source.label} | "
                        f"gross {source.gross_amount:,.2f} | taxable {source.taxable_amount:,.2f} | "
                        f"tax {source.allocated_tax:,.2f} | net {source.net_amount:,.2f}\n",
                    )

        self.results_text.insert(tk.END, "\n")
        self.results_text.insert(tk.END, f"Total Taxes: {total_taxes:,.2f}\n")
        self.results_text.insert(tk.END, f"Final Balance: {projection[-1].ending_balance:,.2f}\n")
        if projection:
            self.results_text.insert(tk.END, f"Effective Tax Rate: {projection[-1].effective_tax_rate * 100:,.2f}%\n")
            self._render_account_balance_graph(projection)

    def export_projection_csv(self) -> None:
        if not self.last_projection_by_scenario:
            messagebox.showinfo("No results", "Run Calculate Plan before exporting CSV.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Export Projection CSV",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=FLAT_EXPORT_COLUMNS)
                writer.writeheader()
                writer.writerows(flatten_projection_rows(self.last_projection_by_scenario))
            messagebox.showinfo("Export complete", f"CSV exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def export_projection_power_bi_csv(self) -> None:
        if not self.last_projection_by_scenario:
            messagebox.showinfo("No results", "Run Calculate Plan before exporting BI CSV.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Export Projection BI CSV",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=POWER_BI_EXPORT_COLUMNS)
                writer.writeheader()
                writer.writerows(flatten_projection_metric_rows(self.last_projection_by_scenario))
            messagebox.showinfo("Export complete", f"BI CSV exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))


def run_app() -> None:
    root = tk.Tk()
    RetirementApp(root)
    root.mainloop()
