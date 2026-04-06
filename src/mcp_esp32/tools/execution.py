"""
execution.py — コード実行ツール

MCP ツール:
  - esp32_exec : Python コードブロックを実行し stdout/stderr を返す
  - esp32_eval : 式を評価して結果を返す
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..serial_manager import NotConnectedError, SerialManager


def register(mcp: FastMCP, manager: SerialManager) -> None:
    """コード実行ツールを MCP サーバーに登録する。"""

    @mcp.tool()
    def esp32_exec(code: str, timeout: int = 10) -> str:
        """
        ESP32 の MicroPython インタープリタで Python コードを実行する。
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
            return f"✗ {e}"
        except Exception as e:
            return f"✗ 実行エラー: {e}"

        if result.ok:
            output = result.stdout.strip()
            return output if output else "(出力なし)"
        else:
            parts = []
            if result.stdout.strip():
                parts.append(f"[stdout]\n{result.stdout.strip()}")
            parts.append(f"[stderr]\n{result.stderr.strip()}")
            return "\n".join(parts)

    @mcp.tool()
    def esp32_eval(expression: str) -> str:
        """
        ESP32 の MicroPython で式を評価し、結果を文字列で返す。

        Args:
            expression: 評価する Python 式 (例: "1 + 1", "machine.freq()")

        Returns:
            評価結果の文字列
        """
        try:
            result = manager.eval_expr(expression)
        except NotConnectedError as e:
            return f"✗ {e}"
        except Exception as e:
            return f"✗ 評価エラー: {e}"

        if result.ok:
            return result.stdout.strip()
        else:
            return f"✗ エラー:\n{result.stderr.strip()}"
