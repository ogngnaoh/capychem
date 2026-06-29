import pytest
from capychem.eval import sweep as sweep_mod
from capychem.eval.beat import BeatVerdict
from capychem.eval.runner import ReproResult
from capychem.eval.sweep import run_sweep, week8_verdict
from capychem.eval.verdict import AnalyzerVerdict


def test_reproduce_mode_aggregates_auc_and_no_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the per-task primitive: a 2-molecule buffer scoring ~0.5 top-10 mean.
    def fake_repro(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return ReproResult(
            mol_buffer={"CCO": (0.5, 1), "c1ccccc1": (0.5, 2)},
            generations=2, unique_calls=2,
        )

    monkeypatch.setattr(sweep_mod, "run_reproduction", fake_repro)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="reproduce")
    assert report.mode == "reproduce"
    assert report.tasks_run == 2 and report.tasks_failed == 0
    assert report.beats is None  # reproduce defines no beat
    assert report.published_sum == pytest.approx(0.940 + 0.553)
    assert report.auc_sum > 0.0
    # qed is registered -> reproduce row carries a baseline diff
    qed_row = next(r for r in report.rows if r.task == "qed")
    assert "baseline_published" in qed_row.payload and "within_tolerance" in qed_row.payload


def test_head_to_head_mode_counts_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_h2h(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        beat = task == "jnk3"
        return BeatVerdict(
            task=task, seed=seed, budget=budget,
            llm_auc=0.60 if beat else 0.40, graph_ga_auc=0.50,
            diff=0.10 if beat else -0.10, beat=beat,
            llm_valid_rate=0.9, llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=None, llm_unique_calls=budget, graph_ga_unique_calls=budget,
        )

    monkeypatch.setattr(sweep_mod, "run_head_to_head", fake_h2h)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="head_to_head")
    assert report.beats == 1
    assert report.auc_sum == pytest.approx(0.40 + 0.60)
    assert report.rows[0].payload["graph_ga_auc"] == 0.50  # full verdict fields preserved


def test_analyzer_verdict_mode_counts_helps(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_av(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        helps = task == "jnk3"
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.70 if helps else 0.50, without_auc=0.60,
            diff=0.10 if helps else -0.10, helps=helps,
            analyzer_parse_rate=1.0, analyzer_calls=10, analyzer_parsed=10,
            parse_rate_healthy=True, with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=budget, without_unique_calls=budget,
        )

    monkeypatch.setattr(sweep_mod, "run_analyzer_verdict", fake_av)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="analyzer_verdict")
    assert report.beats == 1
    assert report.auc_sum == pytest.approx(0.50 + 0.70)
    assert report.rows[0].payload["parse_rate_healthy"] is True


def test_week8_mode_runs_with_analyzer_and_counts_beats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    def fake_h2h(task, budget, seed, *, analyzer=False, **kw):  # type: ignore[no-untyped-def]
        seen[task] = analyzer
        beat = task == "jnk3"
        return BeatVerdict(
            task=task, seed=seed, budget=budget,
            llm_auc=0.60 if beat else 0.40, graph_ga_auc=0.50,
            diff=0.10 if beat else -0.10, beat=beat,
            llm_valid_rate=0.95, llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=None, llm_unique_calls=budget, graph_ga_unique_calls=budget,
            analyzer=True, analyzer_parse_rate=1.0, analyzer_calls=10, analyzer_parsed=10,
            parse_rate_healthy=True,
        )

    monkeypatch.setattr(sweep_mod, "run_head_to_head", fake_h2h)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="week8")
    assert report.mode == "week8"
    assert report.beats == 1
    assert seen == {"qed": True, "jnk3": True}  # week8 always runs the analyzer arm
    assert report.rows[0].payload["parse_rate_healthy"] is True
    assert report.auc_sum == pytest.approx(0.40 + 0.60)


def test_per_task_error_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    def flaky_repro(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        if task == "jnk3":
            raise RuntimeError("oracle download failed")
        return ReproResult(mol_buffer={"CCO": (0.5, 1)}, generations=1, unique_calls=1)

    monkeypatch.setattr(sweep_mod, "run_reproduction", flaky_repro)
    report = run_sweep(("qed", "jnk3"), budget=200, seed=42, mode="reproduce")
    assert report.tasks_run == 1 and report.tasks_failed == 1
    bad = next(r for r in report.rows if r.task == "jnk3")
    assert bad.ok is False and "oracle download failed" in bad.payload["error"]


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        run_sweep(("qed",), budget=10, seed=42, mode="nonsense")


def _week8_row(task, *, beat, valid_passed=True, parse_healthy=True):  # type: ignore[no-untyped-def]
    from capychem.eval.sweep import SweepRow
    return SweepRow(
        task=task, ok=True, headline_auc=0.6 if beat else 0.4, beat=beat,
        payload={
            "beat": beat,
            "llm_valid_gate": {"threshold": 0.8, "passed": valid_passed},
            "parse_rate_healthy": parse_healthy,
        },
    )


def test_week8_verdict_counts_only_guarded_beats() -> None:
    from capychem.eval.sweep import SweepReport
    rows = [
        _week8_row("jnk3", beat=True),                                   # trustworthy
        _week8_row("median1", beat=True),                               # trustworthy
        _week8_row("median2", beat=True),                               # trustworthy -> >=3
        _week8_row("sitagliptin_mpo", beat=True, parse_healthy=False),  # degraded, excluded
        _week8_row("zaleplon_mpo", beat=False),                         # no beat
        _week8_row("perindopril_mpo", beat=True, valid_passed=False),   # degraded, excluded
    ]
    report = SweepReport(
        mode="week8", budget=10000, seed=42, tasks_run=6, tasks_failed=0,
        auc_sum=0.0, published_sum=0.0, beats=4, rows=rows,
    )
    out = week8_verdict(report)
    assert out["trustworthy_beats"] == 3
    assert out["raw_beats"] == 4
    assert out["on_track"] is True
    assert set(out["degraded_tasks"]) == {"sitagliptin_mpo", "perindopril_mpo"}
    assert "CLEARED" in out["week8_verdict"]


def test_week8_verdict_inconclusive_below_three() -> None:
    from capychem.eval.sweep import SweepReport
    rows = [_week8_row("jnk3", beat=True), _week8_row("median1", beat=False)]
    report = SweepReport(
        mode="week8", budget=10000, seed=42, tasks_run=2, tasks_failed=0,
        auc_sum=0.0, published_sum=0.0, beats=1, rows=rows,
    )
    out = week8_verdict(report)
    assert out["trustworthy_beats"] == 1
    assert out["on_track"] is False
    assert "INCONCLUSIVE" in out["week8_verdict"]
    assert "NOT a clean pivot" in out["week8_verdict"]
