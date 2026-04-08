# Limitations

## Connection-dependent data

- Some information is only available after connecting to the board.
- Filesystem contents and `HARDWARE.md` cannot be read without an active session.

## Session behavior

- A reset can close the current serial session.
- Long-running or noisy programs may leave the REPL in a state that needs interrupt or reconnect.

## File transfer constraints

- Large text writes may fail because of Raw REPL and transport limits.
- Large binary transfers are not a primary use case of this server.

## Hardware variability

- GPIO assignments and peripheral availability differ by board.
- The intended usage model is to document board-specific behavior in `HARDWARE.md` and use supported helper modules or board APIs when they are available.
- The exact conditions for updating `HARDWARE.md` are defined in `micropython://policy/hardware-docs`.
- Generic MicroPython examples may still be wrong for a specific board or wiring setup.
