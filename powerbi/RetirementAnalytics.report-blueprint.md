# Retirement Analytics Report Blueprint

This report is designed for the `ProjectionBiExport` table loaded from the BI-oriented CSV export.

## Report Style

- Apply `RetirementAnalytics.theme.json`
- Use a clean white canvas
- Prefer deep blue for primary value series, gold for highlights, red for taxes or negative values, and light blue for secondary comparisons
- Add a scenario slicer on every page

## Page 1: Plan Summary

Goal: mirror the plan summary feel with a compact executive overview.

Visuals:

- Card: `Final Ending Balance`
- Card: `Taxes`
  Use total report context or selected year context depending on page filter preference.
- Card: `First Shortfall Year`
- Line chart:
  Axis: `calendar_year`
  Values: `Ending Balance`
  Title: `Lifetime Portfolio Value`
- Combo chart:
  Axis: `calendar_year`
  Column values: `Total Inflows`
  Line values: `Modeled Outflows`
  Title: `Cash Flow Overview`

## Page 2: Cash Flow

Goal: reproduce the plan's inflows versus outflows view.

Visuals:

- Line chart:
  Axis: `calendar_year`
  Values: `Total Inflows`, `Modeled Outflows`
  Title: `Inflows and Outflows`
- Column chart:
  Axis: `calendar_year`
  Values: `Ending Balance`
  Title: `Portfolio Assets`
- Optional table:
  Columns: `scenario`, `calendar_year`, `Total Inflows`, `Modeled Outflows`, `Net Cash Flow`, `Ending Balance`

## Page 3: Income Flows

Goal: reproduce the plan's stacked income flow chart.

Visuals:

- Stacked column chart:
  Axis: `calendar_year`
  Values: `Salary Income`, `Pension Income`, `Social Security Income`, `Net Withdrawals`
  Title: `Income Flows`
- Optional matrix:
  Rows: `calendar_year`
  Values: the same four measures

## Page 4: Withdrawals And Taxes

Goal: show withdrawal dependence and taxable impact over time.

Visuals:

- Clustered column chart:
  Axis: `calendar_year`
  Values: `Gross Withdrawals`, `Realized Capital Gains`
  Title: `Withdrawals and Realized Gains`
- Line chart:
  Axis: `calendar_year`
  Values: `Taxes`
  Title: `Taxes Over Time`
- Optional matrix:
  Rows: `calendar_year`, `account_name`
  Columns: `metric_name`
  Visual-level filter: `row_type = withdrawal_metric`

## Page 5: Assets By Tax Type

Goal: approximate the plan's tax-type asset breakdown using account type mapping.

Visuals:

- Stacked area chart or stacked column chart:
  Axis: `calendar_year`
  Legend: `Tax Bucket`
  Values: `Ending Balance By Tax Bucket`
  Visual-level filter: `row_type = account_metric`
  Visual-level filter: `metric_name = ending_balance`
  Title: `Assets by Tax Type`

## Recommended Slicers

- `scenario`
- `calendar_year`
- `owner`
- `Tax Bucket`

## Notes

- `Modeled Outflows` is based on `Desired Net Spending + Taxes`. It is not a category-level expense schedule.
- `Net Withdrawals` is based on withdrawal flow rows and therefore reflects after-tax account cash available.
- `Assets by Tax Type` uses account type mapping rather than a separate exported tax-bucket summary table.