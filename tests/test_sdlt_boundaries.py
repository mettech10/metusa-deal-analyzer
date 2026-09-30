import pytest
from app import calculate_stamp_duty


@pytest.mark.parametrize("price,expected", [(0, 0), (39999, 0), (40000, 2000), (40001, 2000.05), (215000, 12550)])
def test_additional_dwelling_threshold(price, expected):
    assert calculate_stamp_duty(price) == pytest.approx(expected)


def test_owner_occupied_relief_remains_available_to_eligible_callers():
    assert calculate_stamp_duty(200000, second_property=False, first_time_buyer=True) == 0
    assert calculate_stamp_duty(500000, second_property=False, first_time_buyer=True) == 10000
