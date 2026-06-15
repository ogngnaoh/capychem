from capychem.eval.baselines import compare_to_baseline


def test_qed_within_tolerance() -> None:
    res = compare_to_baseline("qed", 0.935)
    assert res.baseline == 0.940
    assert res.within_tolerance is True
    assert abs(res.diff - (-0.005)) < 1e-9


def test_qed_outside_tolerance() -> None:
    res = compare_to_baseline("qed", 0.80)
    assert res.within_tolerance is False
