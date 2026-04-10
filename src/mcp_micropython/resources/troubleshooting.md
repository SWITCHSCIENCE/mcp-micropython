# Troubleshooting

## Cannot connect

- Confirm the board is powered and visible in `micropython_list_ports`.
- Check that the selected serial port or `host[:port]` target is the correct one.
- Close other software that may already hold the serial port.
- For WebREPL, verify the password and that the board is already on Wi-Fi.

## REPL does not respond

- Run `micropython_interrupt`.
- If there is still no response, disconnect and reconnect.
- If needed, reset the board and reconnect.

## Cannot read after reset

- A reset can drop the current serial session.
- Reconnect before reading files or running code again.

## `micropython_reset_and_capture` fails

- This tool only works for serial sessions.
- For WebREPL sessions, reconnect after reset instead of using startup-log capture.

## Long code execution is unstable

- Break the task into smaller checks.
- Prefer the documented board API from `HARDWARE.md` over reinitializing buses and pins yourself.
- Prefer short scripts with explicit output.
- Avoid large multi-step scripts until the board state is known.

## Large file writes fail

- Reduce the amount written in one operation.
- Prefer smaller edits over large overwrite operations.
- This server is not optimized for large transfers.
