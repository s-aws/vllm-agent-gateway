from pathlib import Path

from scripts.run_regression import (
    PARALLEL_MARK_EXPR,
    SERIAL_MARK_EXPR,
    SUMMARY_PREFIX,
    build_commands,
    build_parser,
    main,
)


def test_regression_runner_defaults_to_parallel_then_serial_lanes() -> None:
    args = build_parser().parse_args([])

    commands = build_commands(args, python="python")

    assert [command.name for command in commands] == [
        "parallel_safe_regression",
        "serial_regression",
    ]
    assert commands[0].command == (
        "python",
        "-m",
        "pytest",
        "tests/regression",
        "-m",
        PARALLEL_MARK_EXPR,
        "-n",
        "4",
        "--dist",
        "loadfile",
        "--max-worker-restart=0",
    )
    assert commands[1].command == (
        "python",
        "-m",
        "pytest",
        "tests/regression",
        "-m",
        SERIAL_MARK_EXPR,
    )


def test_regression_runner_lane_switches_and_extra_pytest_args() -> None:
    parallel_args = build_parser().parse_args(["--parallel-only", "--workers", "2", "--", "--maxfail=1"])
    serial_args = build_parser().parse_args(["--serial-only", "--", "--tb=short"])

    parallel_commands = build_commands(parallel_args, python="py")
    serial_commands = build_commands(serial_args, python="py")

    assert [command.name for command in parallel_commands] == ["parallel_safe_regression"]
    assert "-n" in parallel_commands[0].command
    assert parallel_commands[0].command[parallel_commands[0].command.index("-n") + 1] == "2"
    assert "--dist" in parallel_commands[0].command
    assert parallel_commands[0].command[parallel_commands[0].command.index("--dist") + 1] == "loadfile"
    assert parallel_commands[0].command[-1] == "--maxfail=1"
    assert [command.name for command in serial_commands] == ["serial_regression"]
    assert "--tb=short" in serial_commands[0].command


def test_regression_runner_accepts_per_run_basetemp() -> None:
    args = build_parser().parse_args(["--workers", "2"])

    commands = build_commands(args, python="py", run_basetemp=Path("tmp") / "run-1")

    assert commands[0].command[-2:] == ("--basetemp", str(Path("tmp") / "run-1" / "parallel"))
    assert commands[1].command[-2:] == ("--basetemp", str(Path("tmp") / "run-1" / "serial"))


def test_regression_runner_dry_run_does_not_require_xdist(capsys) -> None:
    exit_code = main(["--dry-run", "--workers", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "parallel_safe_regression:" in captured.out
    assert "-n 2" in captured.out
    assert "serial_regression:" in captured.out
    assert SUMMARY_PREFIX in captured.out
