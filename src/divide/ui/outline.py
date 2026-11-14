"""Search > Outline: the declarations of the PHP file, to jump to.

A window at the right of the desktop lists the namespaces, classes, interfaces,
traits and enums of the active PHP file, their constants, properties and
methods indented below them (UML's marks: + public, # protected, - private),
and the functions. Enter (or a double click) goes to the declaration. The list
follows the active PHP editor and its edits.
"""

from __future__ import annotations

from divide.lang import php
from divide.ui.runner import DEBUG_CSS, _ListWindow
from divide.ui.windows import EditorWindow, ProjectWindow

WIDTH = 36
NO_OUTLINE = "(the outline is for PHP files)"


class OutlineWindow(_ListWindow):
    """The symbols of ``source``; Enter goes to the one under the bar."""

    DEFAULT_CSS = DEBUG_CSS.format(name="OutlineWindow")
    HINT = "Enter go to the declaration · + public  # protected  - private"

    def __init__(self, number: int = 0) -> None:
        super().__init__("Outline", number=number)
        self.source: EditorWindow | None = None
        self.symbols: list[php.Symbol] = []
        self.text: str | None = None  # the source's text the list was made from

    def load(self, source: EditorWindow | None) -> None:
        self.source = source
        self.text = source.editor.text if source is not None else None
        found = php.outline(source.editor.text) if source is not None and source.editor.lang == "php" else None
        self.symbols = found or []
        if source is None or source.editor.lang != "php":
            lines = [NO_OUTLINE]
        elif found is None:
            lines = ["(no PHP grammar: pip install tree-sitter-php)"]
        else:
            lines = [s.text for s in self.symbols] or ["(no declarations)"]
        name = source.path.name if source is not None and source.path is not None else ""
        self.title = f"Outline: {name}" if name else "Outline"
        self.show(lines)

    def activate(self, index: int) -> None:
        if self.source is None or not 0 <= index < len(self.symbols):
            return
        symbol = self.symbols[index]
        self.app._select_in(self.source, symbol.start, symbol.end)  # type: ignore[attr-defined]


class OutlineMixin:
    """Search > Outline (mixed into the Divide app)."""

    def outline_window(self) -> OutlineWindow | None:
        return next((w for w in self.windows() if isinstance(w, OutlineWindow)), None)

    def show_outline(self) -> None:
        window = self.outline_window()
        if window is None:
            window = OutlineWindow(number=self._free_number())
            self._right_window(window)
        window.load(self.active_editor() or self._php_editor())
        self.raise_window(window)
        window.list.focus()

    def _php_editor(self) -> EditorWindow | None:
        """The editor on top of the others that holds PHP (the outline is opened from a non-editor)."""
        return next((w for w in reversed(self.windows()) if isinstance(w, EditorWindow) and w.editor.lang == "php"), None)

    def _right_window(self, window: OutlineWindow) -> None:
        """Along the right edge; the windows under it end where it starts."""
        width = self.desktop.size.width or 80
        left = max(20, width - WIDTH)
        window.styles.width = width - left
        window.styles.height = "100%"
        window.styles.offset = (left, 0)
        for other in self.windows():
            if other.zoomed or isinstance(other, (_ListWindow, ProjectWindow)) or type(other).__name__ == "MessagesWindow":
                continue
            x = int(other.styles.offset.x.value) if other.styles.offset.x else 0
            if x < left and x + (other.size.width or width) > left and left - x >= 20:
                other.styles.width = left - x
        self.insert_window(window)

    def follow_outline(self, editor: EditorWindow | None = None) -> None:
        """The active PHP editor changed, or its text did: the outline follows."""
        window = self.outline_window()
        if window is None:
            return
        editor = editor or self.active_editor()
        if editor is None or editor.editor.lang != "php":
            return
        if editor is not window.source or window.text != editor.editor.text:
            window.load(editor)
