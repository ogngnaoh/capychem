import capychem.env as env


def test_load_local_env_sets_vars(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    envfile = tmp_path / ".env.local"
    envfile.write_text("CAPYCHEM_TEST_KEY=hello\n")
    monkeypatch.delenv("CAPYCHEM_TEST_KEY", raising=False)
    env.load_local_env(path=envfile)
    import os
    assert os.environ["CAPYCHEM_TEST_KEY"] == "hello"


def test_load_local_env_missing_file_is_noop(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # must not raise when the file is absent
    env.load_local_env(path=tmp_path / "nope.env")


def test_load_local_env_is_idempotent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    envfile = tmp_path / ".env.local"
    envfile.write_text("CAPYCHEM_TEST_KEY=one\n")
    monkeypatch.delenv("CAPYCHEM_TEST_KEY", raising=False)
    env.load_local_env(path=envfile)
    env.load_local_env(path=envfile)  # second call must not raise
    import os
    assert os.environ["CAPYCHEM_TEST_KEY"] == "one"
