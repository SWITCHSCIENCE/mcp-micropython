# Troubleshooting

## Cannot connect

- Confirm the board is powered and visible in `micropython_list_ports`.
- Check that the selected port is the correct one.
- Close other software that may already hold the serial port.

## REPL does not respond

- Run `micropython_interrupt`.
- If there is still no response, disconnect and reconnect.
- If needed, reset the board and reconnect.

## Cannot read after reset

- A reset can drop the current serial session.
- Reconnect before reading files or running code again.

## Long code execution is unstable

- Break the task into smaller checks.
- Prefer the documented board API from `HARDWARE.md` over reinitializing buses and pins yourself.
- Prefer short scripts with explicit output.
- Avoid large multi-step scripts until the board state is known.

## Large file writes fail

- Reduce the amount written in one operation.
- Prefer smaller edits over large overwrite operations.
- This server is not optimized for large transfers.
