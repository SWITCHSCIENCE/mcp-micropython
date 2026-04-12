# Recipes

Use these short recipes as the default workflow.

## Default approach

- Read `HARDWARE.md` before making hardware assumptions.
- Prefer documented helper modules or board APIs.
- Read `/boot.py` and `/main.py` before modifying either file.
- If board-specific behavior changes, follow `micropython://policy/hardware-docs`.

## List available ports

1. Run `micropython_list_ports`.
2. Choose the target serial port from the result.

## Connect to a board

1. Run `micropython_connect` with a selected serial port or a `host[:port]` WebREPL target.
2. If using WebREPL, provide `password`.
3. If needed, run `micropython_connection_status` to confirm the active session.

## Use WebREPL on a preconfigured board

1. Make sure the board is already connected to Wi-Fi and WebREPL is enabled outside this MCP server.
2. Run `micropython_connect(target="host[:port]", password="...")`.
3. If no port is given, the default is `8266`.
4. If needed, run `micropython_connection_status`.

## Read `HARDWARE.md`

1. Connect to the board.
2. Run `micropython_read_hardware_md`.
3. Treat it as the source of truth for wiring, GPIO, attached peripherals, and supported helper APIs.

## Inspect the filesystem

1. Connect to the board.
2. Run `micropython_list_files` with `path="/"`.
3. Read specific files with `micropython_read_file`.

## Wait for device output

1. Run `micropython_read_until` to wait for a specific string.
2. Run `micropython_read_stream` to capture output for a fixed duration.

## Recover from a hang

1. Run `micropython_interrupt`.
2. If the REPL does not recover, reconnect.

## Capture startup logs after reset

1. Use `micropython_reset_and_capture` only on serial sessions.
2. For WebREPL sessions, reconnect after reset instead.

## Disconnect

1. Run `micropython_disconnect` when finished.
