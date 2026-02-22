#!/usr/bin/env python3
"""Automate VulnBot evaluation with PTY-style interaction and full logging."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pexpect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run auto-pen-bench reset + VulnBot interactive evaluation with full logs."
    )
    parser.add_argument("--level", required=True, help="e.g. real-world or in-vitro")
    parser.add_argument("--category", required=True, help="e.g. cve or web_security")
    parser.add_argument("--vm-id", type=int, help="Single target VM id, e.g. 1")
    parser.add_argument("--all-vms", action="store_true", help="Run all VMs in selected level/category")
    parser.add_argument("--run-index", default=1, type=int, help="Start log index suffix")
    parser.add_argument("--run-count", default=1, type=int, help="Number of repeated runs")
    parser.add_argument("--max-interactions", "-m", default=6, type=int, help="VulnBot -m value")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="VulnBot repository root",
    )
    parser.add_argument(
        "--bench-reset-script",
        default="/home/younglee/auto-pen-bench/run_eval.sh",
        help="Absolute path to auto-pen-bench reset script",
    )
    parser.add_argument(
        "--games-file",
        default="games.json",
        help="Path to games.json relative to repo-root (or absolute path)",
    )
    return parser.parse_args()


def resolve_games_path(repo_root: Path, games_file: str) -> Path:
    games_path = Path(games_file)
    if not games_path.is_absolute():
        games_path = repo_root / games_path
    return games_path


def load_scenarios(games_path: Path, level: str, category: str) -> list[dict[str, Any]]:
    with games_path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    try:
        return data[level][category]
    except KeyError as exc:
        raise ValueError(f"Invalid level/category: {level}/{category}") from exc


def build_vm_task_map(
    scenarios: list[dict[str, Any]], level: str, category: str
) -> dict[int, str]:
    vm_task_map: dict[int, str] = {}
    pattern = re.compile(rf"^{re.escape(level)}_{re.escape(category)}_vm(\d+)$")

    for scenario in scenarios:
        target = scenario.get("target")
        task = scenario.get("task")

        if not isinstance(target, str):
            continue
        match = pattern.match(target)
        if not match:
            continue
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"Task is empty for target: {target}")

        vm_id = int(match.group(1))
        vm_task_map[vm_id] = task

    if not vm_task_map:
        raise ValueError(f"No VM task targets found for: {level}/{category}")
    return vm_task_map


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def _strip_backspaces(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch == "\b":
            if out:
                out.pop()
            continue
        out.append(ch)
    return "".join(out)


def clean_terminal_text(text: str, keep_carriage_return: bool = False) -> str:
    # OSC sequences: ESC ] ... BEL or ESC \
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    # CSI sequences and other 7-bit C1 escape sequences.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b[@-Z\\-_]", "", text)
    text = _strip_backspaces(text)
    if keep_carriage_return:
        text = text.replace("\r\n", "\n")
    else:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Keep newline/tab, strip other control chars.
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text


class CleanLogWriter:
    def __init__(self, fp) -> None:
        self.fp = fp

    def write(self, data: str) -> None:
        self.fp.write(clean_terminal_text(data))

    def flush(self) -> None:
        self.fp.flush()


class TeeCleanWriter:
    def __init__(self, log_fp, stream) -> None:
        self.log_fp = log_fp
        self.stream = stream
        self._spinner_seen = False
        self._last_log_line = ""
        self._suppress_task_echo = False
        self._task_compact = ""
        self._describe_prompt_seen = False

    def write(self, data: str) -> None:
        # Log: normalize CR to newline for readability and pass through line filters.
        cleaned_for_log = clean_terminal_text(data, keep_carriage_return=False)
        cleaned_for_log = self._clean_for_log(cleaned_for_log)
        # Terminal: keep CR so spinner updates the same line instead of flooding lines.
        cleaned_for_stream = clean_terminal_text(data, keep_carriage_return=True)
        cleaned_for_stream = self._dedupe_spinner(cleaned_for_stream)
        if cleaned_for_log:
            self.log_fp.write(cleaned_for_log)
        if cleaned_for_stream:
            self.stream.write(cleaned_for_stream)

    def flush(self) -> None:
        self.log_fp.flush()
        self.stream.flush()

    def _dedupe_spinner(self, text: str) -> str:
        spinner_phrase = "Initializing DeepPentest Sessions..."
        spinner_end_markers = ("Plan Initialized.", "Before you quit")
        spinner_pattern = r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*Initializing DeepPentest Sessions\.\.\."

        has_spinner = (spinner_phrase in text) or re.search(spinner_pattern, text) is not None
        if has_spinner:
            # Remove all spinner frames from terminal stream.
            text = re.sub(spinner_pattern, "", text)
            text = text.replace(spinner_phrase, "")
            if not self._spinner_seen:
                # Show a single stable line for this spinner phase.
                text = "[INFO] Initializing DeepPentest Sessions...\n" + text
                self._spinner_seen = True

        if any(marker in text for marker in spinner_end_markers):
            self._spinner_seen = False

        return text

    def set_task_echo_filter(self, task: str) -> None:
        self._task_compact = re.sub(r"\s+", "", task).lower()
        self._suppress_task_echo = True
        self._describe_prompt_seen = False

    def _clean_for_log(self, text: str) -> str:
        out_lines: list[str] = []
        spinner_pattern = r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*Initializing DeepPentest Sessions\.\.\.\s*$"
        ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\s")

        for raw_line in text.splitlines(keepends=True):
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            # Collapse spinner frames to one line in log.
            if stripped == "Initializing DeepPentest Sessions..." or re.match(spinner_pattern, stripped):
                if not self._spinner_seen:
                    out_lines.append("[INFO] Initializing DeepPentest Sessions...\n")
                    self._spinner_seen = True
                    self._last_log_line = "[INFO] Initializing DeepPentest Sessions..."
                continue
            if "Plan Initialized." in line:
                self._spinner_seen = False
                self._suppress_task_echo = False

            # Track prompt display and remove noisy redraw of task echo.
            if "Please describe the penetration testing task." in line:
                if not self._describe_prompt_seen:
                    out_lines.append("Please describe the penetration testing task.\n")
                    self._last_log_line = "Please describe the penetration testing task."
                    self._describe_prompt_seen = True
                continue
            if stripped == ">":
                if self._describe_prompt_seen:
                    out_lines.append(">\n")
                    self._last_log_line = ">"
                continue

            # After task is submitted, prompt_toolkit can emit fragmented redraw echoes.
            # Suppress all mid-phase echo noise until real runtime output begins.
            if self._suppress_task_echo:
                if (
                    "Plan Initialized." in line
                    or "Before you quit" in line
                    or ts_pattern.match(stripped) is not None
                ):
                    self._suppress_task_echo = False
                else:
                    # Keep spinner summary line already handled above; drop other lines.
                    continue

            if self._suppress_task_echo and self._task_compact:
                compact = re.sub(r"\s+", "", line).lower()
                if compact and (
                    compact in self._task_compact or self._task_compact.startswith(compact[: min(len(compact), 32)])
                ):
                    continue
                if "[?25" in line:
                    continue

            # Remove empty-line spam.
            if stripped == "":
                continue

            # De-duplicate consecutive identical lines.
            if line == self._last_log_line:
                continue

            out_lines.append(line + "\n")
            self._last_log_line = line

        return "".join(out_lines)


def write_event(log_file, message: str) -> None:
    line = f"{message}\n"
    log_file.write(line)
    sys.stdout.write(line)
    log_file.flush()
    sys.stdout.flush()


def normalize_task_for_prompt(task: str) -> str:
    # prompt_toolkit input is line-based; embedded newlines can leak into later prompts.
    return " ".join(task.splitlines()).strip()


def send_human_input(child: pexpect.spawn, text: str, char_delay: float = 0.006) -> None:
    for ch in text:
        child.send(ch)
        time.sleep(char_delay)


def run_reset(
    log_file,
    reset_script: str,
    level: str,
    category: str,
    vm_id: int,
    repo_root: Path,
) -> None:
    cmd = [reset_script, level, category, str(vm_id)]
    write_event(log_file, f"[{now_str()}] [STEP 1] Reset environment: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=Path(reset_script).resolve().parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        cleaned = clean_terminal_text(line)
        log_file.write(cleaned)
        sys.stdout.write(cleaned)
        sys.stdout.flush()
    ret = proc.wait()
    write_event(log_file, f"[{now_str()}] [STEP 1] Exit code: {ret}")

    if ret != 0:
        raise RuntimeError(f"Reset script failed with exit code {ret}")

    if not repo_root.exists():
        raise RuntimeError(f"Repo root not found: {repo_root}")


def run_vulnbot_with_pty(log_file, repo_root: Path, max_interactions: int, task: str) -> None:
    cmd = f"uv run python cli.py vulnbot -m {max_interactions}"
    write_event(log_file, f"[{now_str()}] [STEP 2] Start VulnBot: {cmd}")

    child = pexpect.spawn(
        "/bin/zsh",
        ["-lc", cmd],
        cwd=str(repo_root),
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PROMPT_TOOLKIT_NO_CPR": "1",
            "TERM": "xterm-256color",
            "COLUMNS": "160",
            "LINES": "48",
        },
        encoding="utf-8",
        codec_errors="ignore",
        timeout=None,
    )

    # Log only process output here with ANSI/control-code filtering.
    tee_writer = TeeCleanWriter(log_file, sys.stdout)
    child.logfile_read = tee_writer

    # Use strict sequential interaction to avoid prompt_toolkit redraw re-matching.
    child.expect(r"Do you want to continue from a previous session\??", timeout=600)
    # prompt_toolkit confirm consumes a single key; avoid extra newline leaking to next prompt.
    child.send("n")
    write_event(log_file, "[AUTO] continue_from_previous=n")

    prompt_task = normalize_task_for_prompt(task)
    tee_writer.set_task_echo_filter(prompt_task)
    child.expect(r"Please describe the penetration testing task\.", timeout=600)
    # Give prompt_toolkit a brief moment to settle cursor redraw before typing.
    time.sleep(0.15)
    send_human_input(child, prompt_task)
    child.send("\r")
    write_event(log_file, f"[AUTO] task_input={strip_ansi(prompt_task)}")

    child.expect(r"Before you quit, you may want to save the current session\.", timeout=7200)
    child.expect(
        r"Please enter the name of the current session\. \(Default with current timestamp\)",
        timeout=7200,
    )
    # Clear any leaked buffered input, then submit empty to use default timestamp.
    child.sendcontrol("u")
    time.sleep(0.1)
    child.send("\r")
    write_event(log_file, "[AUTO] session_name=<ENTER>")

    child.expect(pexpect.EOF, timeout=7200)

    child.close()
    write_event(log_file, f"[{now_str()}] [STEP 2] VulnBot exit status: {child.exitstatus}")

    if child.exitstatus not in (0, None):
        raise RuntimeError(f"VulnBot exited abnormally with status {child.exitstatus}")


def main() -> int:
    args = parse_args()

    repo_root = Path(args.repo_root).resolve()
    games_path = resolve_games_path(repo_root, args.games_file)

    if not games_path.exists():
        raise FileNotFoundError(f"games.json not found: {games_path}")
    if not Path(args.bench_reset_script).exists():
        raise FileNotFoundError(f"reset script not found: {args.bench_reset_script}")

    if args.run_count < 1:
        raise ValueError("--run-count must be >= 1")
    if args.run_index < 1:
        raise ValueError("--run-index must be >= 1")
    if args.all_vms and args.vm_id is not None:
        raise ValueError("Use either --vm-id or --all-vms, not both")
    if not args.all_vms and args.vm_id is None:
        raise ValueError("Please set --vm-id for single machine run, or use --all-vms")

    scenarios = load_scenarios(games_path, args.level, args.category)
    vm_task_map = build_vm_task_map(scenarios, args.level, args.category)
    vm_ids = sorted(vm_task_map.keys()) if args.all_vms else [int(args.vm_id)]

    log_dir = repo_root / "evaluate"
    log_dir.mkdir(parents=True, exist_ok=True)
    generated_logs: list[Path] = []
    total_jobs = len(vm_ids) * args.run_count
    job_idx = 0
    for vm_id in vm_ids:
        if vm_id not in vm_task_map:
            raise ValueError(f"Target not found in games.json: {args.level}_{args.category}_vm{vm_id}")
        task = vm_task_map[vm_id]

        for i in range(args.run_count):
            job_idx += 1
            current_run_index = args.run_index + i
            log_name = f"{args.level}_VM-{vm_id}_{current_run_index}.log"
            log_path = log_dir / log_name

            with log_path.open("w", encoding="utf-8") as log_file:
                write_event(log_file, f"[{now_str()}] Evaluation start")
                write_event(log_file, f"[{now_str()}] Level/Category/VM: {args.level}/{args.category}/{vm_id}")
                write_event(log_file, f"[{now_str()}] Job progress: {job_idx}/{total_jobs}")
                write_event(
                    log_file,
                    f"[{now_str()}] VM run progress: {i + 1}/{args.run_count} (log index {current_run_index})",
                )
                write_event(log_file, f"[{now_str()}] Task target source: {games_path}")
                write_event(log_file, f"[{now_str()}] Log path: {log_path}")

                run_reset(
                    log_file=log_file,
                    reset_script=args.bench_reset_script,
                    level=args.level,
                    category=args.category,
                    vm_id=vm_id,
                    repo_root=repo_root,
                )
                run_vulnbot_with_pty(
                    log_file=log_file,
                    repo_root=repo_root,
                    max_interactions=args.max_interactions,
                    task=task,
                )
                write_event(log_file, f"[{now_str()}] Evaluation finished")

            generated_logs.append(log_path)
            print(f"[{job_idx}/{total_jobs}] Completed. Full log saved to: {log_path}")

    print("All runs completed:")
    for p in generated_logs:
        print(f"- {p}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
