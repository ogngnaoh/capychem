import pytest
from capychem.eval.metric import top_auc


def test_constant_curve_no_finish_pad() -> None:
    # 300 molecules all score 0.5; budget=300 so finish adds nothing.
    # range(100,300,100)=[100,200]; idx100: +100*(0.5+0)/2=25; idx200: +100*(0.5+0.5)/2=50 -> 75
    # partial: (300-200)*(0.5+0.5)/2=50 -> 125 ; 125/300 = 0.416666...
    buf = {f"s{i}": (0.5, i + 1) for i in range(300)}
    assert top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=300) == pytest.approx(0.416666, abs=1e-5)


def test_finish_pads_remaining_budget() -> None:
    # same buffer but budget=400 -> early stop; finish pads (400-300)*0.5=50 -> 175 ; 175/400 = 0.4375
    buf = {f"s{i}": (0.5, i + 1) for i in range(300)}
    assert top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=400) == pytest.approx(0.4375, abs=1e-5)


def test_top_n_selection_and_call_order_replay() -> None:
    # a(0.1,1) b(0.9,2) c(0.2,3) d(0.8,4); top_n=2 freq_log=2 max=4 finish=True
    # idx2: ordered[:2]=[a,b]; top2=[0.9,0.1] mean=0.5; +2*(0.5+0)/2=0.5
    # partial:(4-2); top2 of all=[0.9,0.8] mean=0.85; +2*(0.85+0.5)/2=1.35 -> 1.85 ; 1.85/4=0.4625
    buf = {"a": (0.1, 1), "b": (0.9, 2), "c": (0.2, 3), "d": (0.8, 4)}
    assert top_auc(buf, top_n=2, finish=True, freq_log=2, max_oracle_calls=4) == pytest.approx(0.4625, abs=1e-9)


def test_fewer_than_top_n_molecules() -> None:
    # 3 molecules, top_n=10 -> mean over the 3 available; must not crash
    buf = {"a": (0.2, 1), "b": (0.4, 2), "c": (0.6, 3)}
    val = top_auc(buf, top_n=10, finish=True, freq_log=100, max_oracle_calls=10000)
    assert 0.0 <= val <= 1.0
