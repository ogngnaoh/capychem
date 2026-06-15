import json

from capychem.eval.cli import main


def test_cli_emits_report(capsys) -> None:  # type: ignore[no-untyped-def]
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
