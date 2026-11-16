"""Search > Outline: the shape of the PHP file or the Div template, to jump to.

A window at the right of the desktop lists, for a PHP file, its namespaces,
classes, interfaces, traits and enums, their constants, properties and
methods indented below them (UML's marks: + public, # protected, - private),
and the functions; for a Div template, its constructs as they are written
(definitions, includes, lists, conditions, capsules, locations...), each one
below the block that holds it (see divide.lang.div.outline). Enter (or a
double click) goes there. The list follows the active editor and its edits.
"""

from __future__ import annotations

from divide.i18n import _

from divide.lang import php
from divide.lang.div import outline as div_outline
from divide.ui.runner import DEBUG_CSS, _ListWindow
from divide.ui.windows import EditorWindow, LocationsWindow, ProjectWindow

WIDTH = 36
LANGUAGES = ("php", "div")
NO_OUTLINE = _('(the outline is for PHP files and Div templates)')
PHP_HINT = _('Enter go to the declaration · + public  # protected  - private')
DIV_HINT = _('Enter go to the tag · below a block, what it holds')


class OutlineWindow(_ListWindow):
    """The symbols of ``source``; Enter goes to the one under the bar."""

    DEFAULT_CSS = DEBUG_CSS.format(name="OutlineWindow")
    HINT = PHP_HINT

    def __init__(self, number: int = 0) -> None:
        super().__init__(_('Outline'), number=number)
        self.source: EditorWindow | None = None
        self.symbols: list = []  # php.Symbol or div_outline.Entry: .text, .start, .end
        self.text: str | None = None  # the source's text the list was made from
        self.hint = PHP_HINT

    def load(self, source: EditorWindow | None) -> None:
        self.source = source
        lang = source.editor.lang if source is not None else None
        self.text = source.editor.text if source is not None else None
        self.symbols = []
        if source is None or lang not in LANGUAGES:
            lines = [NO_OUTLINE]
        elif lang == "div":
            self.hint = DIV_HINT
            self.symbols = div_outline.outline(source.editor.text, source.editor.div_blocks())
            lines = [s.text for s in self.symbols] or [_('(no Div tags)')]
        else:
            self.hint = PHP_HINT
            found = php.outline(source.editor.text)
            self.symbols = found or []
            if found is None:
                lines = [_('(no PHP grammar: pip install tree-sitter-php)')]
            else:
                lines = [s.text for s in self.symbols] or [_('(no declarations)')]
        name = source.path.name if source is not None and source.path is not None else ""
        self.title = _('Outline: {name}').format(name=name) if name else _('Outline')
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
        window.load(self.active_editor() or self._outline_editor())
        self.raise_window(window)
        window.list.focus()

    def _outline_editor(self) -> EditorWindow | None:
        """The editor on top of the others with an outline (the outline is opened from a non-editor)."""
        return next((w for w in reversed(self.windows()) if isinstance(w, EditorWindow) and w.editor.lang in LANGUAGES), None)

    def _right_window(self, window: OutlineWindow) -> None:
        """Along the right edge; the windows under it end where it starts."""
        width = self.desktop.size.width or 80
        left = max(20, width - WIDTH)
        window.styles.width = width - left
        window.styles.height = "100%"
        window.styles.offset = (left, 0)
        for other in self.windows():
            if other.zoomed or isinstance(other, (_ListWindow, ProjectWindow)) or isinstance(other, LocationsWindow):
                continue
            x = int(other.styles.offset.x.value) if other.styles.offset.x else 0
            if x < left and x + (other.size.width or width) > left and left - x >= 20:
                other.styles.width = left - x
        self.insert_window(window)

    def follow_outline(self, editor: EditorWindow | None = None) -> None:
        """The active editor changed, or its text did: the outline follows."""
        window = self.outline_window()
        if window is None:
            return
        editor = editor or self.active_editor()
        if editor is None or editor.editor.lang not in LANGUAGES:
            return
        if editor is not window.source or window.text != editor.editor.text:
            window.load(editor)
