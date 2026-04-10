"""
serial_manager.py — backward-compatible shim.
"""

from .session_manager import NotConnectedError, SessionManager

SerialManager = SessionManager
