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
