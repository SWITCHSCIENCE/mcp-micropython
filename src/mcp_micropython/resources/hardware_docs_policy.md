# HARDWARE.md update policy

Update `/HARDWARE.md` when a task changes or expands board-specific knowledge that future sessions should rely on, including:

- GPIO roles or wiring assumptions
- attached peripherals or device addresses
- supported helper modules or hardware entry points
- reusable hardware workflows, setup steps, or initialization requirements

Do not update `/HARDWARE.md` for:

- temporary experiments or one-off probes
- pure refactors that do not change board usage
- internal implementation changes with no board-visible impact

Rule of thumb: if the change affects how someone should use, initialize, wire, or understand the board in a future session, update `/HARDWARE.md`.

When this applies, treat the task as incomplete until `/HARDWARE.md` is updated.
