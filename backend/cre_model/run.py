from __future__ import annotations

import argparse
import json
from pathlib import Path

from cre_model.engine import calculate_deal
from cre_model.inputs import DealAssumptions
from cre_model.report.render import render_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Underwrite a CRE deal and render an OM PDF.")
    parser.add_argument("--deal", required=True, type=Path, help="Path to deal assumptions JSON")
    parser.add_argument("--output", required=True, type=Path, help="Destination PDF path")
    arguments = parser.parse_args()

    deal = DealAssumptions.model_validate_json(arguments.deal.read_text(encoding="utf-8"))
    results = calculate_deal(deal)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(deal, results, arguments.output)
    print(
        json.dumps(
            {
                "output": str(arguments.output),
                "property_name": results.property_name,
                "unlevered_irr": results.unlevered_irr,
                "levered_irr": results.levered_irr,
                "equity_multiple": results.levered_equity_multiple,
                "monthly_periods": len(results.monthly_cash_flows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()