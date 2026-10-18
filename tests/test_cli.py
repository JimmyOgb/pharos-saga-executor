"""
Unit and integration tests for scripts/saga.py CLI.
"""

import argparse
import io
import json
import sys
from scripts.saga import cmd_demo, cmd_run


def test_cli_demo_stdout(capsys):
    args = argparse.Namespace(
        json=False,
        verbose=False,
        live_preflight=False,
    )
    code = cmd_demo(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "EXECUTING TASK 6 DUAL-OUTCOME DEMONSTRATION SUITE" in captured.out
    assert "Scenario A: Happy Path" in captured.out
    assert "Scenario B: Forced Step 3 Failure" in captured.out
    assert "Status: COMPLETED" in captured.out
    assert "Status: ROLLED_BACK" in captured.out


def test_cli_demo_json(capsys):
    args = argparse.Namespace(
        json=True,
        verbose=False,
        live_preflight=False,
    )
    code = cmd_demo(args)
    captured = capsys.readouterr()

    assert code == 0
    data = json.loads(captured.out)
    assert "scenario_a_happy_path" in data
    assert "scenario_b_forced_failure" in data
    assert data["scenario_a_happy_path"]["status"] == "COMPLETED"
    assert data["scenario_b_forced_failure"]["status"] == "ROLLED_BACK"


def test_cli_run_happy_path(capsys):
    args = argparse.Namespace(
        saga_id="test_cli_run",
        force_fail_step=None,
        fail_compensation=False,
        transient_retries=0,
        live_preflight=False,
        verbose=False,
        json=False,
    )
    code = cmd_run(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "[FINAL STATUS]: COMPLETED" in captured.out
    assert "Steps Succeeded: 3/3" in captured.out


def test_cli_run_forced_failure_rolls_back(capsys):
    args = argparse.Namespace(
        saga_id="test_cli_fail",
        force_fail_step=3,
        fail_compensation=False,
        transient_retries=0,
        live_preflight=False,
        verbose=False,
        json=False,
    )
    code = cmd_run(args)
    captured = capsys.readouterr()

    assert code == 0  # Clean rollback is an orderly terminal state
    assert "[FINAL STATUS]: ROLLED_BACK" in captured.out
    assert "Steps Compensated: 2" in captured.out


def test_cli_run_compensation_failure_returns_error_code(capsys):
    args = argparse.Namespace(
        saga_id="test_cli_comp_fail",
        force_fail_step=3,
        fail_compensation=True,
        transient_retries=0,
        live_preflight=False,
        verbose=False,
        json=False,
    )
    code = cmd_run(args)
    captured = capsys.readouterr()

    assert code == 1  # Abnormal condition
    assert "[FINAL STATUS]: MANUAL_RECOVERY_REQUIRED" in captured.out
    assert "MANUAL RECOVERY REQUIRED!" in captured.out
