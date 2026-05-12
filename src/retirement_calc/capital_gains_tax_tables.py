from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

from .tax_tables import FILING_STATUS_MARRIED_JOINT, FILING_STATUS_SINGLE, calculate_progressive_tax


IRS_CAPITAL_GAINS_URL = "https://www.irs.gov/taxtopics/tc409"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
CONFIG_PATH = CONFIG_DIR / "capital_gains_tax_tables.json"
CONFIG_VERSION = 1


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


def default_capital_gains_config() -> dict[str, object]:
    return {
        "config_version": CONFIG_VERSION,
        "source_url": IRS_CAPITAL_GAINS_URL,
        "source_page_url": IRS_CAPITAL_GAINS_URL,
        "fetched_at": "2026-05-12T00:00:00+00:00",
        "tax_year": 2025,
        "tables": {
            FILING_STATUS_SINGLE: [
                {"lower_bound": 0.0, "upper_bound": 48_350.0, "rate": 0.0},
                {"lower_bound": 48_350.0, "upper_bound": 533_400.0, "rate": 0.15},
                {"lower_bound": 533_400.0, "upper_bound": None, "rate": 0.20},
            ],
            FILING_STATUS_MARRIED_JOINT: [
                {"lower_bound": 0.0, "upper_bound": 96_700.0, "rate": 0.0},
                {"lower_bound": 96_700.0, "upper_bound": 600_050.0, "rate": 0.15},
                {"lower_bound": 600_050.0, "upper_bound": None, "rate": 0.20},
            ],
        },
    }


def _normalized_config(payload: dict[str, object]) -> dict[str, object]:
    config = default_capital_gains_config()
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


def load_capital_gains_config(path: Path = CONFIG_PATH) -> dict[str, object]:
    if not path.exists():
        return default_capital_gains_config()

    with path.open("r", encoding="utf-8") as config_file:
        return _normalized_config(json.load(config_file))


def save_capital_gains_config(config: dict[str, object], path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)


def _capital_gains_from_topic_page(page_text: str) -> dict[str, object]:
    extracted_text = re.sub(r"\s+", " ", page_text)
    fifteen_match = re.search(
        r"A capital gains rate of 15% applies if your taxable income is: .*?"
        r"more than \$48,350 but less than or equal to \$(?P<single>[\d,]+) for single; .*?"
        r"more than \$96,700 but less than or equal to \$(?P<joint>[\d,]+) for married filing jointly",
        extracted_text,
    )
    if not fifteen_match:
        raise ValueError("Could not parse the IRS capital gains tax rate thresholds.")

    return {
        "config_version": CONFIG_VERSION,
        "source_url": IRS_CAPITAL_GAINS_URL,
        "source_page_url": IRS_CAPITAL_GAINS_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "tax_year": 2025,
        "tables": {
            FILING_STATUS_SINGLE: [
                {"lower_bound": 0.0, "upper_bound": 48_350.0, "rate": 0.0},
                {"lower_bound": 48_350.0, "upper_bound": _to_money(fifteen_match.group("single")), "rate": 0.15},
                {"lower_bound": _to_money(fifteen_match.group("single")), "upper_bound": None, "rate": 0.20},
            ],
            FILING_STATUS_MARRIED_JOINT: [
                {"lower_bound": 0.0, "upper_bound": 96_700.0, "rate": 0.0},
                {"lower_bound": 96_700.0, "upper_bound": _to_money(fifteen_match.group("joint")), "rate": 0.15},
                {"lower_bound": _to_money(fifteen_match.group("joint")), "upper_bound": None, "rate": 0.20},
            ],
        },
    }


def refresh_capital_gains_config(path: Path = CONFIG_PATH) -> dict[str, object]:
    with urlopen(IRS_CAPITAL_GAINS_URL, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _HTMLTextExtractor()
    parser.feed(html)
    refreshed = _capital_gains_from_topic_page(parser.text())
    save_capital_gains_config(refreshed, path=path)
    return refreshed


def capital_gains_brackets_for_status(config: dict[str, object], filing_status: str) -> list[dict[str, float | None]]:
    tables = config.get("tables", {})
    if not isinstance(tables, dict):
        raise ValueError("Capital gains configuration is invalid.")
    table = tables.get(filing_status)
    if not isinstance(table, list) or not table:
        raise ValueError(f"No capital gains table found for filing status '{filing_status}'.")
    return table


def calculate_capital_gains_tax(
    ordinary_taxable_income: float,
    capital_gains_income: float,
    brackets: list[dict[str, float | None]],
) -> float:
    if capital_gains_income <= 0:
        return 0.0

    total_tax = calculate_progressive_tax(ordinary_taxable_income + capital_gains_income, brackets)
    ordinary_tax = calculate_progressive_tax(ordinary_taxable_income, brackets)
    return round(max(0.0, total_tax - ordinary_tax), 2)
