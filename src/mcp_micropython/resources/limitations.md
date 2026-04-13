# Limitations

## Connection-dependent data

- Filesystem contents require an active session.
- `HARDWARE.md` on the device requires an active session.

## Transport differences

- `micropython_read_stream` and `micropython_read_until` work on serial and WebREPL.
- `micropython_reset_and_capture` works only on serial.

## File transfer constraints

- Large text writes may fail because of Raw REPL and transport limits.
- Prefer `micropython_write_file` for the initial write and `micropython_append_file` for small follow-up chunks.
- Large binary transfers are not a primary use case.

## Hardware variability

- GPIO assignments and peripheral availability differ by board.
- Use `HARDWARE.md` and supported helper modules or board APIs when available.
- Update rules for `HARDWARE.md` are defined in `micropython://policy/hardware-docs`.
