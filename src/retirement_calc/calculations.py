from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import random

from .models import (
    ACCOUNT_TAX_TREATMENT,
    NON_ROTH_TYPES,
    RMD_ELIGIBLE_TYPES,
    Account,
    AccountType,
    TaxTreatment,
)
from .tax_tables import calculate_progressive_tax
from .capital_gains_tax_tables import calculate_capital_gains_tax


@dataclass
class TaxBreakdown:
    ordinary_income: float
    capital_gains: float
    tax_free: float


@dataclass
class WithdrawalSource:
    owner: str
    account_name: str
    account_type: str
    amount: float
    tax_treatment: str


@dataclass
class YearProjection:
    year_index: int
    calendar_year: int
    user_age: int
    spouse_age: int | None
    withdrawn_total: float
    salary_income: float
    social_security_income: float
    ordinary_income: float
    taxable_social_security: float
    capital_gains: float
    taxes: float
    net_income: float
    ending_balance: float
    shortfall: float
    annual_return_rate: float = 0.0
    annual_gain_loss: float = 0.0
    market_return_adjustment: float = 0.0
    withdrawal_by_account_type: dict[str, float] = field(default_factory=dict)
    withdrawal_sources: list[WithdrawalSource] = field(default_factory=list)


RMD_UNIFORM_LIFETIME_FACTORS: dict[int, float] = {
    72: 27.4,
    73: 26.5,
    74: 25.5,
    75: 24.6,
    76: 23.7,
    77: 22.9,
    78: 22.0,
    79: 21.1,
    80: 20.2,
    81: 19.4,
    82: 18.5,
    83: 17.7,
    84: 16.8,
    85: 16.0,
    86: 15.2,
    87: 14.4,
    88: 13.7,
    89: 12.9,
    90: 12.2,
    91: 11.5,
    92: 10.8,
    93: 10.1,
    94: 9.5,
    95: 8.9,
    96: 8.4,
    97: 7.8,
    98: 7.3,
    99: 6.8,
    100: 6.4,
    101: 6.0,
    102: 5.6,
    103: 5.2,
    104: 4.9,
    105: 4.6,
    106: 4.3,
    107: 4.1,
    108: 3.9,
    109: 3.7,
    110: 3.5,
    111: 3.4,
    112: 3.3,
    113: 3.1,
    114: 3.0,
    115: 2.9,
    116: 2.8,
    117: 2.7,
    118: 2.5,
    119: 2.3,
    120: 2.0,
}


def apply_annual_return(balance: float, annual_return_rate: float) -> float:
    if balance < 0:
        raise ValueError("balance must be >= 0")
    return round(balance * (1.0 + annual_return_rate), 2)


def clamp_annual_return_rate(value: float) -> float:
    return max(-1.0, min(2.0, value))


def account_tax_treatment(account_type: AccountType) -> TaxTreatment:
    return ACCOUNT_TAX_TREATMENT[account_type]


def classify_withdrawals(withdrawals: list[tuple[Account, float]]) -> TaxBreakdown:
    ordinary_income = 0.0
    capital_gains = 0.0
    tax_free = 0.0

    for account, amount in withdrawals:
        if amount < 0:
            raise ValueError("withdrawal amount must be >= 0")

        treatment = account_tax_treatment(account.account_type)
        if treatment == TaxTreatment.ORDINARY_INCOME:
            ordinary_income += amount
        elif treatment == TaxTreatment.CAPITAL_GAINS:
            capital_gains += amount
        else:
            tax_free += amount

    return TaxBreakdown(
        ordinary_income=round(ordinary_income, 2),
        capital_gains=round(capital_gains, 2),
        tax_free=round(tax_free, 2),
    )


def apply_year_end_growth(accounts: list[Account]) -> list[Account]:
    grown_accounts: list[Account] = []
    for account in accounts:
        grown_accounts.append(
            Account(
                owner=account.owner,
                name=account.name,
                account_type=account.account_type,
                balance=apply_annual_return(account.balance, account.annual_return_rate),
                asset_class=account.asset_class,
                annual_return_rate=account.annual_return_rate,
                cost_basis=account.cost_basis,
            )
        )
    return grown_accounts


def age_on_date(birth_date: date, as_of: date) -> int:
    years = as_of.year - birth_date.year
    had_birthday = (as_of.month, as_of.day) >= (birth_date.month, birth_date.day)
    return years if had_birthday else years - 1


def calculate_rmd(balance: float, age: int, account_type: AccountType) -> float:
    if account_type not in RMD_ELIGIBLE_TYPES or age < 72:
        return 0.0
    factor = RMD_UNIFORM_LIFETIME_FACTORS.get(age, 2.0)
    return round(balance / factor, 2)


def _withdraw_from_account(account: Account, amount: float) -> float:
    if amount <= 0:
        return 0.0
    actual = min(account.balance, amount)
    account.balance = round(account.balance - actual, 2)
    return actual


def optimize_withdrawals(
    accounts: list[Account],
    owner_ages: dict[str, int],
    retired_owners: set[str],
    needed_withdrawal: float,
) -> tuple[list[tuple[Account, float]], float]:
    withdrawals: list[tuple[Account, float]] = []
    remaining_needed = max(0.0, needed_withdrawal)

    for account in accounts:
        if account.owner not in retired_owners:
            continue
        age = owner_ages.get(account.owner, 0)
        rmd_amount = calculate_rmd(account.balance, age, account.account_type)
        taken = _withdraw_from_account(account, rmd_amount)
        if taken > 0:
            withdrawals.append((account, taken))
            remaining_needed = max(0.0, remaining_needed - taken)

    def priority_key(account: Account) -> int:
        if account.account_type == AccountType.TAXABLE_INVESTMENT:
            return 0
        if account.account_type in NON_ROTH_TYPES:
            return 1
        return 2

    for account in sorted(accounts, key=priority_key):
        if account.owner not in retired_owners:
            continue
        if remaining_needed <= 0:
            break
        taken = _withdraw_from_account(account, remaining_needed)
        if taken > 0:
            withdrawals.append((account, taken))
            remaining_needed = max(0.0, remaining_needed - taken)

    return withdrawals, round(remaining_needed, 2)


def simulate_retirement(
    accounts: list[Account],
    years: int,
    annual_withdrawal_value: float,
    withdrawal_mode: str,
    owner_age_by_name: dict[str, int],
    owner_retirement_age_by_name: dict[str, int],
    owner_salary_by_name: dict[str, float],
    owner_ss_by_name: dict[str, tuple[int | None, float]],
    tax_brackets: list[dict[str, float | None]],
    capital_gains_brackets: list[dict[str, float | None]],
    annual_return_volatility: float = 0.0,
    scenario_return_bias: float = 0.0,
    random_seed: int | None = None,
) -> list[YearProjection]:
    projections: list[YearProjection] = []
    base_year = date.today().year
    account_type_keys = [account_type.value for account_type in AccountType]
    rng = random.Random(random_seed)

    for year_index in range(1, years + 1):
        total_remaining_before = sum(account.balance for account in accounts)
        if total_remaining_before <= 0:
            break

        market_return_adjustment = rng.gauss(0.0, annual_return_volatility) if annual_return_volatility > 0 else 0.0

        if withdrawal_mode == "distribute_years":
            years_left = years - year_index + 1
            target_withdrawal = round(total_remaining_before / years_left, 2)
        else:
            target_withdrawal = annual_withdrawal_value

        owner_ages = {owner: age + (year_index - 1) for owner, age in owner_age_by_name.items()}
        retired_owners: set[str] = set()
        salary_income = 0.0
        for owner, owner_age in owner_ages.items():
            retirement_age = owner_retirement_age_by_name.get(owner, 65)
            if owner_age > retirement_age:
                retired_owners.add(owner)
            else:
                salary_income += owner_salary_by_name.get(owner, 0.0)

        needed_withdrawal = max(0.0, round(target_withdrawal - salary_income, 2))

        social_security_income = 0.0
        for owner, (start_age, monthly_amount) in owner_ss_by_name.items():
            owner_age = owner_ages.get(owner, 0)
            if start_age is not None and owner_age >= start_age:
                social_security_income += monthly_amount * 12.0

        withdrawals, shortfall = optimize_withdrawals(accounts, owner_ages, retired_owners, needed_withdrawal)
        breakdown = classify_withdrawals(withdrawals)
        sources: list[WithdrawalSource] = []
        withdrawal_by_account_type = {key: 0.0 for key in account_type_keys}
        for account, amount in withdrawals:
            withdrawal_by_account_type[account.account_type.value] = round(
                withdrawal_by_account_type[account.account_type.value] + amount,
                2,
            )
            sources.append(
                WithdrawalSource(
                    owner=account.owner,
                    account_name=account.name,
                    account_type=account.account_type.value,
                    amount=round(amount, 2),
                    tax_treatment=account_tax_treatment(account.account_type).value,
                )
            )
        taxable_social_security = round(social_security_income * 0.85, 2)
        ordinary_taxable_income = round(salary_income + breakdown.ordinary_income + taxable_social_security, 2)
        ordinary_income_tax = calculate_progressive_tax(ordinary_taxable_income, tax_brackets)
        capital_gains_tax = calculate_capital_gains_tax(
            ordinary_taxable_income,
            breakdown.capital_gains,
            capital_gains_brackets,
        )
        taxes = round(ordinary_income_tax + capital_gains_tax, 2)
        withdrawn_total = round(sum(amount for _, amount in withdrawals), 2)
        net_income = round(withdrawn_total + salary_income + social_security_income - taxes, 2)

        pre_growth_balance_total = sum(account.balance for account in accounts)
        weighted_rate_numerator = 0.0
        for account in accounts:
            effective_rate = clamp_annual_return_rate(
                account.annual_return_rate + scenario_return_bias + market_return_adjustment
            )
            weighted_rate_numerator += account.balance * effective_rate
            account.balance = apply_annual_return(account.balance, effective_rate)

        ending_balance = round(sum(account.balance for account in accounts), 2)
        annual_return_rate = (
            round(weighted_rate_numerator / pre_growth_balance_total, 6)
            if pre_growth_balance_total > 0
            else 0.0
        )
        annual_gain_loss = round(ending_balance - pre_growth_balance_total, 2)
        projections.append(
            YearProjection(
                year_index=year_index,
                calendar_year=base_year + (year_index - 1),
                user_age=owner_ages.get("Primary", 0),
                spouse_age=owner_ages.get("Spouse"),
                withdrawn_total=withdrawn_total,
                salary_income=round(salary_income, 2),
                social_security_income=round(social_security_income, 2),
                ordinary_income=round(breakdown.ordinary_income, 2),
                taxable_social_security=taxable_social_security,
                capital_gains=round(breakdown.capital_gains, 2),
                taxes=taxes,
                net_income=net_income,
                ending_balance=ending_balance,
                shortfall=shortfall,
                annual_return_rate=annual_return_rate,
                annual_gain_loss=annual_gain_loss,
                market_return_adjustment=round(market_return_adjustment, 6),
                withdrawal_by_account_type=withdrawal_by_account_type,
                withdrawal_sources=sources,
            )
        )

    return projections


def simulate_retirement_scenarios(
    accounts: list[Account],
    years: int,
    annual_withdrawal_value: float,
    withdrawal_mode: str,
    owner_age_by_name: dict[str, int],
    owner_retirement_age_by_name: dict[str, int],
    owner_salary_by_name: dict[str, float],
    owner_ss_by_name: dict[str, tuple[int | None, float]],
    tax_brackets: list[dict[str, float | None]],
    capital_gains_brackets: list[dict[str, float | None]],
    annual_return_volatility: float,
    pessimistic_return_bias: float,
    likely_return_bias: float,
    optimistic_return_bias: float,
    random_seed: int | None = None,
) -> dict[str, list[YearProjection]]:
    scenario_biases = {
        "Pessimistic": pessimistic_return_bias,
        "Likely": likely_return_bias,
        "Optimistic": optimistic_return_bias,
    }
    projections_by_scenario: dict[str, list[YearProjection]] = {}
    seed_base = random_seed if random_seed is not None else random.randint(1, 1_000_000_000)

    for idx, (scenario_name, bias) in enumerate(scenario_biases.items()):
        scenario_accounts = [
            Account(
                owner=account.owner,
                name=account.name,
                account_type=account.account_type,
                balance=account.balance,
                asset_class=account.asset_class,
                annual_return_rate=account.annual_return_rate,
                cost_basis=account.cost_basis,
            )
            for account in accounts
        ]
        projections_by_scenario[scenario_name] = simulate_retirement(
            accounts=scenario_accounts,
            years=years,
            annual_withdrawal_value=annual_withdrawal_value,
            withdrawal_mode=withdrawal_mode,
            owner_age_by_name=owner_age_by_name,
            owner_retirement_age_by_name=owner_retirement_age_by_name,
            owner_salary_by_name=owner_salary_by_name,
            owner_ss_by_name=owner_ss_by_name,
            tax_brackets=tax_brackets,
            capital_gains_brackets=capital_gains_brackets,
            annual_return_volatility=annual_return_volatility,
            scenario_return_bias=bias,
            random_seed=seed_base + idx,
        )

    return projections_by_scenario
