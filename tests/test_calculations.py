import unittest

from src.retirement_calc.calculations import (
    apply_annual_return,
    calculate_rmd,
    classify_withdrawals,
    simulate_retirement,
    simulate_retirement_scenarios,
)
from src.retirement_calc.models import Account, AccountType
from src.retirement_calc.tax_tables import (
    FILING_STATUS_SINGLE,
    calculate_progressive_tax,
    default_tax_table_config,
    tax_brackets_for_status,
)
from src.retirement_calc.capital_gains_tax_tables import (
    capital_gains_brackets_for_status,
    calculate_capital_gains_tax,
    default_capital_gains_config,
)


class CalculationTests(unittest.TestCase):
    def test_apply_annual_return(self):
        self.assertEqual(apply_annual_return(100000.0, 0.07), 107000.0)

    def test_classify_withdrawals_by_tax_treatment(self):
        withdrawals = [
            (
                Account(
                    owner="User",
                    name="Work 401k",
                    account_type=AccountType.K401_NON_ROTH,
                    balance=100000.0,
                ),
                10000.0,
            ),
            (
                Account(
                    owner="User",
                    name="Roth 401k",
                    account_type=AccountType.K401_ROTH,
                    balance=100000.0,
                ),
                10000.0,
            ),
            (
                Account(
                    owner="User",
                    name="Brokerage",
                    account_type=AccountType.TAXABLE_INVESTMENT,
                    balance=100000.0,
                    cost_basis=70000.0,
                ),
                5000.0,
            ),
        ]

        result = classify_withdrawals(withdrawals)
        self.assertEqual(result.ordinary_income, 10000.0)
        self.assertEqual(result.tax_free, 10000.0)
        self.assertEqual(result.capital_gains, 5000.0)

    def test_calculate_rmd_only_for_eligible_non_roth(self):
        self.assertGreater(calculate_rmd(100000.0, 72, AccountType.K401_NON_ROTH), 0.0)
        self.assertEqual(calculate_rmd(100000.0, 72, AccountType.K401_ROTH), 0.0)

    def test_calculate_progressive_tax_uses_brackets(self):
        brackets = [
            {"lower_bound": 0.0, "upper_bound": 10_000.0, "rate": 0.1},
            {"lower_bound": 10_000.0, "upper_bound": 20_000.0, "rate": 0.2},
            {"lower_bound": 20_000.0, "upper_bound": None, "rate": 0.3},
        ]

        self.assertEqual(calculate_progressive_tax(25_000.0, brackets), 4_500.0)

    def test_default_tax_config_includes_single_brackets(self):
        brackets = tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE)
        self.assertEqual(brackets[0]["upper_bound"], 12_400.0)

    def test_capital_gains_config_includes_single_brackets(self):
        brackets = capital_gains_brackets_for_status(default_capital_gains_config(), FILING_STATUS_SINGLE)
        self.assertEqual(brackets[0]["upper_bound"], 48_350.0)

    def test_capital_gains_tax_uses_brackets(self):
        brackets = capital_gains_brackets_for_status(default_capital_gains_config(), FILING_STATUS_SINGLE)
        self.assertEqual(calculate_capital_gains_tax(40_000.0, 20_000.0, brackets), 1747.5)

    def test_simulate_retirement_withdrawals_respect_tax_identity(self):
        accounts = [
            Account(
                owner="Primary",
                name="401k",
                account_type=AccountType.K401_NON_ROTH,
                balance=5000.0,
                stock_mix=1.0,
            ),
            Account(
                owner="Primary",
                name="401k Roth",
                account_type=AccountType.K401_ROTH,
                balance=10000.0,
                stock_mix=1.0,
            ),
        ]
        projection = simulate_retirement(
            accounts=accounts,
            years=1,
            annual_withdrawal_value=10000.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 65},
            owner_retirement_age_by_name={"Primary": 64},
            owner_salary_by_name={"Primary": 0.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name=None,
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
        )

        self.assertEqual(len(projection), 1)
        self.assertEqual(projection[0].ordinary_income, 5000.0)
        self.assertEqual(projection[0].withdrawn_total, 10000.0)
        self.assertEqual(projection[0].taxes, 500.0)
        self.assertGreaterEqual(len(projection[0].withdrawal_sources), 1)
        self.assertEqual(projection[0].withdrawal_sources[0].owner, "Primary")

    def test_salary_offsets_withdrawals_until_retirement_year_passes(self):
        accounts = [
            Account(
                owner="Primary",
                name="401k",
                account_type=AccountType.K401_NON_ROTH,
                balance=50000.0,
                stock_mix=1.0,
            )
        ]
        projection = simulate_retirement(
            accounts=accounts,
            years=2,
            annual_withdrawal_value=60000.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 54},
            owner_retirement_age_by_name={"Primary": 55},
            owner_salary_by_name={"Primary": 60000.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name=None,
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
        )

        self.assertEqual(len(projection), 2)
        self.assertEqual(projection[0].user_age, 54)
        self.assertEqual(projection[1].user_age, 55)
        self.assertEqual(projection[0].withdrawn_total, 0.0)
        self.assertEqual(projection[1].withdrawn_total, 0.0)
        self.assertEqual(projection[0].salary_income, 60000.0)
        self.assertEqual(projection[1].salary_income, 60000.0)

        follow_on = simulate_retirement(
            accounts=[
                Account(
                    owner="Primary",
                    name="401k",
                    account_type=AccountType.K401_NON_ROTH,
                    balance=50000.0,
                    stock_mix=1.0,
                )
            ],
            years=1,
            annual_withdrawal_value=60000.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 56},
            owner_retirement_age_by_name={"Primary": 55},
            owner_salary_by_name={"Primary": 60000.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name=None,
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
        )
        self.assertEqual(follow_on[0].salary_income, 0.0)
        self.assertGreater(follow_on[0].withdrawn_total, 0.0)

    def test_salary_does_not_increase_ending_balance(self):
        projection = simulate_retirement(
            accounts=[
                Account(
                    owner="Primary",
                    name="401k",
                    account_type=AccountType.K401_NON_ROTH,
                    balance=100000.0,
                    stock_mix=1.0,
                )
            ],
            years=1,
            annual_withdrawal_value=60000.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 50},
            owner_retirement_age_by_name={"Primary": 65},
            owner_salary_by_name={"Primary": 60000.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name=None,
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
        )

        self.assertEqual(len(projection), 1)
        self.assertEqual(projection[0].withdrawn_total, 0.0)
        self.assertEqual(projection[0].salary_income, 60000.0)
        # Ending balance should reflect returns only, not salary contributions.
        self.assertEqual(projection[0].ending_balance, 110000.0)

    def test_scenarios_order_final_balances(self):
        projections = simulate_retirement_scenarios(
            accounts=[
                Account(
                    owner="Primary",
                    name="Brokerage",
                    account_type=AccountType.TAXABLE_INVESTMENT,
                    balance=100000.0,
                    stock_mix=0.70,
                    cost_basis=80000.0,
                )
            ],
            years=5,
            annual_withdrawal_value=0.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 40},
            owner_retirement_age_by_name={"Primary": 30},
            owner_salary_by_name={"Primary": 0.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name=None,
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
            annual_return_volatility=0.0,
            pessimistic_return_bias=-0.03,
            likely_return_bias=0.0,
            optimistic_return_bias=0.03,
            random_seed=42,
        )

        pess_end = projections["Pessimistic"][-1].ending_balance
        likely_end = projections["Likely"][-1].ending_balance
        opt_end = projections["Optimistic"][-1].ending_balance

        self.assertLess(pess_end, likely_end)
        self.assertLess(likely_end, opt_end)

    def test_variable_returns_are_reproducible_with_seed(self):
        def run_once() -> list:
            return simulate_retirement(
                accounts=[
                    Account(
                        owner="Primary",
                        name="401k",
                        account_type=AccountType.K401_NON_ROTH,
                        balance=100000.0,
                        stock_mix=0.70,
                    )
                ],
                years=3,
                annual_withdrawal_value=0.0,
                withdrawal_mode="flat",
                owner_age_by_name={"Primary": 50},
                owner_retirement_age_by_name={"Primary": 40},
                owner_salary_by_name={"Primary": 0.0},
                owner_ss_by_name={"Primary": (67, 0.0)},
                owner_pension_by_name=None,
                tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
                capital_gains_brackets=capital_gains_brackets_for_status(
                    default_capital_gains_config(),
                    FILING_STATUS_SINGLE,
                ),
                annual_return_volatility=0.10,
                scenario_return_bias=0.0,
                random_seed=12345,
            )

        projection_a = run_once()
        projection_b = run_once()

        self.assertEqual(
            [year.ending_balance for year in projection_a],
            [year.ending_balance for year in projection_b],
        )
        self.assertTrue(any(abs(year.market_return_adjustment) > 0 for year in projection_a))

    def test_pension_income_included_after_start_age(self):
        projection = simulate_retirement(
            accounts=[
                Account(
                    owner="Primary",
                    name="IRA",
                    account_type=AccountType.IRA_TRADITIONAL,
                    balance=50000.0,
                    stock_mix=0.5,
                )
            ],
            years=1,
            annual_withdrawal_value=0.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 65},
            owner_retirement_age_by_name={"Primary": 60},
            owner_salary_by_name={"Primary": 0.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            owner_pension_by_name={"Primary": (65, 1000.0)},
            tax_brackets=tax_brackets_for_status(default_tax_table_config(), FILING_STATUS_SINGLE),
            capital_gains_brackets=capital_gains_brackets_for_status(
                default_capital_gains_config(),
                FILING_STATUS_SINGLE,
            ),
            annual_return_volatility=0.0,
            scenario_return_bias=0.0,
            random_seed=1,
        )

        self.assertEqual(len(projection), 1)
        self.assertEqual(projection[0].pension_income, 12000.0)
        self.assertGreater(projection[0].taxes, 0.0)


if __name__ == "__main__":
    unittest.main()
