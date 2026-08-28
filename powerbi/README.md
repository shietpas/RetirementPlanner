# Power BI Report Kit

This folder contains a Power BI starter kit designed for the `Export BI CSV` output from the app.

It does not include a binary `.pbix` file. Instead, it provides repo-friendly assets that can be versioned safely:

- `RetirementAnalytics.theme.json`: report theme inspired by the attached financial plan
- `ProjectionBiExport.pq`: Power Query function to import and type the BI CSV
- `RetirementAnalytics.measures.dax`: calculated columns and measures for visuals
- `RetirementAnalytics.report-blueprint.md`: page and visual design for the report

## Import Steps

1. In the app, run `Calculate Plan` and then use `Export BI CSV`.
2. Open Power BI Desktop.
3. Import the theme from `View > Themes > Browse for themes` and select `RetirementAnalytics.theme.json`.
4. Create a blank query and paste in `ProjectionBiExport.pq`.
5. Invoke the function with the full path to your exported BI CSV.
6. Name the resulting table `ProjectionBiExport`.
7. In Data view, create the calculated columns and measures from `RetirementAnalytics.measures.dax`.
8. Build the pages described in `RetirementAnalytics.report-blueprint.md`.

## Expected Table Name

The DAX in this folder assumes the imported table is named `ProjectionBiExport`.

## Supported Visuals

This kit is designed to support a subset of the financial-plan-style visuals that match the current app data model:

- portfolio assets over time
- cash inflows vs modeled outflows
- income flows by year
- withdrawals and realized capital gains
- assets by tax type using account type mapping
- simple plan summary cards

## Limits

This report kit is built on the simplified analytics model in the app. It does not attempt to reproduce sections that depend on expense categories, liabilities, milestone events, or Monte Carlo simulation.