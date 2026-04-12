"""
device_test_cli.py - real device test CLI for tools wrappers.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from .session_manager import SessionManager
from .tools import device, execution, filesystem
from .transport import DEFAULT_SERIAL_BAUDRATE, parse_target

DEFAULT_LARGE_FILE_SIZE = 10 * 1024
DEFAULT_CHUNK_SIZE = 512
LARGE_FILE_TEST_PATH = "/device_test_cli_large.txt"
SMALL_FILE_TEST_PATH = "/device_test_cli_small.txt"
STREAM_READY_SENTINEL = "DEVICE_TEST_STREAM_READY"
STREAM_TICK_SENTINEL = "DEVICE_TEST_STREAM_TICK"

ToolFunc = Callable[..., dict[str, Any]]
REQUIRED_TOOL_NAMES = {
    "micropython_list_ports",
    "micropython_connect",
    "micropython_disconnect",
    "micropython_connection_status",
    "micropython_get_info",
    "micropython_exec",
    "micropython_eval",
    "micropython_list_files",
    "micropython_read_file",
    "micropython_write_file",
    "micropython_append_file",
    "micropython_delete_file",
    "micropython_read_until",
    "micropython_read_stream",
    "micropython_reset",
    "micropython_reset_and_capture",
    "micropython_interrupt",
}
RUN_GROUPS = {"common", "filesystem", "serial", "stream", "reset"}
DEFAULT_RECONNECT_TIMEOUT = 10.0
DEFAULT_RECONNECT_INTERVAL = 0.5


def make_test_payload(size: int) -> str:
    seed = "MicroPython large text transfer test payload.\n"
    repeat = (size // len(seed)) + 1
    return (seed * repeat)[:size]


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    return [text[offset : offset + chunk_size] for offset in range(0, len(text), chunk_size)]


def build_stream_test_main(iterations: int = 30, delay_ms: int = 100) -> str:
    return "\n".join(
        [
            "import time",
            f"print({STREAM_READY_SENTINEL!r})",
            f"for i in range({iterations}):",
            f"    print('{STREAM_TICK_SENTINEL}:%d' % i)",
            f"    time.sleep_ms({delay_ms})",
        ]
    )


@dataclass
class TestOutcome:
    name: str
    status: str
    detail: str = ""


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, ToolFunc] = {}

    def tool(self):
        def decorator(func: ToolFunc) -> ToolFunc:
            self.tools[func.__name__] = func
            return func

        return decorator


def build_tool_registry(manager: SessionManager | None = None) -> dict[str, ToolFunc]:
    fake_mcp = FakeMCP()
    tool_manager = manager or SessionManager()
    device.register(fake_mcp, tool_manager)
    execution.register(fake_mcp, tool_manager)
    filesystem.register(fake_mcp, tool_manager)
    missing = REQUIRED_TOOL_NAMES - set(fake_mcp.tools)
    if missing:
        raise RuntimeError(f"missing tools in registry: {', '.join(sorted(missing))}")
    return fake_mcp.tools


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-device checks against mcp_micropython tools wrappers."
    )
    parser.add_argument("--target", required=True, help="COM3 or host[:port]")
    parser.add_argument("--password", help="WebREPL password")
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_SERIAL_BAUDRATE,
        help=f"Serial baudrate (default: {DEFAULT_SERIAL_BAUDRATE})",
    )
    parser.add_argument(
        "--tests",
        default="all",
        help="Comma-separated groups: all,common,filesystem,serial,stream,reset",
    )
    parser.add_argument(
        "--large-file-size",
        type=int,
        default=DEFAULT_LARGE_FILE_SIZE,
        help=f"Large file round-trip size in bytes (default: {DEFAULT_LARGE_FILE_SIZE})",
    )
    parser.add_argument(
        "--exec-timeout",
        type=int,
        default=10,
        help="Timeout in seconds for micropython_exec/write calls",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=3.0,
        help="Timeout in seconds for stream/read-until style checks",
    )
    parser.add_argument(
        "--reconnect-timeout",
        type=float,
        default=DEFAULT_RECONNECT_TIMEOUT,
        help=f"Timeout in seconds for serial reconnect after reset (default: {DEFAULT_RECONNECT_TIMEOUT})",
    )

    args = parser.parse_args(argv)
    spec = parse_target(args.target)
    args.target_kind = spec.kind
    try:
        args.requested_groups = normalize_requested_groups(args.tests)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if spec.kind == "webrepl" and not args.password:
        parser.error("--password is required when target is WebREPL")
    if args.large_file_size <= 0:
        parser.error("--large-file-size must be > 0")
    if args.exec_timeout <= 0:
        parser.error("--exec-timeout must be > 0")
    if args.read_timeout <= 0:
        parser.error("--read-timeout must be > 0")
    if args.reconnect_timeout <= 0:
        parser.error("--reconnect-timeout must be > 0")

    return args


def normalize_requested_groups(raw: str) -> set[str]:
    groups = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if not groups:
        groups = {"all"}
    if "all" in groups:
        return set(RUN_GROUPS)
    unknown = groups - RUN_GROUPS
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown test group(s): {', '.join(sorted(unknown))}")
    return groups


def plan_group_execution(target_kind: str, requested_groups: set[str]) -> tuple[set[str], set[str]]:
    incompatible: set[str] = set()
    if target_kind != "serial":
        incompatible |= requested_groups & {"serial", "stream", "reset"}
    runnable = requested_groups - incompatible
    return runnable, incompatible


def summarize_outcomes(outcomes: list[TestOutcome]) -> tuple[dict[str, int], int]:
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    exit_code = 1 if counts.get("FAIL", 0) else 0
    return counts, exit_code


class DeviceTestRunner:
    def __init__(
        self,
        args: argparse.Namespace,
        tools: dict[str, ToolFunc],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.args = args
        self.tools = tools
        self.sleep = sleep
        self.outcomes: list[TestOutcome] = []
        self.connected = False
        self.main_backup: str | None = None
        self.main_existed = False
        self.temp_main_active = False

    def emit(self, outcome: TestOutcome) -> None:
        self.outcomes.append(outcome)
        line = f"{outcome.status:<4} {outcome.name}"
        if outcome.detail:
            line = f"{line} - {outcome.detail}"
        print(line)

    def pass_(self, name: str, detail: str = "") -> None:
        self.emit(TestOutcome(name=name, status="PASS", detail=detail))

    def fail(self, name: str, detail: str) -> None:
        self.emit(TestOutcome(name=name, status="FAIL", detail=detail))

    def skip(self, name: str, detail: str) -> None:
        self.emit(TestOutcome(name=name, status="SKIP", detail=detail))

    def call(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        return self.tools[tool_name](**kwargs)

    def require_ok(self, result: dict[str, Any], context: str) -> dict[str, Any]:
        if result.get("ok"):
            return result
        raise RuntimeError(str(result.get("error") or f"{context} failed"))

    def ensure_connected(self) -> None:
        if self.connected:
            return

        if self.args.target_kind != "serial":
            self._connect_once()
            return

        deadline = time.monotonic() + self.args.reconnect_timeout
        last_error = "serial port did not reappear"

        while True:
            ports_result = self.call("micropython_list_ports")
            if ports_result.get("ok"):
                ports = ports_result.get("ports", [])
                if any(port.get("port") == self.args.target for port in ports):
                    try:
                        self._connect_once()
                        return
                    except RuntimeError as exc:
                        last_error = str(exc)
                else:
                    last_error = f"{self.args.target} not present in port list yet"
            else:
                last_error = str(ports_result.get("error") or "list ports failed")

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"serial reconnect timed out after {self.args.reconnect_timeout:.1f}s: {last_error}"
                )
            self.sleep(DEFAULT_RECONNECT_INTERVAL)

    def _connect_once(self) -> None:
        result = self.call(
            "micropython_connect",
            target=self.args.target,
            password=self.args.password,
            baudrate=self.args.baudrate,
        )
        self.require_ok(result, "connect")
        self.connected = True

    def cleanup_temp_main(self) -> None:
        if not self.temp_main_active:
            return
        try:
            if not self.connected:
                self.ensure_connected()
            self.call("micropython_interrupt")
            if self.main_existed and self.main_backup is not None:
                self.require_ok(
                    self.call(
                        "micropython_write_file",
                        path="/main.py",
                        content=self.main_backup,
                        timeout=self.args.exec_timeout,
                    ),
                    "restore /main.py",
                )
            else:
                delete_result = self.call("micropython_delete_file", path="/main.py")
                if not delete_result.get("ok") and "No such file" not in str(delete_result.get("error")):
                    raise RuntimeError(str(delete_result.get("error") or "delete /main.py failed"))
            self.call("micropython_reset")
            self.connected = False
        finally:
            self.temp_main_active = False

    def run(self) -> int:
        runnable_groups, skipped_groups = plan_group_execution(
            self.args.target_kind,
            self.args.requested_groups,
        )

        for group in sorted(skipped_groups):
            self.skip(f"group:{group}", f"not supported for {self.args.target_kind}")

        try:
            if "serial" in runnable_groups:
                self.run_list_ports_test()

            self.run_connect_test()

            if "common" in runnable_groups:
                self.run_common_tests()
            if "filesystem" in runnable_groups:
                self.run_filesystem_tests()
            if "reset" in runnable_groups:
                self.run_reset_capture_test()
            if "stream" in runnable_groups:
                self.run_stream_tests()
        except Exception as exc:
            if not any(outcome.status == "FAIL" for outcome in self.outcomes):
                self.fail("runner", str(exc))
        finally:
            try:
                self.cleanup_temp_main()
            except Exception as exc:
                self.fail("cleanup_main", str(exc))
            if self.connected:
                disconnect = self.call("micropython_disconnect")
                if disconnect.get("ok"):
                    self.pass_("disconnect", "connection closed")
                else:
                    self.fail("disconnect", str(disconnect.get("error") or "disconnect failed"))
                self.connected = False
            elif not any(outcome.name == "disconnect" for outcome in self.outcomes):
                self.skip("disconnect", "no active connection at shutdown")

        counts, exit_code = summarize_outcomes(self.outcomes)
        print(
            f"SUMMARY pass={counts.get('PASS', 0)} fail={counts.get('FAIL', 0)} skip={counts.get('SKIP', 0)}"
        )
        return exit_code

    def run_list_ports_test(self) -> None:
        result = self.require_ok(self.call("micropython_list_ports"), "list ports")
        ports = result.get("ports", [])
        target_present = any(port.get("port") == self.args.target for port in ports)
        if target_present:
            self.pass_("list_ports", f"found {self.args.target}")
            return
        listed = ", ".join(str(port.get("port")) for port in ports) or "(none)"
        self.fail("list_ports", f"{self.args.target} not found in {listed}")

    def run_connect_test(self) -> None:
        result = self.call(
            "micropython_connect",
            target=self.args.target,
            password=self.args.password,
            baudrate=self.args.baudrate,
        )
        if not result.get("ok"):
            self.fail("connect", str(result.get("error") or "connect failed"))
            raise RuntimeError("connect failed")
        self.connected = True
        detail = f"transport={result.get('transport')} target={result.get('target')}"
        self.pass_("connect", detail)

    def run_common_tests(self) -> None:
        status = self.require_ok(self.call("micropython_connection_status"), "connection status")
        if status.get("connected"):
            self.pass_("connection_status", f"transport={status.get('transport')}")
        else:
            self.fail("connection_status", "tool reported disconnected")

        info = self.require_ok(self.call("micropython_get_info"), "get info")
        info_payload = info.get("info", {})
        if info_payload:
            detail = f"platform={info_payload.get('platform')} version={info_payload.get('version')}"
            self.pass_("get_info", detail)
        else:
            self.fail("get_info", "empty device info")

        eval_result = self.require_ok(self.call("micropython_eval", expression="1 + 1"), "eval")
        if str(eval_result.get("result", "")).strip() == "2":
            self.pass_("eval", "1 + 1 == 2")
        else:
            self.fail("eval", f"unexpected result: {eval_result.get('result')!r}")

        exec_result = self.require_ok(
            self.call(
                "micropython_exec",
                code="print('DEVICE_TEST_EXEC_OK')",
                timeout=self.args.exec_timeout,
            ),
            "exec",
        )
        stdout = str(exec_result.get("stdout", ""))
        if "DEVICE_TEST_EXEC_OK" in stdout:
            self.pass_("exec", "stdout verified")
        else:
            self.fail("exec", f"missing sentinel in stdout: {stdout!r}")

    def run_filesystem_tests(self) -> None:
        list_result = self.require_ok(self.call("micropython_list_files", path="/"), "list files")
        entry_count = len(list_result.get("entries", []))
        self.pass_("list_files", f"entries={entry_count}")

        small_payload = "hello from device_test_cli\n"
        write_result = self.require_ok(
            self.call(
                "micropython_write_file",
                path=SMALL_FILE_TEST_PATH,
                content=small_payload,
                timeout=self.args.exec_timeout,
            ),
            "write small file",
        )
        self.pass_("write_file", f"bytes={write_result.get('bytes_written')}")

        append_result = self.require_ok(
            self.call(
                "micropython_append_file",
                path=SMALL_FILE_TEST_PATH,
                content="appended\n",
                timeout=self.args.exec_timeout,
            ),
            "append small file",
        )
        self.pass_("append_file", f"bytes={append_result.get('bytes_written')}")

        read_result = self.require_ok(
            self.call(
                "micropython_read_file",
                path=SMALL_FILE_TEST_PATH,
                timeout=self.args.exec_timeout,
            ),
            "read small file",
        )
        expected_small = small_payload + "appended\n"
        if normalize_newlines(str(read_result.get("content", ""))) == normalize_newlines(expected_small):
            self.pass_("read_file", "small file round-trip OK")
        else:
            self.fail("read_file", "small file content mismatch")

        delete_result = self.require_ok(self.call("micropython_delete_file", path=SMALL_FILE_TEST_PATH), "delete file")
        self.pass_("delete_file", f"path={delete_result.get('path')}")

        payload = make_test_payload(self.args.large_file_size)
        self.require_ok(
            self.call(
                "micropython_write_file",
                path=LARGE_FILE_TEST_PATH,
                content="",
                timeout=self.args.exec_timeout,
            ),
            "initialize large file",
        )
        try:
            for chunk in chunk_text(payload, DEFAULT_CHUNK_SIZE):
                self.require_ok(
                    self.call(
                        "micropython_append_file",
                        path=LARGE_FILE_TEST_PATH,
                        content=chunk,
                        timeout=self.args.exec_timeout,
                    ),
                    "append large file",
                )
            large_read = self.require_ok(
                self.call(
                    "micropython_read_file",
                    path=LARGE_FILE_TEST_PATH,
                    timeout=max(self.args.exec_timeout, 20),
                ),
                "read large file",
            )
            restored = str(large_read.get("content", ""))
            if normalize_newlines(restored) == normalize_newlines(payload):
                self.pass_("large_file_roundtrip", f"bytes={self.args.large_file_size}")
            else:
                self.fail("large_file_roundtrip", "large file content mismatch")
        finally:
            self.call("micropython_delete_file", path=LARGE_FILE_TEST_PATH)

    def capture_existing_main(self) -> None:
        root = self.require_ok(self.call("micropython_list_files", path="/"), "list files for stream setup")
        paths = {entry.get("path") for entry in root.get("entries", [])}

        if "/boot.py" in paths:
            self.require_ok(
                self.call("micropython_read_file", path="/boot.py", timeout=self.args.exec_timeout),
                "read /boot.py",
            )

        if "/main.py" in paths:
            read_main = self.require_ok(
                self.call("micropython_read_file", path="/main.py", timeout=self.args.exec_timeout),
                "read /main.py",
            )
            self.main_existed = True
            self.main_backup = str(read_main.get("content", ""))
        else:
            self.main_existed = False
            self.main_backup = None

    def install_stream_test_main(self) -> None:
        self.capture_existing_main()
        content = build_stream_test_main()
        self.require_ok(
            self.call(
                "micropython_write_file",
                path="/main.py",
                content=content,
                timeout=self.args.exec_timeout,
            ),
            "install stream test main",
        )
        self.temp_main_active = True
        self.pass_("prepare_stream_main", "temporary /main.py installed")

    def run_reset_capture_test(self) -> None:
        self.install_stream_test_main()
        result = self.require_ok(
            self.call(
                "micropython_reset_and_capture",
                capture_duration=self.args.read_timeout,
                idle_timeout=0.5,
                max_bytes=4096,
            ),
            "reset and capture",
        )
        stdout = str(result.get("stdout", ""))
        if result.get("reset_ok") and STREAM_READY_SENTINEL in stdout:
            self.pass_("reset_and_capture", "boot output captured")
        else:
            self.fail("reset_and_capture", "stream sentinel not found in reset capture")

    def run_stream_tests(self) -> None:
        if not self.temp_main_active:
            self.install_stream_test_main()

        reset_result = self.require_ok(self.call("micropython_reset"), "reset before stream tests")
        if reset_result.get("ok"):
            self.pass_("reset", "device reset requested")
        else:
            self.fail("reset", str(reset_result.get("error") or "reset failed"))
        self.connected = False
        self.ensure_connected()

        until = self.require_ok(
            self.call(
                "micropython_read_until",
                pattern=STREAM_TICK_SENTINEL,
                timeout=self.args.read_timeout,
                max_bytes=2048,
            ),
            "read until",
        )
        if until.get("matched"):
            self.pass_("read_until", f"bytes={until.get('bytes_read')}")
        else:
            self.fail("read_until", "pattern not matched")

        stream = self.require_ok(
            self.call(
                "micropython_read_stream",
                duration=self.args.read_timeout,
                idle_timeout=0.3,
                max_bytes=2048,
            ),
            "read stream",
        )
        stdout = str(stream.get("stdout", ""))
        if STREAM_TICK_SENTINEL in stdout:
            self.pass_("read_stream", f"bytes={stream.get('bytes_read')}")
        else:
            self.fail("read_stream", "tick output not observed")

        interrupt = self.require_ok(self.call("micropython_interrupt"), "interrupt")
        if interrupt.get("ok"):
            self.pass_("interrupt", "stopped temporary stream loop")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    tools = build_tool_registry()
    runner = DeviceTestRunner(args, tools)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
