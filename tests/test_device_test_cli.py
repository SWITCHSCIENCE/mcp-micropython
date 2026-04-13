from __future__ import annotations

import unittest
from argparse import Namespace

from mcp_micropython import device_test_cli


class DeviceTestCliTests(unittest.TestCase):
    def test_build_tool_registry_exposes_expected_tools(self) -> None:
        tools = device_test_cli.build_tool_registry()

        self.assertTrue(device_test_cli.REQUIRED_TOOL_NAMES.issubset(tools))

    def test_parse_args_serial_defaults(self) -> None:
        args = device_test_cli.parse_args(["--target", "COM3"])

        self.assertEqual(args.target, "COM3")
        self.assertEqual(args.target_kind, "serial")
        self.assertEqual(args.requested_groups, device_test_cli.RUN_GROUPS)

    def test_parse_args_requires_password_for_webrepl(self) -> None:
        with self.assertRaises(SystemExit):
            device_test_cli.parse_args(["--target", "192.168.0.10:8266"])

    def test_plan_group_execution_skips_serial_only_groups_for_webrepl(self) -> None:
        runnable, skipped = device_test_cli.plan_group_execution(
            "webrepl",
            {"common", "filesystem", "serial", "stream", "reset"},
        )

        self.assertEqual(runnable, {"common", "filesystem"})
        self.assertEqual(skipped, {"serial", "stream", "reset"})

    def test_summarize_outcomes_returns_failure_exit_code(self) -> None:
        counts, exit_code = device_test_cli.summarize_outcomes(
            [
                device_test_cli.TestOutcome(name="a", status="PASS"),
                device_test_cli.TestOutcome(name="b", status="FAIL"),
                device_test_cli.TestOutcome(name="c", status="SKIP"),
            ]
        )

        self.assertEqual(counts["PASS"], 1)
        self.assertEqual(counts["FAIL"], 1)
        self.assertEqual(counts["SKIP"], 1)
        self.assertEqual(exit_code, 1)

    def test_runner_marks_incompatible_groups_as_skip_for_webrepl(self) -> None:
        tools = self._make_fake_tools()
        args = Namespace(
            target="192.168.0.10:8266",
            password="secret",
            baudrate=115200,
            target_kind="webrepl",
            requested_groups={"stream", "reset"},
            exec_timeout=10,
            read_timeout=1.0,
            reconnect_timeout=2.0,
            large_file_size=1024,
        )

        runner = device_test_cli.DeviceTestRunner(args, tools, sleep=lambda _: None)
        exit_code = runner.run()

        self.assertEqual(exit_code, 0)
        names = {(outcome.name, outcome.status) for outcome in runner.outcomes}
        self.assertIn(("group:stream", "SKIP"), names)
        self.assertIn(("group:reset", "SKIP"), names)
        self.assertIn(("connect", "PASS"), names)
        self.assertIn(("disconnect", "PASS"), names)

    def test_ensure_connected_retries_until_serial_port_reappears(self) -> None:
        state = {
            "ports_calls": 0,
            "connect_calls": 0,
        }

        def list_ports():
            state["ports_calls"] += 1
            ports = []
            if state["ports_calls"] >= 3:
                ports = [{"port": "COM7", "description": "board", "hwid": "USB"}]
            return {"ok": True, "ports": ports, "error": None}

        def connect(**kwargs):
            state["connect_calls"] += 1
            return {
                "ok": True,
                "target": kwargs["target"],
                "transport": "serial",
                "baudrate": kwargs["baudrate"],
                "host": None,
                "port": kwargs["target"],
                "error": None,
            }

        args = Namespace(
            target="COM7",
            password=None,
            baudrate=115200,
            target_kind="serial",
            requested_groups=set(),
            exec_timeout=10,
            read_timeout=1.0,
            reconnect_timeout=2.0,
            large_file_size=1024,
        )
        runner = device_test_cli.DeviceTestRunner(
            args,
            {
                "micropython_list_ports": list_ports,
                "micropython_connect": connect,
            },
            sleep=lambda _: None,
        )

        runner.ensure_connected()

        self.assertTrue(runner.connected)
        self.assertEqual(state["ports_calls"], 3)
        self.assertEqual(state["connect_calls"], 1)

    def test_ensure_connected_times_out_when_serial_port_does_not_reappear(self) -> None:
        args = Namespace(
            target="COM7",
            password=None,
            baudrate=115200,
            target_kind="serial",
            requested_groups=set(),
            exec_timeout=10,
            read_timeout=1.0,
            reconnect_timeout=0.0,
            large_file_size=1024,
        )
        runner = device_test_cli.DeviceTestRunner(
            args,
            {
                "micropython_list_ports": lambda: {"ok": True, "ports": [], "error": None},
                "micropython_connect": lambda **kwargs: {
                    "ok": True,
                    "target": kwargs["target"],
                    "transport": "serial",
                    "baudrate": kwargs["baudrate"],
                    "host": None,
                    "port": kwargs["target"],
                    "error": None,
                },
            },
            sleep=lambda _: None,
        )

        with self.assertRaises(RuntimeError):
            runner.ensure_connected()

    def _make_fake_tools(self) -> dict[str, object]:
        connected = {"value": False}

        def connect(**kwargs):
            connected["value"] = True
            return {
                "ok": True,
                "target": kwargs["target"],
                "transport": "webrepl",
                "baudrate": None,
                "host": "192.168.0.10",
                "port": 8266,
                "error": None,
            }

        def disconnect():
            connected["value"] = False
            return {"ok": True, "error": None}

        def status():
            return {
                "ok": True,
                "connected": connected["value"],
                "transport": "webrepl",
                "target": "192.168.0.10:8266",
                "host": "192.168.0.10",
                "port": 8266,
                "baudrate": None,
                "error": None,
            }

        return {
            "micropython_connect": connect,
            "micropython_disconnect": disconnect,
            "micropython_connection_status": status,
        }


if __name__ == "__main__":
    unittest.main()
