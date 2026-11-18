# PyInstaller recipe for the standalone ``divide`` binary (one file, no Python needed).
# Build from the repository root: pyinstaller packaging/divide.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
# Textual and the Turbo Vision widgets load their parts lazily, and keep CSS and queries beside the code.
for package in ("divide", "textual", "textual_vision"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
# Rich finds Pygments' lexers and styles by name.
hiddenimports += collect_submodules("pygments")
for grammar in ("tree_sitter_php", "tree_sitter_html", "tree_sitter_css", "tree_sitter_javascript",
                "tree_sitter_markdown", "tree_sitter_sql", "tree_sitter_xml", "tree_sitter_yaml",
                "tree_sitter_toml", "tree_sitter_bash"):
    hiddenimports.append(grammar)
    datas += collect_data_files(grammar)

a = Analysis(
    ["divide_main.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="divide",
    console=True,
    upx=False,
)
