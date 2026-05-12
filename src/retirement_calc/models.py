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


class AssetClass(str, Enum):
    STOCKS = "stocks"
    BONDS = "bonds"
    CASH = "cash"


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

ASSET_CLASS_DEFAULT_RETURNS: dict[AssetClass, float] = {
    AssetClass.STOCKS: 0.08,
    AssetClass.BONDS: 0.04,
    AssetClass.CASH: 0.02,
}


@dataclass
class Account:
    owner: str
    name: str
    account_type: AccountType
    balance: float
    asset_class: AssetClass = AssetClass.STOCKS
    annual_return_rate: float = 0.05
    cost_basis: float = 0.0

    def __post_init__(self) -> None:
        if self.balance < 0:
            raise ValueError("balance must be >= 0")
        if not -1.0 <= self.annual_return_rate <= 2.0:
            raise ValueError("annual_return_rate must be between -1.0 and 2.0")
        if self.account_type != AccountType.TAXABLE_INVESTMENT and self.cost_basis != 0:
            raise ValueError("cost_basis is only used for taxable investment accounts")


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
