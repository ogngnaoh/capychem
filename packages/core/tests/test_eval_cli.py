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
