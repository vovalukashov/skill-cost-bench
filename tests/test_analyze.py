from __future__ import annotations

from bench.analyze import collect


def _row(arm: str, **kw) -> dict:
    row = {"arm": arm, "valid": True, "solved": True}
    row.update(kw)
    return row


def test_a_prompted_use_is_counted_apart_from_a_spontaneous_one():
    """The tool's own hook talking is not the model reaching for the tool.

    The stock install pushes 'query the graph first' into the session before
    every read. Reporting only the activation rate would score the hook's
    reminder as a decision the model made, which is the whole difference
    between 'the skill works' and 'the skill has to be forced'.
    """
    rows = [
        _row("graphify", activation_status="used", nudged=True),
        _row("graphify", activation_status="used", nudged=False),
        _row("graphify", activation_status="available_unused", nudged=True),
        _row("control"),
    ]
    per_arm = collect(rows)["per_arm"]

    assert per_arm["graphify"]["used_skill"] == 2
    assert per_arm["graphify"]["nudged"] == 2
    # Used it without ever being told to: the only unprompted use here.
    assert per_arm["graphify"]["used_unprompted"] == 1
    # Told to and still did not: the interesting failure.
    assert per_arm["graphify"]["nudged_unused"] == 1
    assert per_arm["control"]["nudged"] == 0


def test_a_run_without_nudge_tracking_reports_zero_rather_than_guessing():
    per_arm = collect([_row("graphify", activation_status="used")])["per_arm"]
    assert per_arm["graphify"]["nudged"] == 0
    assert per_arm["graphify"]["used_unprompted"] == 1


def test_the_experimental_arm_can_be_named_when_a_sweep_carries_several():
    """One sweep, two variants of the same tool, compared against one control.

    Running the stock install and the strict install as separate sweeps costs
    twice the control runs and compares them against different days. Keeping
    all three arms in one sweep and analysing each pair in turn shares the
    control and holds the conditions fixed.
    """
    from bench.analyze import pick_arms
    from bench.config import ArmConfig

    arms = [
        ArmConfig(name="control", forbidden_patterns=["graphify"]),
        ArmConfig(name="graphify-stock", activation_patterns=["graphify query"]),
        ArmConfig(name="graphify-strict", activation_patterns=["graphify query"]),
    ]
    assert pick_arms(arms) == ("control", "graphify-stock")
    assert pick_arms(arms, "graphify-strict") == ("control", "graphify-strict")

    try:
        pick_arms(arms, "graphify-typo")
    except SystemExit as exc:
        assert "graphify-stock" in str(exc) and "graphify-strict" in str(exc)
    else:
        raise AssertionError("an unknown arm name must not silently fall back")


def test_a_second_pair_writes_its_own_report_instead_of_overwriting_the_first(tmp_path):
    """Two pairs from one sweep are two reports, not one report twice.

    Naming both files `report.md` would leave the last analysis standing and
    silently destroy the first, which is the kind of quiet overwrite that turns
    into a wrong number in an article.
    """
    from bench.analyze import report_paths

    assert report_paths(tmp_path, "control", "graphify-stock", explicit=False) == (
        tmp_path / "summary.json", tmp_path / "report.md")
    assert report_paths(tmp_path, "control", "graphify-strict", explicit=True) == (
        tmp_path / "summary.graphify-strict.json", tmp_path / "report.graphify-strict.md")
