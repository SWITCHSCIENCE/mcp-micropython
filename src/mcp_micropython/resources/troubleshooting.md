# Troubleshooting

## Cannot connect

- For serial, confirm the board is powered, visible in `micropython_list_ports`, and not held by other software.
- For WebREPL, confirm the `host[:port]`, `password`, and Wi-Fi reachability.
- If no port is given for WebREPL, the default is `8266`.
- Run `micropython_connection_status` if the session state is unclear.

## REPL does not respond

- Run `micropython_interrupt`.
- If there is still no response, reconnect.

## Cannot read after reset

- A reset can drop the current session.
- Reconnect before reading files or running code again.

## `micropython_reset_and_capture` fails

- This tool only works for serial sessions.
- For WebREPL sessions, reconnect after reset instead.

## Long code execution is unstable

- Break the task into smaller checks.
- Prefer short scripts with explicit output.
- Use `micropython_read_until` or `micropython_read_stream` when waiting for device output.

## Large file writes fail

- Reduce the amount written in one operation.
- Prefer `micropython_append_file` in small chunks instead of one large overwrite.
