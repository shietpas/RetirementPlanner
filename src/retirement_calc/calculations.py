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


# Long-run nominal approximations used as baseline market behavior.
# The stock baseline is intended to roughly match the S&P 500's long-run
# total-return behavior over the last 20 years.
SP500_REFERENCE_STOCK_RETURN_MEAN = 0.10
HISTORICAL_STOCK_RETURN_MEAN = SP500_REFERENCE_STOCK_RETURN_MEAN
HISTORICAL_BOND_RETURN_MEAN = 0.05


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
    net_amount: float
    allocated_tax: float
    tax_treatment: str


@dataclass
class IncomeSource:
    source_type: str
    owner: str
    label: str
    gross_amount: float
    taxable_amount: float
    allocated_tax: float
    net_amount: float


@dataclass
class YearProjection:
    year_index: int
    calendar_year: int
    user_age: int
    spouse_age: int | None
    desired_net_spending: float
    withdrawn_total: float
    gross_withdrawn_total: float
    net_withdrawn_total: float
    salary_income: float
    social_security_income: float
    pension_income: float
    ordinary_income: float
    taxable_social_security: float
    capital_gains: float
    taxes: float
    net_income: float
    beginning_balance: float
    ending_balance: float
    shortfall: float
    annual_return_rate: float = 0.0
    annual_gain_loss: float = 0.0
    investment_income_earned: float = 0.0
    market_return_adjustment: float = 0.0
    effective_tax_rate: float = 0.0
    withdrawal_by_account_type: dict[str, float] = field(default_factory=dict)
    withdrawal_sources: list[WithdrawalSource] = field(default_factory=list)
    income_sources: list[IncomeSource] = field(default_factory=list)
    account_end_balances: dict[str, float] = field(default_factory=dict)


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
        blended_return = (account.stock_mix * HISTORICAL_STOCK_RETURN_MEAN) + (
            (1.0 - account.stock_mix) * HISTORICAL_BOND_RETURN_MEAN
        )
        grown_accounts.append(
            Account(
                owner=account.owner,
                name=account.name,
                account_type=account.account_type,
                balance=apply_annual_return(account.balance, blended_return),
                stock_mix=account.stock_mix,
                cost_basis=account.cost_basis,
            )
        )
    return grown_accounts


def scenario_target_stock_return(scenario_return_bias: float) -> float:
    return clamp_annual_return_rate(HISTORICAL_STOCK_RETURN_MEAN + scenario_return_bias)


def market_asset_returns(scenario_return_bias: float, stock_shock: float) -> tuple[float, float]:
    stock_return = clamp_annual_return_rate(scenario_target_stock_return(scenario_return_bias) + stock_shock)
    # Bonds tend to be partially counter-cyclical to stock shocks.
    bond_return = clamp_annual_return_rate(
        HISTORICAL_BOND_RETURN_MEAN + (scenario_return_bias * 0.35) - (stock_shock * 0.40)
    )
    return stock_return, bond_return


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


def _clone_accounts(accounts: list[Account]) -> list[Account]:
    return [
        Account(
            owner=account.owner,
            name=account.name,
            account_type=account.account_type,
            balance=account.balance,
            stock_mix=account.stock_mix,
            cost_basis=account.cost_basis,
        )
        for account in accounts
    ]


def _round_money(value: float) -> float:
    return round(value, 2)


def _account_balance_key(account: Account) -> str:
    return f"{account.owner}/{account.name}/{account.account_type.value}"


def _allocate_taxes(
    salary_income: float,
    pension_income: float,
    social_security_income: float,
    breakdown: TaxBreakdown,
    ordinary_income_tax: float,
    capital_gains_tax: float,
) -> dict[str, float]:
    taxable_social_security = _round_money(social_security_income * 0.85)
    ordinary_components = {
        "salary": max(0.0, salary_income),
        "pension": max(0.0, pension_income),
        "taxable_social_security": max(0.0, taxable_social_security),
        "ordinary_withdrawals": max(0.0, breakdown.ordinary_income),
    }
    ordinary_total = sum(ordinary_components.values())

    allocations = {
        "salary": 0.0,
        "pension": 0.0,
        "social_security": 0.0,
        "ordinary_withdrawals": 0.0,
        "capital_gains_withdrawals": 0.0,
    }
    if ordinary_total > 0:
        allocations["salary"] = ordinary_income_tax * (ordinary_components["salary"] / ordinary_total)
        allocations["pension"] = ordinary_income_tax * (ordinary_components["pension"] / ordinary_total)
        allocations["social_security"] = ordinary_income_tax * (
            ordinary_components["taxable_social_security"] / ordinary_total
        )
        allocations["ordinary_withdrawals"] = ordinary_income_tax * (
            ordinary_components["ordinary_withdrawals"] / ordinary_total
        )

    if breakdown.capital_gains > 0:
        allocations["capital_gains_withdrawals"] = capital_gains_tax

    return {key: _round_money(value) for key, value in allocations.items()}


def _build_income_and_withdrawal_sources(
    salary_income: float,
    pension_income: float,
    social_security_income: float,
    withdrawals: list[tuple[Account, float]],
    tax_allocations: dict[str, float],
    breakdown: TaxBreakdown,
) -> tuple[list[IncomeSource], list[WithdrawalSource], float]:
    income_sources: list[IncomeSource] = []
    withdrawal_sources: list[WithdrawalSource] = []

    salary_tax = tax_allocations.get("salary", 0.0)
    pension_tax = tax_allocations.get("pension", 0.0)
    social_security_tax = tax_allocations.get("social_security", 0.0)
    ordinary_withdrawal_tax_total = tax_allocations.get("ordinary_withdrawals", 0.0)
    capital_gains_withdrawal_tax_total = tax_allocations.get("capital_gains_withdrawals", 0.0)

    if salary_income > 0:
        income_sources.append(
            IncomeSource(
                source_type="job_income",
                owner="Household",
                label="Job Income",
                gross_amount=_round_money(salary_income),
                taxable_amount=_round_money(salary_income),
                allocated_tax=salary_tax,
                net_amount=_round_money(salary_income - salary_tax),
            )
        )

    if pension_income > 0:
        income_sources.append(
            IncomeSource(
                source_type="pension_income",
                owner="Household",
                label="Pension Income",
                gross_amount=_round_money(pension_income),
                taxable_amount=_round_money(pension_income),
                allocated_tax=pension_tax,
                net_amount=_round_money(pension_income - pension_tax),
            )
        )

    if social_security_income > 0:
        taxable_social_security = _round_money(social_security_income * 0.85)
        income_sources.append(
            IncomeSource(
                source_type="social_security_income",
                owner="Household",
                label="Social Security Income",
                gross_amount=_round_money(social_security_income),
                taxable_amount=taxable_social_security,
                allocated_tax=social_security_tax,
                net_amount=_round_money(social_security_income - social_security_tax),
            )
        )

    ordinary_withdrawn_total = max(0.0, breakdown.ordinary_income)
    capital_gains_withdrawn_total = max(0.0, breakdown.capital_gains)
    net_withdrawn_total = 0.0

    for account, amount in withdrawals:
        treatment = account_tax_treatment(account.account_type)
        allocated_tax = 0.0
        if treatment == TaxTreatment.ORDINARY_INCOME and ordinary_withdrawn_total > 0:
            allocated_tax = ordinary_withdrawal_tax_total * (amount / ordinary_withdrawn_total)
        elif treatment == TaxTreatment.CAPITAL_GAINS and capital_gains_withdrawn_total > 0:
            allocated_tax = capital_gains_withdrawal_tax_total * (amount / capital_gains_withdrawn_total)

        allocated_tax = _round_money(allocated_tax)
        net_amount = _round_money(amount - allocated_tax)
        net_withdrawn_total += net_amount
        source = WithdrawalSource(
            owner=account.owner,
            account_name=account.name,
            account_type=account.account_type.value,
            amount=_round_money(amount),
            net_amount=net_amount,
            allocated_tax=allocated_tax,
            tax_treatment=treatment.value,
        )
        withdrawal_sources.append(source)
        income_sources.append(
            IncomeSource(
                source_type="account_withdrawal",
                owner=account.owner,
                label=account.name,
                gross_amount=source.amount,
                taxable_amount=(source.amount if treatment != TaxTreatment.TAX_FREE else 0.0),
                allocated_tax=source.allocated_tax,
                net_amount=source.net_amount,
            )
        )

    return income_sources, withdrawal_sources, _round_money(net_withdrawn_total)


def _evaluate_withdrawal_plan(
    accounts_snapshot: list[Account],
    owner_ages: dict[str, int],
    retired_owners: set[str],
    needed_withdrawal: float,
    salary_income: float,
    social_security_income: float,
    pension_income: float,
    tax_brackets: list[dict[str, float | None]],
    capital_gains_brackets: list[dict[str, float | None]],
) -> dict[str, object]:
    withdrawals, shortfall = optimize_withdrawals(
        accounts_snapshot,
        owner_ages,
        retired_owners,
        needed_withdrawal,
    )
    breakdown = classify_withdrawals(withdrawals)
    taxable_social_security = _round_money(social_security_income * 0.85)
    ordinary_taxable_income = _round_money(
        salary_income + pension_income + breakdown.ordinary_income + taxable_social_security,
    )
    ordinary_income_tax = calculate_progressive_tax(ordinary_taxable_income, tax_brackets)
    capital_gains_tax = calculate_capital_gains_tax(
        ordinary_taxable_income,
        breakdown.capital_gains,
        capital_gains_brackets,
    )
    taxes = _round_money(ordinary_income_tax + capital_gains_tax)
    withdrawn_total = _round_money(sum(amount for _, amount in withdrawals))
    net_income = _round_money(withdrawn_total + salary_income + social_security_income + pension_income - taxes)

    return {
        "withdrawals": withdrawals,
        "shortfall": shortfall,
        "breakdown": breakdown,
        "taxable_social_security": taxable_social_security,
        "ordinary_taxable_income": ordinary_taxable_income,
        "ordinary_income_tax": ordinary_income_tax,
        "capital_gains_tax": capital_gains_tax,
        "taxes": taxes,
        "withdrawn_total": withdrawn_total,
        "net_income": net_income,
    }


def simulate_retirement(
    accounts: list[Account],
    years: int,
    annual_withdrawal_value: float,
    withdrawal_mode: str,
    owner_age_by_name: dict[str, int],
    owner_retirement_age_by_name: dict[str, int],
    owner_salary_by_name: dict[str, float],
    owner_ss_by_name: dict[str, tuple[int | None, float]],
    owner_pension_by_name: dict[str, tuple[int | None, float]] | None,
    tax_brackets: list[dict[str, float | None]],
    capital_gains_brackets: list[dict[str, float | None]],
    annual_return_volatility: float = 0.0,
    inflation_rate: float = 0.025,
    scenario_return_bias: float = 0.0,
    random_seed: int | None = None,
) -> list[YearProjection]:
    projections: list[YearProjection] = []
    base_year = date.today().year
    account_type_keys = [account_type.value for account_type in AccountType]
    rng = random.Random(random_seed)
    pension_config = owner_pension_by_name or {}

    for year_index in range(1, years + 1):
        total_remaining_before = sum(account.balance for account in accounts)
        if total_remaining_before <= 0:
            break

        stock_shock = rng.gauss(0.0, annual_return_volatility) if annual_return_volatility > 0 else 0.0
        stock_return, bond_return = market_asset_returns(scenario_return_bias, stock_shock)

        inflation_multiplier = (1.0 + inflation_rate) ** (year_index - 1)
        if withdrawal_mode == "distribute_years":
            years_left = years - year_index + 1
            target_withdrawal = round((total_remaining_before / years_left) * inflation_multiplier, 2)
        else:
            target_withdrawal = round(annual_withdrawal_value * inflation_multiplier, 2)

        owner_ages = {owner: age + (year_index - 1) for owner, age in owner_age_by_name.items()}
        retired_owners: set[str] = set()
        
        # Calculate salary and pension per owner with mid-year transition handling
        # Rule: Salary stops at retirement_age. Pension cannot start before retirement_age.
        # If retirement_age == pension_start_age, assume mid-year transition (half salary, half pension).
        # Otherwise, there may be a gap between retirement and collecting benefits.
        salary_income_by_owner = {}
        pension_income_by_owner = {}
        
        for owner, owner_age in owner_ages.items():
            retirement_age = owner_retirement_age_by_name.get(owner, 65)
            pension_start_age, pension_monthly = pension_config.get(owner, (None, 0.0))
            
            if owner_age < retirement_age:
                # Not yet retired: full salary
                salary_income_by_owner[owner] = owner_salary_by_name.get(owner, 0.0)
            elif owner_age == retirement_age:
                if pension_start_age == retirement_age:
                    # Mid-year transition: half salary (first 6 months) + half pension (last 6 months)
                    salary_income_by_owner[owner] = owner_salary_by_name.get(owner, 0.0) * 0.5
                    pension_income_by_owner[owner] = pension_monthly * 12.0 * 0.5
                else:
                    # Retirement year but pension starts later: salary stops
                    salary_income_by_owner[owner] = 0.0
                retired_owners.add(owner)
            else:  # owner_age > retirement_age
                # Past retirement: salary stopped, check if pension has started
                retired_owners.add(owner)
                if pension_start_age is not None and owner_age >= pension_start_age:
                    pension_income_by_owner[owner] = pension_monthly * 12.0
                # Otherwise: gap with no income from this source

        pension_income = sum(pension_income_by_owner.values())
        salary_income = sum(salary_income_by_owner.values())

        social_security_income = 0.0
        for owner, (start_age, monthly_amount) in owner_ss_by_name.items():
            owner_age = owner_ages.get(owner, 0)
            if start_age is not None and owner_age >= start_age:
                social_security_income += monthly_amount * 12.0

        # Calculate beginning balance before withdrawals
        beginning_balance = round(sum(account.balance for account in accounts), 2)

        # Determine withdrawal need against desired net spending, not gross spending.
        # Guardrail: if net job income alone exceeds desired spending, take no discretionary withdrawals.
        salary_only_tax = calculate_progressive_tax(max(0.0, salary_income), tax_brackets)
        net_job_income = _round_money(salary_income - salary_only_tax)
        desired_net_spending = _round_money(target_withdrawal)

        max_withdrawable = _round_money(
            sum(account.balance for account in accounts if account.owner in retired_owners)
        )
        discretionary_request = 0.0
        if net_job_income > desired_net_spending:
            discretionary_request = 0.0
        elif desired_net_spending > 0:
            low = 0.0
            high = max_withdrawable
            for _ in range(24):
                mid = _round_money((low + high) / 2.0)
                eval_mid = _evaluate_withdrawal_plan(
                    accounts_snapshot=_clone_accounts(accounts),
                    owner_ages=owner_ages,
                    retired_owners=retired_owners,
                    needed_withdrawal=mid,
                    salary_income=salary_income,
                    social_security_income=social_security_income,
                    pension_income=pension_income,
                    tax_brackets=tax_brackets,
                    capital_gains_brackets=capital_gains_brackets,
                )
                if float(eval_mid["net_income"]) >= desired_net_spending:
                    high = mid
                else:
                    low = mid
            discretionary_request = high

        evaluation = _evaluate_withdrawal_plan(
            accounts_snapshot=accounts,
            owner_ages=owner_ages,
            retired_owners=retired_owners,
            needed_withdrawal=discretionary_request,
            salary_income=salary_income,
            social_security_income=social_security_income,
            pension_income=pension_income,
            tax_brackets=tax_brackets,
            capital_gains_brackets=capital_gains_brackets,
        )

        withdrawals = evaluation["withdrawals"]
        shortfall = float(evaluation["shortfall"])
        breakdown = evaluation["breakdown"]
        taxable_social_security = float(evaluation["taxable_social_security"])
        ordinary_income_tax = float(evaluation["ordinary_income_tax"])
        capital_gains_tax = float(evaluation["capital_gains_tax"])
        taxes = float(evaluation["taxes"])
        withdrawn_total = float(evaluation["withdrawn_total"])
        net_income = float(evaluation["net_income"])

        withdrawal_by_account_type = {key: 0.0 for key in account_type_keys}

        for account, amount in withdrawals:
            withdrawal_by_account_type[account.account_type.value] = round(
                withdrawal_by_account_type[account.account_type.value] + amount,
                2,
            )

        tax_allocations = _allocate_taxes(
            salary_income=salary_income,
            pension_income=pension_income,
            social_security_income=social_security_income,
            breakdown=breakdown,
            ordinary_income_tax=ordinary_income_tax,
            capital_gains_tax=capital_gains_tax,
        )
        income_sources, sources, net_withdrawn_total = _build_income_and_withdrawal_sources(
            salary_income=salary_income,
            pension_income=pension_income,
            social_security_income=social_security_income,
            withdrawals=withdrawals,
            tax_allocations=tax_allocations,
            breakdown=breakdown,
        )

        pre_growth_balance_total = sum(account.balance for account in accounts)
        weighted_rate_numerator = 0.0
        for account in accounts:
            effective_rate = (account.stock_mix * stock_return) + ((1.0 - account.stock_mix) * bond_return)
            weighted_rate_numerator += account.balance * effective_rate
            account.balance = apply_annual_return(account.balance, effective_rate)

        ending_balance = round(sum(account.balance for account in accounts), 2)
        account_end_balances = {
            _account_balance_key(account): _round_money(account.balance)
            for account in accounts
        }
        annual_return_rate = (
            round(weighted_rate_numerator / pre_growth_balance_total, 6)
            if pre_growth_balance_total > 0
            else 0.0
        )
        annual_gain_loss = round(ending_balance - pre_growth_balance_total, 2)
        gross_withdrawn_total = _round_money(withdrawn_total)
        effective_tax_rate = (
            round((gross_withdrawn_total - net_withdrawn_total) / gross_withdrawn_total, 6)
            if gross_withdrawn_total > 0
            else 0.0
        )
        projections.append(
            YearProjection(
                year_index=year_index,
                calendar_year=base_year + (year_index - 1),
                user_age=owner_ages.get("Primary", 0),
                spouse_age=owner_ages.get("Spouse"),
                desired_net_spending=desired_net_spending,
                withdrawn_total=withdrawn_total,
                gross_withdrawn_total=gross_withdrawn_total,
                net_withdrawn_total=net_withdrawn_total,
                salary_income=round(salary_income, 2),
                social_security_income=round(social_security_income, 2),
                pension_income=round(pension_income, 2),
                ordinary_income=round(breakdown.ordinary_income, 2),
                taxable_social_security=taxable_social_security,
                capital_gains=round(breakdown.capital_gains, 2),
                taxes=taxes,
                net_income=net_income,
                beginning_balance=beginning_balance,
                ending_balance=ending_balance,
                shortfall=shortfall,
                annual_return_rate=annual_return_rate,
                annual_gain_loss=annual_gain_loss,
                investment_income_earned=annual_gain_loss,
                market_return_adjustment=round(stock_shock, 6),
                effective_tax_rate=effective_tax_rate,
                withdrawal_by_account_type=withdrawal_by_account_type,
                withdrawal_sources=sources,
                income_sources=income_sources,
                account_end_balances=account_end_balances,
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
    owner_pension_by_name: dict[str, tuple[int | None, float]] | None,
    tax_brackets: list[dict[str, float | None]],
    capital_gains_brackets: list[dict[str, float | None]],
    annual_return_volatility: float,
    pessimistic_return_bias: float,
    likely_return_bias: float,
    optimistic_return_bias: float,
    inflation_rate: float = 0.025,
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
                stock_mix=account.stock_mix,
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
            owner_pension_by_name=owner_pension_by_name,
            tax_brackets=tax_brackets,
            capital_gains_brackets=capital_gains_brackets,
            annual_return_volatility=annual_return_volatility,
            inflation_rate=inflation_rate,
            scenario_return_bias=bias,
            random_seed=seed_base + idx,
        )

    return projections_by_scenario
