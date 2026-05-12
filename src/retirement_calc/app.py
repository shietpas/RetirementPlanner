from __future__ import annotations

import csv
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from .calculations import YearProjection, age_on_date, simulate_retirement
from .models import ASSET_CLASS_DEFAULT_RETURNS, Account, AccountType, AssetClass


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
ASSET_CLASS_LABELS = {
    AssetClass.STOCKS: "Stocks",
    AssetClass.BONDS: "Bonds",
    AssetClass.CASH: "Cash",
}
LABEL_TO_ASSET_CLASS = {label: asset_class for asset_class, label in ASSET_CLASS_LABELS.items()}


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
        self.primary_ss_age_var = tk.StringVar(value="67")
        self.primary_ss_monthly_var = tk.StringVar(value="2500")

        self.include_spouse_var = tk.BooleanVar(value=False)
        self.spouse_name_var = tk.StringVar(value="Spouse")
        self.spouse_birth_var = tk.StringVar(value="1972-01-01")
        self.spouse_ret_age_var = tk.StringVar(value="65")
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
        self.income_tax_rate_var = tk.StringVar(value="22")
        self.cap_gains_tax_rate_var = tk.StringVar(value="15")
        self.last_projection: list[YearProjection] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.title("RetirementCalc")
        self.root.geometry("1180x760")

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

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
        ttk.Button(frame, text="Remove Selected", command=self.remove_selected_account).grid(row=1, column=8, padx=6, pady=4)

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
        self.accounts_tree.grid(row=3, column=0, columnspan=9, sticky="ew", padx=6, pady=8)

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

    def _build_plan_section(self, frame: ttk.LabelFrame) -> None:
        ttk.Radiobutton(frame, text="Flat annual withdrawal", variable=self.withdrawal_mode_var, value="flat").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Radiobutton(frame, text="Distribute across projection years", variable=self.withdrawal_mode_var, value="distribute_years").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )

        ttk.Label(frame, text="Withdrawal Value (amount if flat)").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.withdrawal_value_var, width=14).grid(row=1, column=1, padx=6, pady=4)

        ttk.Label(frame, text="Projection Years").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.projection_years_var, width=8).grid(row=1, column=2, padx=6, pady=4)

        ttk.Label(frame, text="Income Tax %").grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.income_tax_rate_var, width=8).grid(row=1, column=3, padx=6, pady=4)

        ttk.Label(frame, text="Capital Gains Tax %").grid(row=0, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(frame, textvariable=self.cap_gains_tax_rate_var, width=8).grid(row=1, column=4, padx=6, pady=4)

        ttk.Button(frame, text="Calculate Plan", command=self.calculate_plan).grid(row=1, column=5, padx=10, pady=4)
        ttk.Button(frame, text="Export CSV", command=self.export_projection_csv).grid(row=1, column=6, padx=10, pady=4)

    def _asset_class_default_rate(self, asset_class: AssetClass) -> float:
        if asset_class == AssetClass.STOCKS:
            return float(self.default_stock_return_var.get()) / 100.0
        if asset_class == AssetClass.BONDS:
            return float(self.default_bond_return_var.get()) / 100.0
        return float(self.default_cash_return_var.get()) / 100.0

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

    def calculate_plan(self) -> None:
        try:
            if not self.accounts:
                raise ValueError("Add at least one account before calculating.")

            years = int(self.projection_years_var.get())
            withdrawal_value = float(self.withdrawal_value_var.get())
            income_tax_rate = float(self.income_tax_rate_var.get()) / 100.0
            cap_gains_tax_rate = float(self.cap_gains_tax_rate_var.get()) / 100.0

            owner_age_by_name = self._owner_age_by_name()
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
                owner_ss_by_name=owner_ss_by_name,
                income_tax_rate=income_tax_rate,
                capital_gains_tax_rate=cap_gains_tax_rate,
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

        self.results_text.insert(
            tk.END,
            "Year | Withdrawn | SS Income | Ordinary | Taxable SS | Cap Gains | Taxes | Net Income | End Balance | Shortfall\n",
        )
        self.results_text.insert(tk.END, "-" * 122 + "\n")

        total_taxes = 0.0
        for item in projection:
            total_taxes += item.taxes
            self.results_text.insert(
                tk.END,
                f"{item.year_index:>4} | "
                f"{item.withdrawn_total:>10,.2f} | "
                f"{item.social_security_income:>9,.2f} | "
                f"{item.ordinary_income:>8,.2f} | "
                f"{item.taxable_social_security:>10,.2f} | "
                f"{item.capital_gains:>9,.2f} | "
                f"{item.taxes:>7,.2f} | "
                f"{item.net_income:>10,.2f} | "
                f"{item.ending_balance:>11,.2f} | "
                f"{item.shortfall:>8,.2f}\n"
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
                        "withdrawn_total",
                        "social_security_income",
                        "ordinary_income",
                        "taxable_social_security",
                        "capital_gains",
                        "taxes",
                        "net_income",
                        "ending_balance",
                        "shortfall",
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
                            f"{year.withdrawn_total:.2f}",
                            f"{year.social_security_income:.2f}",
                            f"{year.ordinary_income:.2f}",
                            f"{year.taxable_social_security:.2f}",
                            f"{year.capital_gains:.2f}",
                            f"{year.taxes:.2f}",
                            f"{year.net_income:.2f}",
                            f"{year.ending_balance:.2f}",
                            f"{year.shortfall:.2f}",
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
