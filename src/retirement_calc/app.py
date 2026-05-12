from __future__ import annotations

import csv
import json
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .calculations import YearProjection, age_on_date, simulate_retirement
from .capital_gains_tax_tables import (
    FILING_STATUS_MARRIED_JOINT as CG_FILING_STATUS_MARRIED_JOINT,
    FILING_STATUS_SINGLE as CG_FILING_STATUS_SINGLE,
    CONFIG_PATH as CG_CONFIG_PATH,
    capital_gains_brackets_for_status,
    load_capital_gains_config,
    refresh_capital_gains_config,
    save_capital_gains_config,
)
from .models import ASSET_CLASS_DEFAULT_RETURNS, Account, AccountType, AssetClass
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
ASSET_CLASS_LABELS = {
    AssetClass.STOCKS: "Stocks",
    AssetClass.BONDS: "Bonds",
    AssetClass.CASH: "Cash",
}
LABEL_TO_ASSET_CLASS = {label: asset_class for asset_class, label in ASSET_CLASS_LABELS.items()}
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

        self.include_spouse_var = tk.BooleanVar(value=False)
        self.spouse_name_var = tk.StringVar(value="Spouse")
        self.spouse_birth_var = tk.StringVar(value="1972-01-01")
        self.spouse_ret_age_var = tk.StringVar(value="65")
        self.spouse_salary_var = tk.StringVar(value="90000")
        self.spouse_ss_age_var = tk.StringVar(value="67")
        self.spouse_ss_monthly_var = tk.StringVar(value="2000")

        self.account_owner_var = tk.StringVar(value="Primary")
        self.account_name_var = tk.StringVar(value="")
        self.account_type_var = tk.StringVar(value=ACCOUNT_TYPE_LABELS[AccountType.K401_NON_ROTH])
        self.account_asset_class_var = tk.StringVar(value=ASSET_CLASS_LABELS[AssetClass.STOCKS])
        self.account_balance_var = tk.StringVar(value="0")
        self.account_return_var = tk.StringVar(value="5")
        self.account_cost_basis_var = tk.StringVar(value="0")
        self.use_default_returns_var = tk.BooleanVar(value=True)
        self.default_stock_return_var = tk.StringVar(value=str(int(ASSET_CLASS_DEFAULT_RETURNS[AssetClass.STOCKS] * 100)))
        self.default_bond_return_var = tk.StringVar(value=str(int(ASSET_CLASS_DEFAULT_RETURNS[AssetClass.BONDS] * 100)))
        self.default_cash_return_var = tk.StringVar(value=str(int(ASSET_CLASS_DEFAULT_RETURNS[AssetClass.CASH] * 100)))

        self.withdrawal_mode_var = tk.StringVar(value="flat")
        self.withdrawal_value_var = tk.StringVar(value="60000")
        self.projection_years_var = tk.StringVar(value="30")
        self.tax_table_status_var = tk.StringVar(value="")
        self.cap_gains_table_status_var = tk.StringVar(value="")
        self.last_projection: list[YearProjection] = []
        self.tax_table_config = load_tax_table_config()
        self.capital_gains_table_config = load_capital_gains_config()
        self.include_spouse_var.trace_add("write", lambda *_: self._update_tax_table_status())
        self.include_spouse_var.trace_add("write", lambda *_: self._update_capital_gains_table_status())

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

        ttk.Label(frame, text="Asset Class").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.account_asset_class_var,
            values=list(LABEL_TO_ASSET_CLASS.keys()),
            state="readonly",
            width=10,
        ).grid(row=1, column=3, padx=6, pady=4)

        ttk.Label(frame, text="Balance").grid(row=0, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_balance_var, width=12).grid(row=1, column=4, padx=6, pady=4)

        ttk.Label(frame, text="Annual Return %").grid(row=0, column=5, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_return_var, width=10).grid(row=1, column=5, padx=6, pady=4)

        ttk.Label(frame, text="Cost Basis (Taxable only)").grid(row=0, column=6, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.account_cost_basis_var, width=14).grid(row=1, column=6, padx=6, pady=4)

        ttk.Button(frame, text="Add Account", command=self.add_account).grid(row=1, column=7, padx=6, pady=4)
        ttk.Button(frame, text="Update Selected", command=self.update_selected_account).grid(row=1, column=8, padx=6, pady=4)
        ttk.Button(frame, text="Remove Selected", command=self.remove_selected_account).grid(row=1, column=9, padx=6, pady=4)

        ttk.Checkbutton(
            frame,
            text="Use default return profile",
            variable=self.use_default_returns_var,
        ).grid(row=2, column=0, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(frame, text="Stocks %").grid(row=2, column=1, sticky="e", padx=4)
        ttk.Entry(frame, textvariable=self.default_stock_return_var, width=6).grid(row=2, column=2, sticky="w")
        ttk.Label(frame, text="Bonds %").grid(row=2, column=3, sticky="e", padx=4)
        ttk.Entry(frame, textvariable=self.default_bond_return_var, width=6).grid(row=2, column=4, sticky="w")
        ttk.Label(frame, text="Cash %").grid(row=2, column=5, sticky="e", padx=4)
        ttk.Entry(frame, textvariable=self.default_cash_return_var, width=6).grid(row=2, column=6, sticky="w")

        self.accounts_tree = ttk.Treeview(
            frame,
            columns=("owner", "name", "type", "asset_class", "balance", "return", "cost_basis"),
            show="headings",
            height=7,
        )
        self.accounts_tree.grid(row=3, column=0, columnspan=10, sticky="ew", padx=6, pady=8)

        for col, text, width in [
            ("owner", "Owner", 90),
            ("name", "Name", 160),
            ("type", "Type", 220),
            ("asset_class", "Asset Class", 95),
            ("balance", "Balance", 110),
            ("return", "Return %", 90),
            ("cost_basis", "Cost Basis", 110),
        ]:
            self.accounts_tree.heading(col, text=text)
            self.accounts_tree.column(col, width=width, anchor="w")

        self.accounts_tree.bind("<<TreeviewSelect>>", self.on_account_selected)

    def _build_plan_section(self, frame: ttk.LabelFrame) -> None:
        ttk.Radiobutton(frame, text="Flat annual withdrawal", variable=self.withdrawal_mode_var, value="flat").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Radiobutton(frame, text="Distribute across projection years", variable=self.withdrawal_mode_var, value="distribute_years").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )

        ttk.Label(frame, text="Household Spending Target (annual)").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.withdrawal_value_var, width=14).grid(row=1, column=1, padx=6, pady=4)

        ttk.Label(frame, text="Projection Years").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.projection_years_var, width=8).grid(row=1, column=2, padx=6, pady=4)

        ttk.Label(frame, text="Tax Table").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Label(frame, textvariable=self.tax_table_status_var).grid(row=1, column=3, columnspan=2, sticky="w", padx=6, pady=4)

        ttk.Label(frame, text="Capital Gains Table").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(frame, textvariable=self.cap_gains_table_status_var).grid(row=2, column=1, columnspan=4, sticky="w", padx=6, pady=4)

        ttk.Button(frame, text="Calculate Plan", command=self.calculate_plan).grid(row=1, column=5, padx=10, pady=4)

        ttk.Label(frame, text="Settings").grid(row=3, column=0, sticky="w", padx=6, pady=(8, 4))
        ttk.Button(frame, text="Import Settings", command=self.import_settings_json).grid(
            row=3, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Button(frame, text="Export Settings", command=self.export_settings_json).grid(
            row=3, column=2, padx=6, pady=4, sticky="w"
        )
        ttk.Button(frame, text="Export CSV", command=self.export_projection_csv).grid(
            row=3, column=3, padx=6, pady=4, sticky="w"
        )

        ttk.Button(frame, text="Export Income Tax Table", command=self.export_income_tax_table_json).grid(
            row=4, column=0, padx=6, pady=4, sticky="w"
        )
        ttk.Button(frame, text="Refresh Income Tax Table", command=self.refresh_income_tax_table).grid(
            row=4, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Button(frame, text="Export Capital Gains Table", command=self.export_capital_gains_table_json).grid(
            row=4, column=2, padx=6, pady=4, sticky="w"
        )
        ttk.Button(frame, text="Refresh Capital Gains Table", command=self.refresh_capital_gains_table).grid(
            row=4, column=3, padx=6, pady=4, sticky="w"
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
                },
                "include_spouse": self.include_spouse_var.get(),
                "spouse": {
                    "name": self.spouse_name_var.get(),
                    "birth_date": self.spouse_birth_var.get(),
                    "target_retirement_age": self.spouse_ret_age_var.get(),
                    "annual_salary": self.spouse_salary_var.get(),
                    "social_security_start_age": self.spouse_ss_age_var.get(),
                    "social_security_monthly": self.spouse_ss_monthly_var.get(),
                },
            },
            "plan": {
                "withdrawal_mode": self.withdrawal_mode_var.get(),
                "withdrawal_value": self.withdrawal_value_var.get(),
                "projection_years": self.projection_years_var.get(),
            },
            "return_profile": {
                "use_default_returns": self.use_default_returns_var.get(),
                "stocks_return_percent": self.default_stock_return_var.get(),
                "bonds_return_percent": self.default_bond_return_var.get(),
                "cash_return_percent": self.default_cash_return_var.get(),
            },
            "accounts": [
                {
                    "owner": account.owner,
                    "name": account.name,
                    "account_type": account.account_type.value,
                    "asset_class": account.asset_class.value,
                    "balance": account.balance,
                    "annual_return_rate": account.annual_return_rate,
                    "cost_basis": account.cost_basis,
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

    @staticmethod
    def _asset_class_from_settings(value: object) -> AssetClass:
        if isinstance(value, str):
            if value in LABEL_TO_ASSET_CLASS:
                return LABEL_TO_ASSET_CLASS[value]
            return AssetClass(value)
        raise ValueError("Invalid asset class in settings.")

    def _apply_settings_snapshot(self, payload: dict[str, object]) -> None:
        people = payload.get("people", {})
        if not isinstance(people, dict):
            raise ValueError("Invalid settings: people section is missing or invalid.")
        primary = people.get("primary", {})
        spouse = people.get("spouse", {})
        plan = payload.get("plan", {})
        return_profile = payload.get("return_profile", {})
        accounts_data = payload.get("accounts", [])

        if not isinstance(primary, dict) or not isinstance(spouse, dict):
            raise ValueError("Invalid settings: person details are invalid.")
        if not isinstance(plan, dict) or not isinstance(return_profile, dict):
            raise ValueError("Invalid settings: plan or return profile is invalid.")
        if not isinstance(accounts_data, list):
            raise ValueError("Invalid settings: accounts must be an array.")

        self.primary_name_var.set(str(primary.get("name", self.primary_name_var.get())))
        self.primary_birth_var.set(str(primary.get("birth_date", self.primary_birth_var.get())))
        self.primary_ret_age_var.set(str(primary.get("target_retirement_age", self.primary_ret_age_var.get())))
        self.primary_salary_var.set(str(primary.get("annual_salary", self.primary_salary_var.get())))
        self.primary_ss_age_var.set(str(primary.get("social_security_start_age", self.primary_ss_age_var.get())))
        self.primary_ss_monthly_var.set(str(primary.get("social_security_monthly", self.primary_ss_monthly_var.get())))

        self.include_spouse_var.set(self._to_bool(people.get("include_spouse", self.include_spouse_var.get())))
        self.spouse_name_var.set(str(spouse.get("name", self.spouse_name_var.get())))
        self.spouse_birth_var.set(str(spouse.get("birth_date", self.spouse_birth_var.get())))
        self.spouse_ret_age_var.set(str(spouse.get("target_retirement_age", self.spouse_ret_age_var.get())))
        self.spouse_salary_var.set(str(spouse.get("annual_salary", self.spouse_salary_var.get())))
        self.spouse_ss_age_var.set(str(spouse.get("social_security_start_age", self.spouse_ss_age_var.get())))
        self.spouse_ss_monthly_var.set(str(spouse.get("social_security_monthly", self.spouse_ss_monthly_var.get())))

        self.withdrawal_mode_var.set(str(plan.get("withdrawal_mode", self.withdrawal_mode_var.get())))
        self.withdrawal_value_var.set(str(plan.get("withdrawal_value", self.withdrawal_value_var.get())))
        self.projection_years_var.set(str(plan.get("projection_years", self.projection_years_var.get())))

        self.use_default_returns_var.set(
            self._to_bool(return_profile.get("use_default_returns", self.use_default_returns_var.get()))
        )
        self.default_stock_return_var.set(
            str(return_profile.get("stocks_return_percent", self.default_stock_return_var.get()))
        )
        self.default_bond_return_var.set(
            str(return_profile.get("bonds_return_percent", self.default_bond_return_var.get()))
        )
        self.default_cash_return_var.set(
            str(return_profile.get("cash_return_percent", self.default_cash_return_var.get()))
        )

        loaded_accounts: list[Account] = []
        for item in accounts_data:
            if not isinstance(item, dict):
                continue
            account_type = self._account_type_from_settings(
                item.get("account_type", AccountType.K401_NON_ROTH.value)
            )
            asset_class = self._asset_class_from_settings(item.get("asset_class", AssetClass.STOCKS.value))
            loaded_accounts.append(
                Account(
                    owner=str(item.get("owner", "Primary")),
                    name=str(item.get("name", ACCOUNT_TYPE_LABELS[account_type])),
                    account_type=account_type,
                    balance=float(item.get("balance", 0.0)),
                    asset_class=asset_class,
                    annual_return_rate=float(item.get("annual_return_rate", 0.05)),
                    cost_basis=float(item.get("cost_basis", 0.0)),
                )
            )

        self.accounts = loaded_accounts
        self.last_projection = []
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

    def _asset_class_default_rate(self, asset_class: AssetClass) -> float:
        if asset_class == AssetClass.STOCKS:
            return float(self.default_stock_return_var.get()) / 100.0
        if asset_class == AssetClass.BONDS:
            return float(self.default_bond_return_var.get()) / 100.0
        return float(self.default_cash_return_var.get()) / 100.0

    def _filing_status(self) -> str:
        return FILING_STATUS_MARRIED_JOINT if self.include_spouse_var.get() else FILING_STATUS_SINGLE

    def _update_tax_table_status(self) -> None:
        tax_year = self.tax_table_config.get("tax_year", "unknown")
        source_url = self.tax_table_config.get("source_url", "IRS")
        filing_status = self._filing_status()
        status_label = "Married Filing Jointly" if filing_status == FILING_STATUS_MARRIED_JOINT else "Single"
        self.tax_table_status_var.set(f"{status_label} | IRS {tax_year} | {source_url}")

    def _capital_gains_status_filing(self) -> str:
        return CG_FILING_STATUS_MARRIED_JOINT if self.include_spouse_var.get() else CG_FILING_STATUS_SINGLE

    def _update_capital_gains_table_status(self) -> None:
        tax_year = self.capital_gains_table_config.get("tax_year", "unknown")
        source_url = self.capital_gains_table_config.get("source_url", "IRS")
        filing_status = self._capital_gains_status_filing()
        status_label = "Married Filing Jointly" if filing_status == CG_FILING_STATUS_MARRIED_JOINT else "Single"
        self.cap_gains_table_status_var.set(f"{status_label} | IRS {tax_year} | {source_url}")

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
            asset_class = LABEL_TO_ASSET_CLASS[self.account_asset_class_var.get()]
            balance = float(self.account_balance_var.get())
            if self.use_default_returns_var.get():
                annual_return_rate = self._asset_class_default_rate(asset_class)
            else:
                annual_return_rate = float(self.account_return_var.get()) / 100.0
            cost_basis = float(self.account_cost_basis_var.get())

            if account_type != AccountType.TAXABLE_INVESTMENT:
                cost_basis = 0.0

            account = Account(
                owner=self.account_owner_var.get(),
                name=self.account_name_var.get().strip() or account_label,
                account_type=account_type,
                balance=balance,
                asset_class=asset_class,
                annual_return_rate=annual_return_rate,
                cost_basis=cost_basis,
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
        self.account_asset_class_var.set(ASSET_CLASS_LABELS[account.asset_class])
        self.account_balance_var.set(f"{account.balance:.2f}")
        self.account_return_var.set(f"{account.annual_return_rate * 100:.2f}")
        self.account_cost_basis_var.set(f"{account.cost_basis:.2f}")

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
            asset_class = LABEL_TO_ASSET_CLASS[self.account_asset_class_var.get()]
            balance = float(self.account_balance_var.get())
            if self.use_default_returns_var.get():
                annual_return_rate = self._asset_class_default_rate(asset_class)
            else:
                annual_return_rate = float(self.account_return_var.get()) / 100.0
            cost_basis = float(self.account_cost_basis_var.get())

            if account_type != AccountType.TAXABLE_INVESTMENT:
                cost_basis = 0.0

            self.accounts[index] = Account(
                owner=self.account_owner_var.get(),
                name=self.account_name_var.get().strip() or account_label,
                account_type=account_type,
                balance=balance,
                asset_class=asset_class,
                annual_return_rate=annual_return_rate,
                cost_basis=cost_basis,
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
                    ASSET_CLASS_LABELS[account.asset_class],
                    f"{account.balance:,.2f}",
                    f"{account.annual_return_rate * 100:.2f}",
                    f"{account.cost_basis:,.2f}",
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
            tax_brackets = tax_brackets_for_status(self.tax_table_config, self._filing_status())
            capital_gains_brackets = capital_gains_brackets_for_status(
                self.capital_gains_table_config,
                self._capital_gains_status_filing(),
            )

            owner_age_by_name = self._owner_age_by_name()
            owner_retirement_age_by_name = self._owner_retirement_age_config()
            owner_salary_by_name = self._owner_salary_config()
            owner_ss_by_name = self._owner_ss_config()
            projection = simulate_retirement(
                accounts=[
                    Account(
                        owner=acc.owner,
                        name=acc.name,
                        account_type=acc.account_type,
                        balance=acc.balance,
                        asset_class=acc.asset_class,
                        annual_return_rate=acc.annual_return_rate,
                        cost_basis=acc.cost_basis,
                    )
                    for acc in self.accounts
                ],
                years=years,
                annual_withdrawal_value=withdrawal_value,
                withdrawal_mode=self.withdrawal_mode_var.get(),
                owner_age_by_name=owner_age_by_name,
                owner_retirement_age_by_name=owner_retirement_age_by_name,
                owner_salary_by_name=owner_salary_by_name,
                owner_ss_by_name=owner_ss_by_name,
                tax_brackets=tax_brackets,
                capital_gains_brackets=capital_gains_brackets,
            )
            self.last_projection = projection
            self._render_projection(projection)
        except Exception as exc:
            messagebox.showerror("Calculation error", str(exc))

    def _render_projection(self, projection: list[YearProjection]) -> None:
        self.results_text.delete("1.0", tk.END)
        if not projection:
            self.results_text.insert(tk.END, "No projection results generated.\n")
            return

        account_type_headers = " | ".join(
            [ACCOUNT_TYPE_LABELS[account_type] for account_type in ACCOUNT_TYPE_EXPORT_COLUMNS]
        )
        self.results_text.insert(
            tk.END,
            "Year | Calendar Year | User Age | Spouse Age | Withdrawn | Salary | SS Income | Ordinary | "
            "Taxable SS | Cap Gains | Taxes | Net Income | End Balance | Shortfall | "
            f"{account_type_headers}\n",
        )
        self.results_text.insert(tk.END, "-" * 260 + "\n")

        total_taxes = 0.0
        for item in projection:
            total_taxes += item.taxes
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
                f"{item.ordinary_income:>8,.2f} | "
                f"{item.taxable_social_security:>10,.2f} | "
                f"{item.capital_gains:>9,.2f} | "
                f"{item.taxes:>7,.2f} | "
                f"{item.net_income:>10,.2f} | "
                f"{item.ending_balance:>11,.2f} | "
                f"{item.shortfall:>8,.2f} | "
                f"{account_type_values}\n"
            )
            if item.withdrawal_sources:
                for source in item.withdrawal_sources:
                    self.results_text.insert(
                        tk.END,
                        "      -> "
                        f"{source.owner} | {source.account_name} | {source.account_type} | "
                        f"{source.tax_treatment} | {source.amount:,.2f}\n",
                    )

        self.results_text.insert(tk.END, "\n")
        self.results_text.insert(tk.END, f"Total Taxes: {total_taxes:,.2f}\n")
        self.results_text.insert(tk.END, f"Final Balance: {projection[-1].ending_balance:,.2f}\n")

    def export_projection_csv(self) -> None:
        if not self.last_projection:
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
                writer = csv.writer(csv_file)
                writer.writerow(
                    [
                        "year",
                        "calendar_year",
                        "user_age",
                        "spouse_age",
                        "withdrawn_total",
                        "salary_income",
                        "social_security_income",
                        "ordinary_income",
                        "taxable_social_security",
                        "capital_gains",
                        "taxes",
                        "net_income",
                        "ending_balance",
                        "shortfall",
                        *[account_type.value for account_type in ACCOUNT_TYPE_EXPORT_COLUMNS],
                        "withdrawal_sources",
                    ]
                )
                for year in self.last_projection:
                    sources = "; ".join(
                        [
                            (
                                f"{source.owner}/{source.account_name}/"
                                f"{source.account_type}/{source.tax_treatment}/{source.amount:.2f}"
                            )
                            for source in year.withdrawal_sources
                        ]
                    )
                    writer.writerow(
                        [
                            year.year_index,
                            year.calendar_year,
                            year.user_age,
                            "" if year.spouse_age is None else year.spouse_age,
                            f"{year.withdrawn_total:.2f}",
                            f"{year.salary_income:.2f}",
                            f"{year.social_security_income:.2f}",
                            f"{year.ordinary_income:.2f}",
                            f"{year.taxable_social_security:.2f}",
                            f"{year.capital_gains:.2f}",
                            f"{year.taxes:.2f}",
                            f"{year.net_income:.2f}",
                            f"{year.ending_balance:.2f}",
                            f"{year.shortfall:.2f}",
                            *[
                                f"{year.withdrawal_by_account_type.get(account_type.value, 0.0):.2f}"
                                for account_type in ACCOUNT_TYPE_EXPORT_COLUMNS
                            ],
                            sources,
                        ]
                    )
            messagebox.showinfo("Export complete", f"CSV exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))


def run_app() -> None:
    root = tk.Tk()
    RetirementApp(root)
    root.mainloop()
