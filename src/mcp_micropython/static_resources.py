"""
Static MCP resources that can be read before connecting to a device.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

_RESOURCE_DIR = Path(__file__).with_name("resources")


def _read_guide(name: str) -> str:
    return (_RESOURCE_DIR / name).read_text(encoding="utf-8")


def register(mcp: FastMCP) -> None:
    """Register static guide resources."""

    @mcp.resource(
        "micropython://guide/recipes",
        name="micropython_guide_recipes",
        title="MicroPython MCP recipes",
        description="Common task recipes that prefer HARDWARE.md and board-specific helper APIs.",
        mime_type="text/markdown",
    )
    def recipes() -> str:
        return _read_guide("recipes.md")

    @mcp.resource(
        "micropython://policy/hardware-docs",
        name="micropython_policy_hardware_docs",
        title="MicroPython HARDWARE.md policy",
        description="Completion policy for when HARDWARE.md should be updated after board-specific changes.",
        mime_type="text/markdown",
    )
    def hardware_docs_policy() -> str:
        return _read_guide("hardware_docs_policy.md")

    @mcp.resource(
        "micropython://guide/troubleshooting",
        name="micropython_guide_troubleshooting",
        title="MicroPython MCP troubleshooting",
        description="Troubleshooting guide for common MCP and device issues.",
        mime_type="text/markdown",
    )
    def troubleshooting() -> str:
        return _read_guide("troubleshooting.md")

    @mcp.resource(
        "micropython://guide/limitations",
        name="micropython_guide_limitations",
        title="MicroPython MCP limitations",
        description="Known limitations and constraints of this MCP server and its device access model.",
        mime_type="text/markdown",
    )
    def limitations() -> str:
        return _read_guide("limitations.md")
