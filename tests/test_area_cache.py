import pytest
from app import _area_cache_key


def test_same_deal_has_stable_key_independent_of_json_order():
    a = {'dealData': {'purchasePrice': 200000, 'monthlyCashFlow': 150}, 'postcode': 'M14 5AA'}
    b = {'postcode': 'M14 5AA', 'dealData': {'monthlyCashFlow': 150, 'purchasePrice': 200000}}
    assert _area_cache_key('M14', 'btl', a) == _area_cache_key('M14', 'BTL', b)


@pytest.mark.parametrize('change', [
    {'dealData': {'purchasePrice': 350000}},
    {'postcode': 'M14 6AA'},
    {'benchmark': {'gross_yield_median': 6}},
    {'articleFour': {'is_article_4': True}},
    {'marketContext': {'avgSoldPrice': 240958}},
])
def test_new_deal_or_source_snapshot_cannot_reuse_another_narrative(change):
    base = {'postcode': 'M14 5AA', 'dealData': {'purchasePrice': 200000}}
    assert _area_cache_key('M14', 'BTL', base) != _area_cache_key('M14', 'BTL', {**base, **change})
