from __future__ import annotations

import sys
from typing import Protocol, TextIO


class ProgressReporter(Protocol):
    def stage(self, message: str) -> None:
        ...

    def start(self, total: int, description: str) -> None:
        ...

    def update(self, completed: int) -> None:
        ...

    def finish(self) -> None:
        ...

    def fail(self) -> None:
        ...


class NullProgress:
    def stage(self, message: str) -> None:
        pass

    def start(self, total: int, description: str) -> None:
        pass

    def update(self, completed: int) -> None:
        pass

    def finish(self) -> None:
        pass

    def fail(self) -> None:
        pass


class TerminalProgress:
    def __init__(self, stream: TextIO | None = None):
        self.stream = stream or sys.stderr
        self._description = ""
        self._total = 0
        self._completed = 0
        self._line_active = False
        self._dynamic = bool(getattr(self.stream, "isatty", lambda: False)())

    def stage(self, message: str) -> None:
        self._end_line()
        print(message, file=self.stream, flush=True)

    def start(self, total: int, description: str) -> None:
        self._end_line()
        self._description = description
        self._total = total
        self._completed = 0
        if total <= 0:
            print(f"{description}: no items", file=self.stream, flush=True)
            return
        self._render()

    def update(self, completed: int) -> None:
        if self._total <= 0:
            return
        self._completed = min(max(completed, 0), self._total)
        if self._dynamic:
            self._render()
        elif self._completed >= self._total:
            self._render()

    def finish(self) -> None:
        if self._dynamic:
            if self._total > 0 and self._completed < self._total:
                self._completed = self._total
                self._render()
            self._end_line()
        elif self._total > 0 and self._completed < self._total:
            self._completed = self._total
            self._render()

    def fail(self) -> None:
        self._end_line()

    def _render(self) -> None:
        percentage = self._completed / self._total * 100 if self._total else 100
        message = f"{self._description}: {self._completed}/{self._total} ({percentage:.1f}%)"
        if self._dynamic:
            self.stream.write(f"\r{message}")
            self.stream.flush()
            self._line_active = True
        else:
            print(message, file=self.stream, flush=True)

    def _end_line(self) -> None:
        if self._line_active:
            print(file=self.stream, flush=True)
            self._line_active = False
