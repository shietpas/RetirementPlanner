from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen


IRS_TAX_BRACKETS_URL = "https://www.irs.gov/filing/federal-income-tax-rates-and-brackets"
IRS_TAX_ADJUSTMENTS_URL = (
    "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-"
    "including-amendments-from-the-one-big-beautiful-bill"
)
CONFIG_DIR = Path(__file__).resolve().parent / "config"
CONFIG_PATH = CONFIG_DIR / "tax_tables.json"
CONFIG_VERSION = 1
FILING_STATUS_SINGLE = "single"
FILING_STATUS_MARRIED_JOINT = "married_filing_jointly"
TAX_RATES = [10, 12, 22, 24, 32, 35, 37]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(self._parts)


def _to_money(value: str) -> float:
    return float(value.replace(",", ""))


def _build_brackets(bounds: list[float]) -> list[dict[str, float | None]]:
    brackets: list[dict[str, float | None]] = []
    lower_bound = 0.0
    for index, rate in enumerate(TAX_RATES):
        upper_bound = bounds[index] if index < len(bounds) else None
        brackets.append(
            {
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "rate": rate / 100.0,
            }
        )
        lower_bound = 0.0 if upper_bound is None else upper_bound
    return brackets


def _table_from_adjustments_page(page_text: str) -> dict[str, object]:
    extracted_text = re.sub(r"\s+", " ", page_text)

    lowest_match = re.search(
        r"The lowest rate is 10% for incomes of single individuals with incomes of \$(?P<single>[\d,]+) or less "
        r"\(\$(?P<joint>[\d,]+) for married couples filing jointly\)",
        extracted_text,
    )
    if not lowest_match:
        raise ValueError("Could not parse the 10% IRS tax bracket from the IRS page.")

    rate_thresholds: dict[int, dict[str, float]] = {
        10: {
            FILING_STATUS_SINGLE: _to_money(lowest_match.group("single")),
            FILING_STATUS_MARRIED_JOINT: _to_money(lowest_match.group("joint")),
        }
    }

    for rate_match in re.finditer(
        r"(?P<rate>12|22|24|32|35)% for incomes over \$(?P<single>[\d,]+) "
        r"\(\$(?P<joint>[\d,]+) for married couples filing jointly\)",
        extracted_text,
    ):
        rate = int(rate_match.group("rate"))
        rate_thresholds[rate] = {
            FILING_STATUS_SINGLE: _to_money(rate_match.group("single")),
            FILING_STATUS_MARRIED_JOINT: _to_money(rate_match.group("joint")),
        }

    top_match = re.search(
        r"37% .*? incomes greater than \$(?P<single>[\d,]+) \(\$(?P<joint>[\d,]+) for married couples filing jointly\)",
        extracted_text,
    )
    if not top_match:
        raise ValueError("Could not parse the 37% IRS tax bracket from the IRS page.")

    rate_thresholds[37] = {
        FILING_STATUS_SINGLE: _to_money(top_match.group("single")),
        FILING_STATUS_MARRIED_JOINT: _to_money(top_match.group("joint")),
    }

    if len(rate_thresholds) != len(TAX_RATES):
        raise ValueError("IRS tax bracket table did not contain the expected number of rate bands.")

    return {
        "config_version": CONFIG_VERSION,
        "source_url": IRS_TAX_ADJUSTMENTS_URL,
        "source_page_url": IRS_TAX_BRACKETS_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "tax_year": 2026,
        "tables": {
            FILING_STATUS_SINGLE: _build_brackets(
                [
                    rate_thresholds[10][FILING_STATUS_SINGLE],
                    rate_thresholds[12][FILING_STATUS_SINGLE],
                    rate_thresholds[22][FILING_STATUS_SINGLE],
                    rate_thresholds[24][FILING_STATUS_SINGLE],
                    rate_thresholds[32][FILING_STATUS_SINGLE],
                    rate_thresholds[35][FILING_STATUS_SINGLE],
                    rate_thresholds[37][FILING_STATUS_SINGLE],
                ]
            ),
            FILING_STATUS_MARRIED_JOINT: _build_brackets(
                [
                    rate_thresholds[10][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[12][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[22][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[24][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[32][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[35][FILING_STATUS_MARRIED_JOINT],
                    rate_thresholds[37][FILING_STATUS_MARRIED_JOINT],
                ]
            ),
        },
    }


def default_tax_table_config() -> dict[str, object]:
    return {
        "config_version": CONFIG_VERSION,
        "source_url": IRS_TAX_ADJUSTMENTS_URL,
        "source_page_url": IRS_TAX_BRACKETS_URL,
        "fetched_at": "2026-10-09T00:00:00+00:00",
        "tax_year": 2026,
        "tables": {
            FILING_STATUS_SINGLE: _build_brackets([12400.0, 50400.0, 105700.0, 201775.0, 256225.0, 640600.0]),
            FILING_STATUS_MARRIED_JOINT: _build_brackets(
                [24800.0, 100800.0, 211400.0, 403550.0, 512450.0, 768700.0]
            ),
        },
    }


def _normalized_config(payload: dict[str, object]) -> dict[str, object]:
    config = default_tax_table_config()
    if not isinstance(payload, dict):
        return config

    config["config_version"] = int(payload.get("config_version", CONFIG_VERSION))
    config["source_url"] = str(payload.get("source_url", config["source_url"]))
    config["source_page_url"] = str(payload.get("source_page_url", config["source_page_url"]))
    config["fetched_at"] = str(payload.get("fetched_at", config["fetched_at"]))
    config["tax_year"] = int(payload.get("tax_year", config["tax_year"]))

    tables = payload.get("tables", {})
    if isinstance(tables, dict):
        for filing_status in (FILING_STATUS_SINGLE, FILING_STATUS_MARRIED_JOINT):
            table_data = tables.get(filing_status)
            if not isinstance(table_data, list):
                continue
            normalized_table: list[dict[str, float | None]] = []
            for row in table_data:
                if not isinstance(row, dict):
                    continue
                normalized_table.append(
                    {
                        "lower_bound": float(row.get("lower_bound", 0.0)),
                        "upper_bound": None if row.get("upper_bound") is None else float(row.get("upper_bound")),
                        "rate": float(row.get("rate", 0.0)),
                    }
                )
            if normalized_table:
                config["tables"][filing_status] = normalized_table

    return config


def load_tax_table_config(path: Path = CONFIG_PATH) -> dict[str, object]:
    if not path.exists():
        return default_tax_table_config()

    with path.open("r", encoding="utf-8") as config_file:
        return _normalized_config(json.load(config_file))


def save_tax_table_config(config: dict[str, object], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)


def refresh_tax_table_config(path: Path = CONFIG_PATH) -> dict[str, object]:
    with urlopen(IRS_TAX_ADJUSTMENTS_URL, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _HTMLTextExtractor()
    parser.feed(html)
    refreshed = _table_from_adjustments_page(parser.text())
    save_tax_table_config(refreshed, path=path)
    return refreshed


def tax_brackets_for_status(config: dict[str, object], filing_status: str) -> list[dict[str, float | None]]:
    tables = config.get("tables", {})
    if not isinstance(tables, dict):
        raise ValueError("Tax table configuration is invalid.")
    table = tables.get(filing_status)
    if not isinstance(table, list) or not table:
        raise ValueError(f"No tax table found for filing status '{filing_status}'.")
    return table


def calculate_progressive_tax(taxable_income: float, brackets: list[dict[str, float | None]]) -> float:
    if taxable_income <= 0:
        return 0.0

    tax_due = 0.0
    for bracket in brackets:
        lower_bound = float(bracket.get("lower_bound", 0.0))
        upper_bound = bracket.get("upper_bound")
        rate = float(bracket.get("rate", 0.0))

        if taxable_income <= lower_bound:
            continue

        taxable_slice = taxable_income - lower_bound
        if upper_bound is not None:
            taxable_slice = min(taxable_slice, float(upper_bound) - lower_bound)

        tax_due += taxable_slice * rate

    return round(tax_due, 2)
