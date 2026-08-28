from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class AccountType(str, Enum):
    K401_NON_ROTH = "401k_non_roth"
    K401_ROTH = "401k_roth"
    B403_NON_ROTH = "403b_non_roth"
    B403_ROTH = "403b_roth"
    IRA_TRADITIONAL = "ira_traditional"
    IRA_ROTH = "ira_roth"
    TAXABLE_INVESTMENT = "taxable_investment"


class TaxTreatment(str, Enum):
    ORDINARY_INCOME = "ordinary_income"
    TAX_FREE = "tax_free"
    CAPITAL_GAINS = "capital_gains"


ACCOUNT_TAX_TREATMENT: dict[AccountType, TaxTreatment] = {
    AccountType.K401_NON_ROTH: TaxTreatment.ORDINARY_INCOME,
    AccountType.K401_ROTH: TaxTreatment.TAX_FREE,
    AccountType.B403_NON_ROTH: TaxTreatment.ORDINARY_INCOME,
    AccountType.B403_ROTH: TaxTreatment.TAX_FREE,
    AccountType.IRA_TRADITIONAL: TaxTreatment.ORDINARY_INCOME,
    AccountType.IRA_ROTH: TaxTreatment.TAX_FREE,
    AccountType.TAXABLE_INVESTMENT: TaxTreatment.CAPITAL_GAINS,
}

RMD_ELIGIBLE_TYPES: set[AccountType] = {
    AccountType.K401_NON_ROTH,
    AccountType.B403_NON_ROTH,
    AccountType.IRA_TRADITIONAL,
}

NON_ROTH_TYPES: set[AccountType] = {
    AccountType.K401_NON_ROTH,
    AccountType.B403_NON_ROTH,
    AccountType.IRA_TRADITIONAL,
}

ROTH_TYPES: set[AccountType] = {
    AccountType.K401_ROTH,
    AccountType.B403_ROTH,
    AccountType.IRA_ROTH,
}

@dataclass
class Account:
    owner: str
    name: str
    account_type: AccountType
    balance: float
    stock_mix: float = 0.60
    cost_basis: float = 0.0
    capital_gains_amount: float = 0.0

    def __post_init__(self) -> None:
        if self.balance < 0:
            raise ValueError("balance must be >= 0")
        if not 0.0 <= self.stock_mix <= 1.0:
            raise ValueError("stock_mix must be between 0.0 and 1.0")
        if self.cost_basis < 0:
            raise ValueError("cost_basis must be >= 0")
        if self.capital_gains_amount < 0:
            raise ValueError("capital_gains_amount must be >= 0")
        if self.capital_gains_amount > self.balance:
            raise ValueError("capital_gains_amount must be <= balance")
        if self.account_type != AccountType.TAXABLE_INVESTMENT and self.cost_basis != 0:
            raise ValueError("cost_basis is only used for taxable investment accounts")
        if self.account_type != AccountType.TAXABLE_INVESTMENT and self.capital_gains_amount != 0:
            raise ValueError("capital_gains_amount is only used for taxable investment accounts")
        if self.account_type == AccountType.TAXABLE_INVESTMENT and self.capital_gains_amount == 0.0:
            self.capital_gains_amount = max(0.0, round(self.balance - self.cost_basis, 2))


@dataclass
class Person:
    name: str
    birth_date: date
    target_retirement_age: int
    social_security_start_age: int | None = None
    social_security_monthly_amount: float = 0.0


@dataclass
class PlanInput:
    primary: Person
    spouse: Person | None
    accounts: list[Account]
    filing_status: str = "married"
