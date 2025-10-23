from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .logging import log_event
from .state import load_session, update_session, ensure_session
from .time import utc_timestamp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BIN_DIR = PROJECT_ROOT / "bin"

ALLOWED_TOOLS = {
    "tool_status",
    "tool_circle",
    "tool_figure8",
    "tool_stop",
    "tool_voice",
    "tool_weather",
}

TOOL_COMMANDS = {
    "tool_status": BIN_DIR / "tool-status",
    "tool_circle": BIN_DIR / "tool-circle",
    "tool_figure8": BIN_DIR / "tool-figure8",
    "tool_stop": BIN_DIR / "tool-stop",
    "tool_voice": BIN_DIR / "tool-voice",
    "tool_weather": BIN_DIR / "tool-weather",
}


class VoiceLoopError(Exception):
    """Domain-specific errors."""


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex-driven PiCar-X voice assistant loop")
    parser.add_argument(
        "--prompt",
        default=str(PROJECT_ROOT / "docs/prompts/codex-voice-system.md"),
        help="Path to the system prompt file",
    )
    parser.add_argument(
        "--input-mode",
        choices=["text", "voice"],
        default="text",
        help="How to capture user input (default: text)",
    )
    parser.add_argument(
        "--transcriber-cmd",
        help="Command used to transcribe microphone input when --input-mode=voice",
    )
    parser.add_argument(
        "--codex-cmd",
        default=os.environ.get("CODEX_CHAT_CMD", "codex chat --model gpt-4.1-mini --input -"),
        help="Command used to invoke the Codex CLI",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Maximum conversation turns before exiting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force PX_DRY=1 for all tool executions",
    )
    parser.add_argument(
        "--auto-log",
        action="store_true",
        help="Append full Codex responses to logs/voice-loop.log for auditing",
    )
    parser.add_argument(
        "--exit-on-stop",
        action="store_true",
        help="Exit loop immediately after a successful tool_stop call",
    )
    return parser.parse_args(argv)


def read_prompt(path: Path) -> str:
    if not path.exists():
        raise VoiceLoopError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def capture_text_input() -> Optional[str]:
    try:
        line = input("You> ").strip()
    except EOFError:
        return None
    if not line:
        return None
    return line


def capture_voice_input(cmd_spec: str) -> Optional[str]:
    if not cmd_spec:
        raise VoiceLoopError("voice mode requested but --transcriber-cmd not provided")
    command = shlex.split(cmd_spec)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise VoiceLoopError(
            f"transcription failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    text = result.stdout.strip()
    return text or None


def build_model_prompt(system_prompt: str, state: Dict[str, Any], user_text: str) -> str:
    state_copy = {k: v for k, v in state.items() if k != "history"}
    return (
        f"{system_prompt}\n\n"
        f"Current state: {json.dumps(state_copy, indent=2)}\n"
        f"User transcript: {user_text}\n"
        f"Respond with a single JSON object as instructed."
    )


def run_codex(command_spec: str, prompt: str) -> Tuple[int, str, str]:
    command = shlex.split(command_spec)
    result = subprocess.run(
        command,
        input=prompt,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def extract_action(text: str) -> Optional[Dict[str, Any]]:
    for line in reversed(text.strip().splitlines()):
        candidate = line.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            return data
    return None


def parse_tool_payload(raw: str) -> Optional[Dict[str, Any]]:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError:
        return None

def validate_action(action: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    tool = action.get("tool")
    if tool not in ALLOWED_TOOLS:
        raise VoiceLoopError(f"unsupported tool requested: {tool}")

    params = action.get("params", {})
    sanitized: Dict[str, Any] = {}

    if tool == "tool_circle":
        speed = int(float(params.get("speed", 30)))
        duration = float(params.get("duration", 6))
        if not (0 <= speed <= 60):
            raise VoiceLoopError("tool_circle speed out of range")
        if not (1 <= duration <= 12):
            raise VoiceLoopError("tool_circle duration out of range")
        sanitized["PX_SPEED"] = str(speed)
        sanitized["PX_DURATION"] = f"{duration:.2f}"
    elif tool == "tool_figure8":
        speed = int(float(params.get("speed", 30)))
        duration = float(params.get("duration", 6))
        rest = float(params.get("rest", 1.5))
        if not (0 <= speed <= 60):
            raise VoiceLoopError("tool_figure8 speed out of range")
        if not (1 <= duration <= 12):
            raise VoiceLoopError("tool_figure8 duration out of range")
        if not (0 <= rest <= 5):
            raise VoiceLoopError("tool_figure8 rest out of range")
        sanitized["PX_SPEED"] = str(speed)
        sanitized["PX_DURATION"] = f"{duration:.2f}"
        sanitized["PX_REST"] = f"{rest:.2f}"
    elif tool == "tool_voice":
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            raise VoiceLoopError("tool_voice requires a non-empty text parameter")
        if len(text) > 180:
            text = text[:180]
        sanitized["PX_TEXT"] = text
    else:
        if params:
            raise VoiceLoopError("unexpected parameters for tool")

    return tool, sanitized


def execute_tool(tool: str, env_overrides: Dict[str, str], dry_mode: bool) -> Tuple[int, str, str]:
    command_path = TOOL_COMMANDS[tool]
    if not command_path.exists():
        raise VoiceLoopError(f"tool command missing: {command_path}")

    env = os.environ.copy()
    env.setdefault("PROJECT_ROOT", str(PROJECT_ROOT))
    env_overrides = dict(env_overrides)
    env["PX_DRY"] = "1" if dry_mode else env_overrides.pop("PX_DRY", "0")
    for key, value in env_overrides.items():
        env[key] = value

    result = subprocess.run(
        [str(command_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def supervisor_loop(args: argparse.Namespace) -> None:
    ensure_session()
    system_prompt = read_prompt(Path(args.prompt))

    for turn in range(1, args.max_turns + 1):
        session = load_session()
        update_session(fields={"watchdog_heartbeat_ts": utc_timestamp()})

        if args.input_mode == "text":
            user_text = capture_text_input()
        else:
            user_text = capture_voice_input(args.transcriber_cmd)

        if not user_text:
            print("[voice-loop] No input, exiting.")
            break

        prompt = build_model_prompt(system_prompt, session, user_text)
        rc, stdout, stderr = run_codex(args.codex_cmd, prompt)
        if args.auto_log:
            log_event(
                "voice-loop",
                {
                    "turn": turn,
                    "model_rc": rc,
                    "stdout": stdout[-4000:],
                    "stderr": stderr[-4000:],
                },
            )

        if rc != 0:
            print(f"[voice-loop] Codex CLI exited with {rc}: {stderr.strip()}")
            continue

        action = extract_action(stdout)
        if not action:
            print("[voice-loop] No JSON action detected; ignoring response.")
            continue

        try:
            tool, env_overrides = validate_action(action)
        except VoiceLoopError as exc:
            print(f"[voice-loop] Invalid action: {exc}")
            continue

        try:
            rc_tool, tool_stdout, tool_stderr = execute_tool(tool, env_overrides, args.dry_run)
        except VoiceLoopError as exc:
            print(f"[voice-loop] Execution error: {exc}")
            continue

        log_event(
            "voice-loop",
            {
                "turn": turn,
                "tool": tool,
                "returncode": rc_tool,
                "dry": args.dry_run,
            },
        )

        if tool_stdout.strip():
            print(tool_stdout.strip())
        if tool_stderr.strip():
            print(tool_stderr.strip(), file=sys.stderr)

        if tool == "tool_weather":
            payload = parse_tool_payload(tool_stdout)
            summary = payload.get("summary") if isinstance(payload, dict) else None
            if summary:
                try:
                    rc_voice, voice_stdout, voice_stderr = execute_tool(
                        "tool_voice",
                        {"PX_TEXT": summary},
                        args.dry_run,
                    )
                except VoiceLoopError as exc:
                    print(f"[voice-loop] Voice execution error: {exc}")
                else:
                    log_event(
                        "voice-loop",
                        {"turn": turn, "tool": "tool_voice", "returncode": rc_voice, "dry": args.dry_run},
                    )
                    if voice_stdout.strip():
                        print(voice_stdout.strip())
                    if voice_stderr.strip():
                        print(voice_stderr.strip(), file=sys.stderr)

        if args.exit_on_stop and tool == "tool_stop" and rc_tool == 0:
            print("[voice-loop] Stop command acknowledged. Exiting loop.")
            break


def main(argv: Optional[list[str]] = None) -> int:
    try:
        args = parse_args(argv)
        supervisor_loop(args)
        return 0
    except VoiceLoopError as exc:
        print(f"voice-loop error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
