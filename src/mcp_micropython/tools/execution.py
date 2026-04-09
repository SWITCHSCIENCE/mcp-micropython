"""
execution.py — コード実行ツール

MCP ツール:
  - micropython_exec : Python コードブロックを実行し stdout/stderr を返す
  - micropython_eval : 式を評価して結果を返す
"""

from __future__ import annotations

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from ..serial_manager import NotConnectedError, SerialManager


class ExecResult(TypedDict):
    ok: bool
    stdout: str
    stderr: str
    error: str | None


class EvalResult(TypedDict):
    ok: bool
    result: str
    error: str | None


def register(mcp: FastMCP, manager: SerialManager) -> None:
    """コード実行ツールを MCP サーバーに登録する。"""

    @mcp.tool()
    def micropython_exec(code: str, timeout: int = 10) -> ExecResult:
        """
        MicroPython インタープリタで Python コードを実行する。
        複数行のコードも実行できる。

        Args:
            code: 実行する Python コード (複数行可)
            timeout: 実行タイムアウト秒数 (デフォルト 10秒)

        Returns:
            実行結果 (stdout/stderr)

        Example:
            code = "import machine\\nprint(machine.freq())"
        """
        try:
            result = manager.exec_code(code, timeout=float(timeout))
        except NotConnectedError as e:
            return {"ok": False, "stdout": "", "stderr": "", "error": str(e)}
        except Exception as e:
            return {"ok": False, "stdout": "", "stderr": "", "error": str(e)}

        return {
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": None if result.ok else (result.stderr.strip() or "execution failed"),
        }

    @mcp.tool()
    def micropython_eval(expression: str) -> EvalResult:
        """
        MicroPython ボードで式を評価し、結果を文字列で返す。

        Args:
            expression: 評価する Python 式 (例: "1 + 1", "machine.freq()")

        Returns:
            評価結果の文字列
        """
        try:
            result = manager.eval_expr(expression)
        except NotConnectedError as e:
            return {"ok": False, "result": "", "error": str(e)}
        except Exception as e:
            return {"ok": False, "result": "", "error": str(e)}

        if result.ok:
            return {"ok": True, "result": result.stdout.strip(), "error": None}
        else:
            return {
                "ok": False,
                "result": "",
                "error": result.stderr.strip() or "evaluation failed",
            }
