import json

from capychem.eval.cli import main


def test_cli_emits_report(harness: None, capsys) -> None:  # type: ignore[no-untyped-def]
    argv = ["--task", "qed", "--budget", "120", "--seed", "42"]
    argv += ["--pop-size", "20", "--offspring", "10"]
    rc = main(argv)
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["task"] == "qed"
    assert report["budget"] == 120
    assert 0.0 <= report["auc_top10"] <= 1.0
    assert report["unique_calls_used"] <= 120
    assert report["baseline_published"] == 0.940
    assert "within_tolerance" in report and "diff" in report and "wall_seconds" in report


def test_cli_head_to_head_report(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # Stub the verdict so the CLI test runs no eval and makes no DeepSeek call —
    # the wiring (flag -> run_head_to_head -> report) is what's under test.
    from capychem.eval import beat as beat_mod
    from capychem.eval.beat import BeatVerdict

    def fake_h2h(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return BeatVerdict(
            task=task,
            seed=seed,
            budget=budget,
            llm_auc=0.61,
            graph_ga_auc=0.55,
            diff=0.06,
            beat=True,
            llm_valid_rate=0.9,
            llm_valid_gate={"threshold": 0.8, "passed": True},
            published_baseline=0.553,
            llm_unique_calls=budget,
            graph_ga_unique_calls=budget,
        )

    monkeypatch.setattr(beat_mod, "run_head_to_head", fake_h2h)
    rc = main(["--task", "jnk3", "--budget", "1500", "--seed", "42", "--head-to-head"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["head_to_head"] is True
    assert report["task"] == "jnk3"
    assert report["beat"] is True
    assert report["llm_auc"] == 0.61 and report["graph_ga_auc"] == 0.55
    assert report["published_baseline"] == 0.553
    assert report["llm_valid_gate"] == {"threshold": 0.8, "passed": True}
    assert "wall_seconds" in report
    assert report["seed"] == 42
    assert report["budget"] == 1500
    assert report["diff"] == 0.06
    assert report["llm_valid_rate"] == 0.9
    assert report["llm_unique_calls"] == 1500
    assert report["graph_ga_unique_calls"] == 1500


def test_cli_analyzer_verdict_report(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # Stub the verdict so the CLI test runs no eval and makes no DeepSeek call —
    # the wiring (flag -> run_analyzer_verdict -> report + verdict string) is under test.
    from capychem.eval import verdict as verdict_mod
    from capychem.eval.verdict import AnalyzerVerdict

    def fake_verdict(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.72, without_auc=0.66, diff=0.06, helps=True,
            analyzer_parse_rate=0.95, analyzer_calls=20, analyzer_parsed=19,
            parse_rate_healthy=True,
            with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=2600, without_unique_calls=3100,
        )

    monkeypatch.setattr(verdict_mod, "run_analyzer_verdict", fake_verdict)
    rc = main(["--task", "jnk3", "--budget", "10000", "--seed", "42", "--analyzer-verdict"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["analyzer_verdict"] is True
    assert report["task"] == "jnk3" and report["seed"] == 42 and report["budget"] == 10000
    assert report["with_auc"] == 0.72 and report["without_auc"] == 0.66
    assert report["diff"] == 0.06 and report["helps"] is True
    assert report["analyzer_parse_rate"] == 0.95 and report["parse_rate_healthy"] is True
    assert report["analyzer_calls"] == 20 and report["analyzer_parsed"] == 19
    assert report["with_unique_calls"] == 2600 and report["without_unique_calls"] == 3100
    assert "ADDS value" in report["verdict"]
    assert "wall_seconds" in report


def test_cli_analyzer_verdict_invalid_when_parse_rate_unhealthy(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import verdict as verdict_mod
    from capychem.eval.verdict import AnalyzerVerdict

    def fake_verdict(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.50, without_auc=0.55, diff=-0.05, helps=False,
            analyzer_parse_rate=0.40, analyzer_calls=20, analyzer_parsed=8,
            parse_rate_healthy=False,
            with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=2600, without_unique_calls=3100,
        )

    monkeypatch.setattr(verdict_mod, "run_analyzer_verdict", fake_verdict)
    rc = main(["--task", "jnk3", "--budget", "10000", "--seed", "42", "--analyzer-verdict"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    # an unhealthy parse-rate must read INVALID, never as a clean null
    assert report["parse_rate_healthy"] is False
    assert "INVALID" in report["verdict"]


def test_cli_analyzer_verdict_null_pivot(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    # Healthy parse-rate but the analyzer does NOT help (with_auc <= without_auc):
    # the verdict must read NULL/pivot — the kill-switch's analyzer-only outcome.
    from capychem.eval import verdict as verdict_mod
    from capychem.eval.verdict import AnalyzerVerdict

    def fake_verdict(task, budget, seed, **kw):  # type: ignore[no-untyped-def]
        return AnalyzerVerdict(
            task=task, seed=seed, budget=budget,
            with_auc=0.60, without_auc=0.64, diff=-0.04, helps=False,
            analyzer_parse_rate=0.96, analyzer_calls=20, analyzer_parsed=19,
            parse_rate_healthy=True,
            with_valid_rate=0.98, without_valid_rate=0.97,
            with_unique_calls=2600, without_unique_calls=3100,
        )

    monkeypatch.setattr(verdict_mod, "run_analyzer_verdict", fake_verdict)
    rc = main(["--task", "jnk3", "--budget", "10000", "--seed", "42", "--analyzer-verdict"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["parse_rate_healthy"] is True and report["helps"] is False
    assert "NULL" in report["verdict"] and "pivot" in report["verdict"]


def test_capture_analyzer_traces_mode_emits_traces(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import cli as cli_mod
    from capychem.eval.runner import ReproResult
    from capychem.eval.trace import GenerationTrace

    def fake_run(task, budget, seed, *, trace_sink=None, **kw):  # type: ignore[no-untyped-def]
        assert trace_sink is not None  # capture mode must pass a sink
        trace_sink.append(GenerationTrace(
            generation=2, summary_top=[("CCO", 0.5)], summary_bottom=[],
            recent_top10_means=[0.5], prior_structured=None, analyzer_raw="raw",
            analyzer_structured={"focus": "f", "avoid": []},
            prompt_used="cond", prompt_unconditioned="plain",
        ))
        return ReproResult(mol_buffer={"CCO": (0.5, 1)}, generations=2, unique_calls=1,
                           analyzer_calls=1, analyzer_parsed=1, analyzer_parse_rate=1.0)

    monkeypatch.setattr(cli_mod, "run_reproduction", fake_run)
    rc = cli_mod.main(["--task=jnk3", "--budget=300", "--seed=42",
                       "--mutation-strategy=llm", "--capture-analyzer-traces"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["task"] == "jnk3"
    assert out["analyzer_calls"] == 1
    assert out["traces"][0]["analyzer_structured"] == {"focus": "f", "avoid": []}
    assert out["traces"][0]["prompt_used"] == "cond"


def test_cli_all_default_mode_reproduce(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport, SweepRow

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(
            mode=mode, budget=budget, seed=seed, tasks_run=1, tasks_failed=0,
            auc_sum=0.94, published_sum=13.751, beats=None,
            rows=[SweepRow(task="qed", ok=True, headline_auc=0.94, beat=None,
                           payload={"auc_top10": 0.94})],
        )

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--budget", "200", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sweep"] is True
    assert captured["mode"] == "reproduce"
    assert report["mode"] == "reproduce"
    assert report["published_sum"] == 13.751
    assert report["beats"] is None
    assert report["rows"][0]["task"] == "qed"
    assert "wall_seconds" in report


def test_cli_all_selects_analyzer_verdict_mode(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(mode=mode, budget=budget, seed=seed, tasks_run=0,
                           tasks_failed=0, auc_sum=0.0, published_sum=13.751,
                           beats=0, rows=[])

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--analyzer-verdict", "--budget", "10000", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert captured["mode"] == "analyzer_verdict"
    assert report["mode"] == "analyzer_verdict"


def test_cli_all_selects_head_to_head_mode(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        return SweepReport(mode=mode, budget=budget, seed=seed, tasks_run=0,
                           tasks_failed=0, auc_sum=0.0, published_sum=13.751,
                           beats=0, rows=[])

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--head-to-head", "--budget", "1500", "--seed", "42"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "head_to_head"
    assert captured["mode"] == "head_to_head"


def test_cli_all_selects_week8_and_passes_tasks(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from capychem.eval import sweep as sweep_mod
    from capychem.eval.sweep import SweepReport, SweepRow

    captured: dict = {}

    def fake_sweep(tasks=None, *, budget, seed, mode, **kw):  # type: ignore[no-untyped-def]
        captured["mode"] = mode
        captured["tasks"] = tasks
        return SweepReport(
            mode=mode, budget=budget, seed=seed, tasks_run=1, tasks_failed=0,
            auc_sum=0.6, published_sum=0.553, beats=1,
            rows=[SweepRow(task="jnk3", ok=True, headline_auc=0.6, beat=True,
                           payload={"beat": True,
                                    "llm_valid_gate": {"threshold": 0.8, "passed": True},
                                    "parse_rate_healthy": True})],
        )

    monkeypatch.setattr(sweep_mod, "run_sweep", fake_sweep)
    rc = main(["--all", "--week8", "--tasks", "jnk3,median1", "--budget", "10000", "--seed", "42"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert captured["mode"] == "week8"
    assert captured["tasks"] == ("jnk3", "median1")
    assert report["mode"] == "week8"
    # week8 verdict keys are merged into the sweep output
    assert report["trustworthy_beats"] == 1
    assert "week8_verdict" in report and "on_track" in report


def test_cli_tasks_rejects_unknown_task(capsys) -> None:  # type: ignore[no-untyped-def]
    import pytest as _pytest
    with _pytest.raises(SystemExit):
        main(["--all", "--week8", "--tasks", "jnk3,not_a_real_task", "--budget", "10000"])
    assert "not_a_real_task" in capsys.readouterr().err


def test_cli_week8_requires_all(capsys) -> None:  # type: ignore[no-untyped-def]
    import pytest as _pytest
    with _pytest.raises(SystemExit):
        main(["--week8", "--task", "jnk3", "--budget", "10000"])
    assert "--all" in capsys.readouterr().err
