from capychem.eval.tasks import PMO_TASKS


def test_registry_has_23_unique_tasks() -> None:
    assert len(PMO_TASKS) == 23
    assert len(set(PMO_TASKS)) == 23


def test_registry_first_entry_is_qed_and_contains_milestone02_tasks() -> None:
    assert PMO_TASKS[0] == "qed"
    assert "jnk3" in PMO_TASKS
    assert "drd2" in PMO_TASKS  # a real PMO task that used to be the "unknown" fixture
