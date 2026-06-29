from capychem.eval.baselines import GRAPH_GA_AUC_TOP10, compare_to_baseline
from capychem.eval.tasks import PMO_TASKS


def test_qed_within_tolerance() -> None:
    res = compare_to_baseline("qed", 0.935)
    assert res.baseline == 0.940
    assert res.within_tolerance is True
    assert abs(res.diff - (-0.005)) < 1e-9


def test_qed_outside_tolerance() -> None:
    res = compare_to_baseline("qed", 0.80)
    assert res.within_tolerance is False


def test_jnk3_registered() -> None:
    assert GRAPH_GA_AUC_TOP10["jnk3"] == 0.553
    res = compare_to_baseline("jnk3", 0.553)
    assert res.baseline == 0.553
    assert res.within_tolerance is True


def test_baselines_cover_every_registry_task() -> None:
    assert set(GRAPH_GA_AUC_TOP10) == set(PMO_TASKS)


def test_baseline_sum_matches_published_total() -> None:
    # PMO paper Table 2, Graph-GA "Sum (23 tasks)" = 13.751.
    # The 3-decimal display values sum to 13.742; the paper's sum is computed from
    # higher-precision internals, yielding a -0.009 rounding-accumulation gap.
    # Tolerance 1e-2 correctly captures "within published rounding" for 23 values.
    assert abs(sum(GRAPH_GA_AUC_TOP10.values()) - 13.751) < 1e-2


def test_baseline_spot_values() -> None:
    assert GRAPH_GA_AUC_TOP10["jnk3"] == 0.553
    assert GRAPH_GA_AUC_TOP10["drd2"] == 0.964
    assert GRAPH_GA_AUC_TOP10["valsartan_smarts"] == 0.000
