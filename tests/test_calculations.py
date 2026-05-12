import unittest

from src.retirement_calc.calculations import (
    apply_annual_return,
    calculate_rmd,
    classify_withdrawals,
    simulate_retirement,
)
from src.retirement_calc.models import Account, AccountType


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

    def test_simulate_retirement_withdrawals_respect_tax_identity(self):
        accounts = [
            Account(
                owner="Primary",
                name="401k",
                account_type=AccountType.K401_NON_ROTH,
                balance=5000.0,
                annual_return_rate=0.0,
            ),
            Account(
                owner="Primary",
                name="401k Roth",
                account_type=AccountType.K401_ROTH,
                balance=10000.0,
                annual_return_rate=0.0,
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
            income_tax_rate=0.22,
            capital_gains_tax_rate=0.15,
        )

        self.assertEqual(len(projection), 1)
        self.assertEqual(projection[0].ordinary_income, 5000.0)
        self.assertEqual(projection[0].withdrawn_total, 10000.0)
        self.assertEqual(projection[0].taxes, 1100.0)
        self.assertGreaterEqual(len(projection[0].withdrawal_sources), 1)
        self.assertEqual(projection[0].withdrawal_sources[0].owner, "Primary")

    def test_salary_offsets_withdrawals_until_retirement_year_passes(self):
        accounts = [
            Account(
                owner="Primary",
                name="401k",
                account_type=AccountType.K401_NON_ROTH,
                balance=50000.0,
                annual_return_rate=0.0,
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
            income_tax_rate=0.22,
            capital_gains_tax_rate=0.15,
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
                    annual_return_rate=0.0,
                )
            ],
            years=1,
            annual_withdrawal_value=60000.0,
            withdrawal_mode="flat",
            owner_age_by_name={"Primary": 56},
            owner_retirement_age_by_name={"Primary": 55},
            owner_salary_by_name={"Primary": 60000.0},
            owner_ss_by_name={"Primary": (67, 0.0)},
            income_tax_rate=0.22,
            capital_gains_tax_rate=0.15,
        )
        self.assertEqual(follow_on[0].salary_income, 0.0)
        self.assertGreater(follow_on[0].withdrawn_total, 0.0)


if __name__ == "__main__":
    unittest.main()
