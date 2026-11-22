"""Runner Modules and Functions in divide (divide.run.flowfunctions): the catalog, making them, and
the project's .div/runner.json, checked against the real Runner on a copy of examples/generator.

What needs no PHP (names, templates read by tree-sitter, the catalog, precedence) always runs;
what runs Runner needs php and ``composer install --working-dir examples/generator``, and skips
without them.
"""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from divide.run import flowfunctions as ff
from divide.run import flowmodel as fm
from divide.run.flow import find_runner, run_flow

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
FLOW = "flows/generate_php_dto.yml"
VENDOR = EXAMPLE / "vendor"
has_runner = bool(shutil.which("php")) and (VENDOR / "divengine" / "runner" / "bin" / "run.php").is_file() \
    and (VENDOR / "divengine" / "div" / "src" / "div.php").is_file()
needs_runner = pytest.mark.skipif(not has_runner, reason="needs php and composer install --working-dir examples/generator")
needs_php = pytest.mark.skipif(not shutil.which("php"), reason="needs php")
CONTEXT = {"model": "model/package_info.json", "output": "build"}


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", ".div", "composer.lock"))
    if VENDOR.is_dir():
        try:
            (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
        except OSError:  # Windows without the right to make links
            shutil.copytree(VENDOR, root / "vendor")
    return root.resolve()


def functions(project: Path, context: dict | None = None, root: str = "functions") -> fm.Functions:
    return fm.functions_for(project, root, context or {}, ff.load_settings(project))


def run(project: Path, context: dict | None = None, flow: str = FLOW, root: str | None = "functions"):
    runner = find_runner(project)
    assert runner.usable, runner.problem
    return asyncio.run(run_flow(runner, project / flow, cwd=project, context_text=json.dumps(context or CONTEXT),
                                functions=(project / root) if root is not None else None))


def lint(path: Path) -> None:
    result = subprocess.run(["php", "-l", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "No syntax errors" in result.stdout, result.stdout + result.stderr


def add_step(project: Path, after: str, step_id: str, values: dict, block: str = "main", flow: str = FLOW) -> str:
    """A Step written as the Designer writes it: one edit of the YAML, verified by parsing it again."""
    path = project / flow
    doc = fm.parse(path.read_text(encoding="utf-8"))
    change = fm.add_step(doc, doc.block(block), doc.step(block, after), step_id, values)
    text = fm.apply(doc.text, change)
    assert fm.verify(doc, text, block, step_id, values) is None
    path.write_text(text, encoding="utf-8")
    return text


# ------------------------------------------------------------------ the catalog
def test_the_catalog_of_the_generator_has_its_modules_functions_and_steps(project):
    cat = ff.catalog(project, functions(project))
    assert [f.name for f in cat.root_functions] == ["load_model", "outputs_current", "write_report"]
    assert [(m.name, [f.name for f in m.functions]) for m in cat.modules] == [
        ("quality", ["lint", "verify"]), ("render", ["manifest", "php_class", "readme"]),
        ("validate", ["has_problems", "identifiers", "reject", "schema"])]
    assert all(m.origin == fm.MODULE_FOLDER and m.inside and m.exists for m in cat.modules)
    assert cat.flows == [project / FLOW] and cat.missing == []
    reject = cat.entry("validate", "reject")
    assert [(r.step_name, r.key) for r in reject.references] == [("validate.reject", "activity")]
    assert [(r.step_name, r.key) for r in cat.entry("validate", "has_problems").references] == [("validate.reject", "condition")]
    assert cat.entry(None, "outputs_current").roles == ["condition"]
    for entry in cat.entries():  # the example's own callables, read and not judged
        assert entry.source.form in ("closure", "arrow") and not [p for p in entry.source.problems if p[0] != "note"]
        assert entry.source.signature.startswith("(array &$context)")


def test_the_same_name_in_two_modules_and_the_root_stays_three_functions(project):
    fns = functions(project)
    for module in ("alpha", "beta"):
        ff.create_module(fns, project, module)
        ff.create_function(fns, project, module, "same", "activity")
    ff.create_function(fns, project, None, "same", "condition")
    cat = ff.catalog(project, functions(project))
    found = {e.qualified: e.path for e in cat.entries() if e.name == "same"}
    assert found == {"same": project / "functions/same.php", "alpha:same": project / "functions/alpha/same.php",
                     "beta:same": project / "functions/beta/same.php"}
    with pytest.raises(ff.CreateError, match="already there"):
        ff.create_function(fns, project, "alpha", "same", "condition")
    with pytest.raises(ff.CreateError, match="already there"):
        ff.create_module(fns, project, "beta")
    with pytest.raises(ff.CreateError, match="already there"):
        ff.create_function(fns, project, None, "load_model", "activity")  # never over an existing Function
    assert "return function (array &$context): bool" in (project / "functions/same.php").read_text()  # not rewritten


def test_names_that_runner_or_the_filesystem_would_refuse_are_refused(project):
    fns = functions(project)
    for bad in ("", "-x", "a b", "a.b", "vendor", "../up", "a/b"):
        assert ff.module_name_problem(bad), bad
        with pytest.raises(ff.CreateError):
            ff.create_module(fns, project, bad)
    for bad, module in (("", None), ("x.php", None), ("../x", "render"), ("a/b", None), ("a b", None), ("a//b", "render"),
                        ("./x", "render"), ("x.y", "render"), ("-x", None)):
        assert ff.function_name_problem(bad, module), (bad, module)
        with pytest.raises(ff.CreateError):
            ff.create_function(fns, project, module, bad, "activity")
    assert ff.function_name_problem("tax/compute", "render") is None  # a folder inside a Module, as Runner allows
    with pytest.raises(ff.CreateError, match="activity or a condition"):
        ff.create_function(fns, project, None, "ok", "step")
    assert sorted(p.relative_to(project).as_posix() for p in (project / "functions").rglob("*.php")) == sorted(
        p.relative_to(EXAMPLE).as_posix() for p in (EXAMPLE / "functions").rglob("*.php"))  # nothing was written


def test_nothing_is_written_outside_the_project_or_in_vendor_and_external_modules_are_shown(project, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "stamp.php").write_text("<?php\nreturn fn (array &$context) => 'stamped';\n")
    fns = functions(project, {"_modules": {"shared": str(shared)}})
    cat = ff.catalog(project, fns)
    module = cat.module("shared")
    assert (module.origin, module.inside, [f.name for f in module.functions]) == (fm.MODULE_CONTEXT, False, ["stamp"])
    with pytest.raises(ff.CreateError, match="outside the project"):
        ff.create_function(fns, project, "shared", "other", "activity")
    with pytest.raises(ff.CreateError, match="outside the project"):
        ff.create_function(functions(project, root=str(tmp_path)), project, None, "loose", "activity")
    (project / "vendor_root").mkdir()
    (project / "composer.json").write_text(json.dumps({"config": {"vendor-dir": "vendor_root"}}))
    with pytest.raises(ff.CreateError, match="vendor"):
        ff.create_function(functions(project, root="vendor_root"), project, None, "x", "activity")
    assert sorted(p.name for p in shared.iterdir()) == ["stamp.php"]


def test_making_takes_back_exactly_what_it_made(project):
    fns = functions(project)
    made = ff.create_function(fns, project, "fresh", "deep/name", "activity")
    assert made.folders == [project / "functions/fresh", project / "functions/fresh/deep"]
    assert made.undo() and not (project / "functions/fresh").exists()
    made = ff.create_function(fns, project, "render", "extra", "condition")
    assert made.folders == []
    made.path.write_text(made.text + "// mine\n")
    assert not made.undo() and made.path.is_file()  # edited since: it stays


def test_missing_references_are_found_and_unqualified_ones_may_be_php_callables(project):
    add_step(project, "report", "later", {"module": "render", "activity": "nowhere"})
    add_step(project, "later", "builtin", {"condition": "is_array"})
    cat = ff.catalog(project, functions(project))
    assert [(r.qualified, r.step_name, r.may_be_callable) for r in cat.missing] == [
        ("render:nowhere", "main.later", False), ("is_array", "main.builtin", True)]
    found = fm.diagnose(fm.parse((project / FLOW).read_text()), functions(project), project, None)
    assert [d.message for d in found] == [
        "activity render:nowhere: no file functions/render/nowhere.php",
        "condition is_array: no file functions/is_array.php; Runner tries a PHP callable"]


def test_open_buffers_are_read_instead_of_their_files(project):
    flow = project / FLOW
    doc = fm.parse(flow.read_text())
    change = fm.edit_step(doc, doc.step("main", "report"), {"activity": "unsaved_name"})
    cat = ff.catalog(project, functions(project), texts={flow: fm.apply(doc.text, change)})
    assert [r.qualified for r in cat.missing] == ["unsaved_name"] and cat.entry(None, "write_report").references == []


# ------------------------------------------------------------------ reading a Function (never running it)
@pytest.mark.parametrize("source, form, problems", [
    ("<?php\nreturn function (array &$context): mixed { return 1; };\n", "closure", []),
    ("<?php\nreturn static fn (array &$context): bool => true;\n", "arrow", []),
    ("<?php\nreturn function (?array &$c = null) { return 1; };\n", "closure", []),
    ("<?php\nreturn function () { return 1; };\n", "closure", []),  # takes nothing: fine for Runner
    ("<?php\nreturn 'strtoupper';\n", "other", []),
    ("<?php\nreturn new class { public function __invoke(array &$context) {} };\n", "other", []),
    ("<?php\nreturn require __DIR__ . '/real.php';\n", "other", []),
    ("<?php\nreturn function (array $context): bool { return true; };\n", "closure", ["note"]),
    ("<?php\nreturn function (array &$context, int $n) {};\n", "closure", ["error"]),
    ("<?php\nreturn function (string &$context) {};\n", "closure", ["error"]),
    ("<?php\nfunction helper() {}\n", "none", ["error"]),
    ("<?php\nreturn function (array &$context) {\n", "unknown", []),  # PHP's lint says what is wrong
])
def test_the_callable_is_read_without_running_it(source, form, problems):
    info = ff.inspect_text(source)
    assert info.form == form and [p[0] for p in info.problems] == problems


def test_importer_calls_written_literally_are_linked_and_computed_ones_are_unknown(project):
    (project / "functions/report_twice.php").write_text(
        "<?php\nreturn function (array &$context): mixed {\n"
        "    $lint = $context['_importer']('lint', 'quality');\n"
        "    $import = $context['_importer'];\n"
        "    $load = $import(\"load_model\");\n"
        "    $any = $context['_importer']($context['which'], 'render');\n"
        "    return $lint($context);\n};\n")
    cat = ff.catalog(project, functions(project))
    entry = cat.entry(None, "report_twice")
    assert [(i.qualified, i.line, i.dynamic) for i in entry.source.imports] == [
        ("quality:lint", 3, False), ("load_model", 5, False), ("?", 6, True)]
    assert [(e.qualified, i.line) for e, i in cat.entry("quality", "lint").imported_by] == [("report_twice", 3)]
    assert [(e.qualified, i.line) for e, i in cat.entry(None, "load_model").imported_by] == [("report_twice", 5)]


def test_a_function_runner_cannot_call_is_a_flow_problem_where_the_step_names_it(project):
    (project / "functions/render/readme.php").write_text("<?php\nreturn function (array &$context, $extra) { return 1; };\n")
    doc = fm.parse((project / FLOW).read_text())
    found = fm.diagnose(doc, functions(project), project, None, inspect=ff.inspect_source)
    assert [(d.severity, d.message) for d in found] == [
        ("error", "activity render:readme: functions/render/readme.php: the callable needs 2 arguments: Runner passes only the context")]
    readme = doc.step("generate", "readme").attrs["activity"]
    assert (found[0].start, found[0].end) == (readme.value_start, readme.value_end)


# ------------------------------------------------------------------ the project's settings
def test_settings_precedence_flow_root_then_context_then_project_file_then_project(project):
    assert ff.load_settings(project) == ff.ProjectSettings(project / ".div/runner.json")
    (project / ".div").mkdir()
    (project / ".div/runner.json").write_text(json.dumps({"root": "functions", "modules": {"render": "functions/quality"}}))
    settings = ff.load_settings(project)
    assert (settings.exists, settings.root, settings.modules, settings.problems) == (True, "functions", {"render": "functions/quality"}, ())
    fns = fm.functions_for(project, "", {}, settings)
    assert (fns.root, fns.origin, fns.folder("render"), fns.module_origin("render")) == (
        project / "functions", fm.ROOT_SETTINGS, project / "functions/quality", fm.MODULE_SETTINGS)
    fns = fm.functions_for(project, "", {"_root_folder": "model", "_modules": {"render": "templates"}}, settings)
    assert (fns.root, fns.origin, fns.folder("render"), fns.module_origin("render")) == (
        project / "model", fm.ROOT_CONTEXT, project / "templates", fm.MODULE_CONTEXT)
    fns = fm.functions_for(project, "lib", {"_root_folder": "model"}, settings)
    assert (fns.root, fns.origin) == (project / "lib", fm.ROOT_OPTION)
    assert fm.functions_for(project).origin == fm.ROOT_PROJECT
    assert ff.run_options(settings, "", {}) == ("functions", {"render": "functions/quality"})
    assert ff.run_options(settings, "lib", {"_modules": {"render": "x"}}) == ("lib", {})
    assert ff.run_options(settings, "", {"_root_folder": "model"}) == ("", {"render": "functions/quality"})


def test_a_settings_file_that_is_wrong_says_what_and_is_ignored_there(project):
    (project / ".div").mkdir()
    (project / ".div/runner.json").write_text(json.dumps({"root": 3, "modules": {"bad name": "x", "ok": ""}, "other": 1}))
    settings = ff.load_settings(project)
    assert (settings.root, settings.modules) == ("", {}) and len(settings.problems) == 4
    (project / ".div/runner.json").write_text("{nope")
    assert "not JSON" in ff.load_settings(project).problems[0]


# ------------------------------------------------------------------ with the real Runner
@needs_php
@pytest.mark.parametrize("role", ff.ROLES)
def test_the_templates_are_php_that_lints(project, role):
    made = ff.create_function(functions(project), project, "fresh", f"new_{role}", role)
    lint(made.path)
    text = made.path.read_text()
    assert text.startswith("<?php\n\ndeclare(strict_types=1);\n") and "array &$context" in text
    assert ("): bool {" in text) == (role == "condition")
    assert ff.inspect_source(made.path).problems == ()


@needs_runner
def test_a_module_and_function_made_attached_edited_validated_and_run_by_runner(project):
    """The issue's workflow without the UI: a Module, a Function in it, a Step that uses it, its PHP
    written, the Flow checked by Runner's compiler, then run by Runner."""
    fns = functions(project)
    ff.create_module(fns, project, "publish")
    made = ff.create_function(fns, project, "publish", "stamp", "activity")
    gate = ff.create_function(fns, project, "publish", "has_report", "condition")
    flow = project / FLOW
    comments = flow.read_text().count("#")
    add_step(project, "report", "stamp", {"module": "publish", "condition": "has_report", "activity": "stamp"})
    assert flow.read_text().count("#") == comments  # the Flow's comments are where they were
    made.path.write_text(made.text.replace("    return null;",
                                           "    $context['stamped'] = $context['regenerated'];\n    return 'stamped ' . count($context['trail']);"))
    gate.path.write_text(gate.text.replace("return true;", "return ($context['report'] ?? '') !== '';"))
    doc = fm.parse(flow.read_text())
    runner = find_runner(project)
    result = asyncio.run(fm.check(runner.bootstrap, doc.text, "generate_php_dto.yml", fm.function_names(doc)))
    assert result.ok, result.error
    assert fm.diagnose(doc, functions(project), project, result, inspect=ff.inspect_source) == []
    done = run(project)
    assert (done.state, done.exit_code) == ("done", 0), done.stderr
    assert done.context["stamp"] == "stamped 9" and done.context["stamped"] is True
    cat = ff.catalog(project, functions(project))
    assert [(r.step_name, r.key) for r in cat.entry("publish", "stamp").references] == [("main.stamp", "activity")]
    assert [(r.step_name, r.key) for r in cat.entry("publish", "has_report").references] == [("main.stamp", "condition")]
    assert cat.missing == []


@needs_runner
def test_same_names_in_modules_resolve_as_runner_resolves_them(project, tmp_path):
    fns = functions(project)
    for module in ("alpha", "beta"):
        made = ff.create_function(fns, project, module, "which", "activity")
        made.path.write_text(made.text.replace("return null;", f"return '{module}';"))
    root = ff.create_function(fns, project, None, "which", "activity")
    root.path.write_text(root.text.replace("return null;", "return 'root';"))
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "which.php").write_text("<?php\nreturn fn (array &$context): string => 'mapped';\n")
    add_step(project, "report", "a", {"module": "alpha", "activity": "which"})
    add_step(project, "a", "b", {"module": "beta", "activity": "which"})
    add_step(project, "b", "plain", {"activity": "which"})
    add_step(project, "plain", "ext", {"module": "gamma", "activity": "which"})
    context = {**CONTEXT, "_modules": {"gamma": str(outside)}}
    done = run(project, context)
    assert done.state == "done", done.stderr
    assert [done.context[k] for k in ("a", "b", "plain", "ext")] == ["alpha", "beta", "root", "mapped"]
    fns = functions(project, context)
    assert [fns.find("which", m, project) for m in ("alpha", "beta", None, "gamma")] == [
        project / "functions/alpha/which.php", project / "functions/beta/which.php", project / "functions/which.php",
        outside / "which.php"]


@needs_runner
def test_existing_callables_of_other_shapes_keep_working_and_are_never_rewritten(project):
    shapes = {"invokable": "<?php\nreturn new class {\n    public function __invoke(array &$context): string { return 'object'; }\n};\n",
              "by_value": "<?php\nreturn fn (array $context): string => 'arrow ' . $context['dto']['class'];\n",
              "named": "<?php\nfunction named_step(array &$context): string { return 'named'; }\nreturn 'named_step';\n"}
    for name, source in shapes.items():
        (project / f"functions/{name}.php").write_text(source)
    previous = "report"
    for name in shapes:
        add_step(project, previous, name, {"activity": name})
        previous = name
    done = run(project)
    assert done.state == "done", done.stderr
    assert [done.context[k] for k in shapes] == ["object", "arrow PackageInfo", "named"]
    for name, source in shapes.items():
        assert (project / f"functions/{name}.php").read_text() == source
        with pytest.raises(ff.CreateError):
            ff.create_function(functions(project), project, None, name, "activity")
    doc = fm.parse((project / FLOW).read_text())
    assert fm.diagnose(doc, functions(project), project, None, inspect=ff.inspect_source) == []
