"""
FILE: app.py
ROLE: Composition root.
WHAT IT DOES: Wires all components, owns application lifecycle.
    Does NOT contain business logic — only construction and startup.
"""

from __future__ import annotations


def main() -> int:
    # Wire components here:
    #   engine = Engine(...)
    #   window = MainWindow(engine=engine)
    #   window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
