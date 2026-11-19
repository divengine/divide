"""A project as divide works on it, without the interface (UI-independent).

What the IDE and divide's MCP server (:mod:`divide.mcpserver`) both need to
know about a project's templates, so that the same question gets the same
answer in both: which Div engine renders them, where Div looks for templates,
which data file a template takes, which dialect a template is in and what is
wrong with it. Div decides what is Div's to decide (where an include leads,
which dialect file ``@_DIALECT`` loads): it is asked through the bridge, see
:mod:`divide.run.render`.
"""

from __future__ import annotations

from divide.i18n import _

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from divide import config
from divide.lang.div.diagnostics import Diagnostic, check, include_paths
from divide.lang.div.dialect import DEFAULT_DIALECT, Dialect, resolve_dialect, template_properties
from divide.lang.div.lexer import tokenize
from divide.run import setup as div_setup
from divide.run.render import IncludeTarget, RenderError, default_data_file, find_engine, load_dialect, resolve_includes


def find_div_engine(root: Path, start_dirs: list[Path]) -> Path | None:
    """Div's engine: $DIVIDE_DIV_PHP, the project's Div setup, Options > Div engine, then vendor/."""
    return find_engine(start_dirs, config.load().get("div_engine"), div_setup.load(root).engine)


def engine_for(root: Path, template: Path) -> Path | None:
    """The engine that renders ``template`` (None: no php, or no Div)."""
    if not shutil.which("php"):
        return None
    return find_div_engine(root, [template.parent, root])


def template_roots(root: Path) -> list[Path]:
    """Where Div looks for templates besides the template's folder: the project, and
    the setup's packages, repository and include paths."""
    setup = div_setup.load(root)
    roots = [root]
    for place in (setup.constants.get("PACKAGES"), setup.constants.get("DIV_REPO"), *setup.include_paths):
        if isinstance(place, str) and (path := Path(place)) not in roots:
            roots.append(path)
    return roots


def data_file(root: Path, template: Path) -> Path:
    """The data file Div's convention gives ``template`` (``page.tpl``: ``page.json``,
    with the project's data extension)."""
    return default_data_file(template, div_setup.load(root).data_ext)


def base_dialect(root: Path) -> Dialect:
    """The project's dialect (its Div setup), else Div's default one."""
    return div_setup.load(root).dialect or DEFAULT_DIALECT


def dialect_ref(text: str) -> str | None:
    """The value of the template's ``@_DIALECT``, None without one."""
    prop = template_properties(text).get("DIALECT")
    return prop[0].strip() if prop and prop[0].strip() else None


def guess_dialect(ref: str, text: str, template: Path | None, roots: list[Path], base: Dialect) -> Dialect:
    """Until Div answers (or without Div): the dialect file looked for in Python, to colour."""
    guess = resolve_dialect(text, template, roots, base)
    if guess.error is not None:  # the base; whether the file is fine is Div's to say
        guess = Dialect(name=ref, tags=dict(base.tags))
    return guess


async def dialect_from_div(engine: Path, root: Path, template: Path, ref: str, *, history: list[Path] | None = None,
                           describe: Callable[[Path], str] = str) -> Dialect | None:
    """The dialect Div loads for ``@_DIALECT = ref`` in ``template`` (None: Div could not be asked)."""
    try:
        loaded = await load_dialect(engine, cwd=root, template=template, ref=ref, history=history)
    except RenderError:
        return None
    if loaded.file is None:
        return Dialect(name=ref, error=_('Div cannot find the dialect file {ref}').format(ref=ref))
    if loaded.tags is None:
        return Dialect(name=ref, source=loaded.file, error=f"{loaded.problem}: {describe(loaded.file)}")
    return Dialect.from_overrides(loaded.tags, name=loaded.file.stem, source=loaded.file, base=base_dialect(root))


async def include_targets(engine: Path, root: Path, template: Path, includes: list[str], dialect: Dialect, *,
                          history: list[Path] | None = None) -> dict[str, IncludeTarget] | None:
    """Where Div takes each include of ``template`` (None: Div could not be asked)."""
    try:
        return await resolve_includes(engine, template, includes, cwd=root, history=history,
                                      separator=dialect["DIV_TAG_PREPROCESSED_SEPARATOR"])
    except RenderError:
        return None


@dataclass
class TemplateCheck:
    """What divide finds wrong in a template, as the editor shows it."""

    dialect: Dialect
    diagnostics: list[Diagnostic]
    includes: dict[str, IncludeTarget] = field(default_factory=dict)  # Div's answers
    div_asked: bool = False  # Div told the dialect and the includes (without it: a guess, includes unchecked)


async def check_template(root: Path, template: Path, text: str, *, engine: Path | None,
                         history: list[Path] | None = None, describe: Callable[[Path], str] = str) -> TemplateCheck:
    """The editor's checks of ``text`` (the source of ``template``): its dialect as Div
    loads it, the lexer's tokens in that dialect, Div's answers for its includes."""
    base = base_dialect(root)
    ref = dialect_ref(text)
    dialect: Dialect | None = base if ref is None else None
    asked = engine is not None
    if ref is not None:
        if engine is not None:
            dialect = await dialect_from_div(engine, root, template, ref, history=history, describe=describe)
        if dialect is None:
            asked = False
            dialect = guess_dialect(ref, text, template, template_roots(root), base)
    assert dialect is not None
    tokens = tokenize(text, dialect)
    raws = sorted({raw for _, _, raw in include_paths(text, tokens, dialect)})
    targets: dict[str, IncludeTarget] = {}
    if raws and engine is not None:
        found = await include_targets(engine, root, template, raws, dialect, history=history)
        if found is None:
            asked = False
        else:
            targets = found
    return TemplateCheck(dialect, check(text, tokens, dialect, targets), targets, asked)
