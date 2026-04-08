# Recipes

Use these short recipes as starting points for common tasks.

## Preferred approach

- Treat `HARDWARE.md` as the board-specific guide.
- Use documented helper modules or board APIs first.
- If new behavior is needed, add or extend a small reusable helper module instead of leaving a one-off script.
- If the task changes reusable board-specific behavior or assumptions, follow `micropython://policy/hardware-docs` before considering the task complete.
- Only fall back to direct `machine.Pin`, `I2C`, `SPI`, or `UART` access when no supported path is documented.
- Read `/boot.py` and `/main.py` before modifying either file.

## List available ports

1. Run `micropython_list_ports`.
2. Choose the target serial port from the result.

## Connect to a board

1. Run `micropython_connect` with the selected port.
2. Confirm the connection before reading device resources.

## Read `HARDWARE.md`

1. Connect to the board.
2. Run `micropython_read_hardware_md`.
3. Treat it as the source of truth for wiring, GPIO, attached peripherals, and supported helper APIs.

## Inspect the filesystem

1. Connect to the board.
2. Run `micropython_list_files` with `path="/"`.
3. Read specific files with `micropython_read_file`.

## Use or add a hardware feature

1. Read `HARDWARE.md` and inspect the existing device files.
2. If a supported helper exists, use it.
3. If not, implement the behavior as a small helper module or extend an existing one.
4. Verify with a short explicit call.
5. If the change affects future board usage, update `HARDWARE.md` according to `micropython://policy/hardware-docs`.

## Recover from a hang

1. Run `micropython_interrupt`.
2. If the REPL does not recover, reconnect.
3. If the board was reset, treat the session as disconnected.

## Disconnect

1. Run `micropython_disconnect` when finished.
