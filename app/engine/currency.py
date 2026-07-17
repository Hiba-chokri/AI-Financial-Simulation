"""
Currency conversion for API outputs.

All internal engines compute in MAD. This module converts output values to
whichever currency the caller requested. Rates live here and nowhere else —
update RATES_FROM_MAD when exchange rates change.
"""
from enum import Enum
from typing import Dict


class Currency(str, Enum):
    MAD = "MAD"
    USD = "USD"
    EUR = "EUR"


# How many units of the target currency equal 1 MAD.
# Source: approximate mid-market rates — update periodically.
RATES_FROM_MAD: Dict[str, float] = {
    "MAD": 1.0,
    "USD": 0.099,   # 1 MAD ≈ 0.099 USD  (≈ 10.1 MAD / USD)
    "EUR": 0.091,   # 1 MAD ≈ 0.091 EUR  (≈ 11.0 MAD / EUR)
}


def convert(amount_mad: float, to: Currency) -> float:
    """Convert a MAD amount to the target currency."""
    return amount_mad * RATES_FROM_MAD[to.value]
