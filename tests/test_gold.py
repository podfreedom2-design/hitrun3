import math
from hitrun3.data import thai_gold_from_usd, BAHT_WEIGHT_FACTOR
from hitrun3.config import Config
from hitrun3 import engine as E


def test_baht_weight_factor():
    assert math.isclose(BAHT_WEIGHT_FACTOR, 0.47295, rel_tol=1e-4)


def test_thai_gold_conversion_matches_gta():
    # 2026-10-30 สมาคมค้าทองคำ: spot 3999 USD, 33.69 THB → ทองแท่งขายออก 63,750
    p = thai_gold_from_usd(3999, 33.69)
    assert abs(p / 63750 - 1) < 0.005


def test_gold_fractional_units_and_spread():
    c = Config(gold_source="THGOLD", gold_spread_thb=200, gold_fee_thb=5, gold_unit_step=0.0001)
    q = E.gold_qty(c, 120000, 62250)
    assert 1.92 < q < 1.93 and abs(q * 10000 - round(q * 10000)) < 1e-6
    h, cash, tr = E.rebalance(c, {}, 120000, {"GOLD": 62250}, {"GOLD": q}, "2026-10-30")
    assert cash >= 0 and tr[0]["fee"] == 5
    h2, cash2, tr2 = E.rebalance(c, h, cash, {"GOLD": 62250}, {}, "2026-11-30")
    assert math.isclose(tr2[0]["fee"], q * 200, rel_tol=1e-9)
