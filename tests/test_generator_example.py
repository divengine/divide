"""examples/generator: a generator developed in divide, run through the real Runner and Div.

The example turns model/package_info.json into a PHP DTO class and its README with Div
templates, and flows/generate_php_dto.yml orders the stages: load, validate (a call),
skip when the outputs are current (a jump), generate (a call), lint and verify (a call),
report. Each test runs a copy of it (its vendor/ from ``composer install --working-dir
examples/generator``) as divide does, with Runner's own bootstrap; without php or that
installation, the tests skip.
"""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from divide.run import flowmodel as fm
from divide.run.flow import find_runner, run_flow

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generator"
FLOW = "flows/generate_php_dto.yml"
VENDOR = EXAMPLE / "vendor"
needs_generator = pytest.mark.skipif(
    not (shutil.which("php") and (VENDOR / "divengine" / "runner" / "bin" / "run.php").is_file()
         and (VENDOR / "divengine" / "div" / "src" / "div.php").is_file()),
    reason="needs php and composer install --working-dir examples/generator")
pytestmark = needs_generator

ALL = ["load", "schema", "identifiers", "php", "readme", "manifest", "lint", "verify", "report"]
SKIPPED = ["load", "schema", "identifiers", "lint", "verify", "report"]


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "generator"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "vendor", ".div", "composer.lock"))
    try:
        (root / "vendor").symlink_to(VENDOR, target_is_directory=True)
    except OSError:  # Windows without the right to make links
        shutil.copytree(VENDOR, root / "vendor")
    return root


def generate(root: Path, context: dict | None = None):
    runner = find_runner(root)
    assert runner.usable, runner.problem
    text = json.dumps(context or {"model": "model/package_info.json", "output": "build"})
    return asyncio.run(run_flow(runner, root / FLOW, cwd=root, context_text=text, functions=root / "functions"))


def model(root: Path) -> dict:
    return json.loads((root / "model/package_info.json").read_text(encoding="utf-8"))


def save_model(root: Path, value: dict) -> None:
    (root / "model/package_info.json").write_text(json.dumps(value, indent=4) + "\n", encoding="utf-8")


def outputs(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root / "build")): p.read_bytes() for p in sorted((root / "build").rglob("*")) if p.is_file()}


def php(code: str, cwd: Path) -> str:
    return subprocess.run(["php", "-r", code], cwd=cwd, capture_output=True, text=True, check=True, timeout=30).stdout


def test_the_generator_runs_and_its_php_parses_and_says_what_the_model_says(project):
    run = generate(project)
    assert (run.state, run.exit_code) == ("done", 0), run.stderr
    assert run.context["trail"] == ALL  # validate., generate. and quality.lint each came back into main
    assert run.context["_flow_stack"] == [] and run.context["regenerated"] is True
    assert run.context["report"] == "PackageInfo: generated, 2 files, 13 checks passed"
    built = outputs(project)
    assert set(built) == {"src/PackageInfo.php", "README.md", "manifest.json", "report.json"}  # build/ only
    lint = subprocess.run(["php", "-l", str(project / "build/src/PackageInfo.php")], capture_output=True, text=True)
    assert lint.returncode == 0 and "No syntax errors" in lint.stdout
    source = built["src/PackageInfo.php"].decode()
    assert "namespace Acme\\Registry\\Dto;" in source and "final class PackageInfo" in source
    for field in model(project)["fields"]:
        kind = ("?" if field.get("nullable") else "") + field["type"]
        assert f"public readonly {kind} ${field['name']}," in source
        assert f"| `{field['name']}` | `{kind}` | {field['description']} |" in built["README.md"].decode()
    # the class itself, loaded by PHP: the model's fields, in order, and its data back
    said = php("require 'build/src/PackageInfo.php'; $c = new ReflectionClass('Acme\\Registry\\Dto\\PackageInfo');"
               "foreach ($c->getConstructor()->getParameters() as $p) echo $p->getName(), ':', $p->getType(), \"\\n\";"
               "$d = ['name' => 'divengine/div', 'version' => '6.1.4', 'license' => 'GPL-3.0-or-later',"
               " 'downloads' => 10, 'score' => 0.9, 'abandoned' => false, 'homepage' => null];"
               "echo Acme\\Registry\\Dto\\PackageInfo::fromArray($d)->toArray() === $d ? 'same' : 'different';", project)
    assert said.splitlines() == ["name:string", "version:string", "license:string", "downloads:int", "score:float",
                                 "abandoned:bool", "homepage:?string", "same"]
    report = json.loads(built["report.json"])
    assert report["regenerated"] is True and report["stages"] == ALL and report["lint"] == "ok"
    assert set(report["outputs"]) == {"src/PackageInfo.php", "README.md"}


def test_an_unchanged_second_run_jumps_over_generation_and_writes_nothing_else(project):
    assert generate(project).state == "done"
    before = outputs(project)
    times = {p: p.stat().st_mtime_ns for p in (project / "build").rglob("*") if p.is_file()}
    run = generate(project)
    assert run.state == "done", run.stderr
    assert run.context["trail"] == SKIPPED  # main.current jumped to .verify: no php, readme or manifest
    assert run.context["regenerated"] is False and "php" not in run.context
    assert run.context["report"] == "PackageInfo: up to date, generation skipped, 2 files, 13 checks passed"
    after = outputs(project)
    assert {k: v for k, v in after.items() if k != "report.json"} == {k: v for k, v in before.items() if k != "report.json"}
    assert all(p.stat().st_mtime_ns == t for p, t in times.items() if p.name != "report.json")
    assert json.loads(after["report.json"])["regenerated"] is False


def test_rendering_is_deterministic(project, tmp_path):
    assert generate(project).state == "done"
    first = outputs(project)
    shutil.rmtree(project / "build")
    assert generate(project).state == "done"
    assert outputs(project) == first  # byte for byte, the report included


def test_a_changed_model_or_template_or_an_edited_output_regenerates(project):
    assert generate(project).state == "done"
    value = model(project)
    value["fields"].append({"name": "stars", "type": "int", "description": "Stars on the forge"})
    save_model(project, value)
    run = generate(project)
    assert run.context["trail"] == ALL and run.context["regenerated"] is True
    assert "public readonly int $stars," in (project / "build/src/PackageInfo.php").read_text()
    assert "| `stars` | `int` | Stars on the forge |" in (project / "build/README.md").read_text()
    assert run.context["verify"] == 14  # one check more: the new field's type
    assert generate(project).context["trail"] == SKIPPED

    template = project / "templates/readme.tpl"
    template.write_text(template.read_text().replace("# {$class}", "# The {$class} class"))
    assert generate(project).context["trail"] == ALL
    assert (project / "build/README.md").read_text().startswith("# The PackageInfo class\n")

    with (project / "build/src/PackageInfo.php").open("a") as f:
        f.write("// edited by hand\n")
    assert generate(project).context["trail"] == ALL
    assert "edited by hand" not in (project / "build/src/PackageInfo.php").read_text()


def test_an_invalid_model_ends_the_run_before_anything_is_written(project):
    value = model(project)
    value["class"] = "package info"
    value["fields"] += [{"name": "score", "type": "float"}, {"name": "tags", "type": "array"}]
    save_model(project, value)
    run = generate(project)
    assert (run.state, run.exit_code) == ("error", 1)
    assert run.context["trail"] == ["load", "schema", "identifiers"]  # validate.reject stopped it
    error = run.context["_runner_error"]
    assert "The model is not valid" in error and '"package info" must be a PHP class name' in error
    assert 'field "score" twice' in error and '"type" must be one of string, int, float, bool' in error
    assert not (project / "build").exists()


def test_generated_php_that_does_not_parse_stops_at_the_lint(project):
    template = project / "templates/dto.tpl"
    template.write_text(template.read_text().replace("final class {$class}\n{", "final class {$class}\n{{"))
    run = generate(project)
    assert run.state == "error"
    assert run.context["trail"] == ["load", "schema", "identifiers", "php", "readme", "manifest", "lint"]
    assert "The generated class does not parse" in run.context["_runner_error"]
    assert not (project / "build/report.json").exists()


def test_paths_never_leave_the_generator_or_its_build_folder(project):
    for context, said in (({"model": "model/package_info.json", "output": "src"}, "must be build/ or a folder in it"),
                          ({"model": "model/package_info.json", "output": "build/../.."}, "may not leave"),
                          ({"model": "../../etc/passwd", "output": "build"}, "may not leave the generator")):
        run = generate(project, context)
        assert run.state == "error" and said in run.context["_runner_error"]
    assert not (project / "build").exists() and not (project / "src").exists()
    run = generate(project, {"model": "model/package_info.json", "output": "build/dto"})
    assert run.state == "done" and (project / "build/dto/src/PackageInfo.php").is_file()


def test_the_flow_is_four_blocks_with_its_calls_and_jump_and_divide_finds_no_problem(project):
    from divide.ui.flowlayout import Board

    text = (project / FLOW).read_text(encoding="utf-8")
    doc = fm.parse(text)
    assert [b.id for b in doc.blocks] == ["main", "validate", "generate", "quality"]
    board = Board(doc, card_width=24)
    links = sorted((c.source[1:], c.key, c.target) for c in board.connections)
    assert links == [(("main", "current"), "jump", ("step", "main", "verify")),
                     (("main", "generate"), "call", ("step", "generate", "php")),
                     (("main", "validate"), "call", ("step", "validate", "schema")),
                     (("main", "verify"), "call", ("step", "quality", "lint"))]
    runner = find_runner(project)
    result = asyncio.run(fm.check(runner.bootstrap, text, "generate_php_dto.yml", fm.function_names(doc)))
    assert result.ok, result.error
    assert fm.diagnose(doc, fm.functions_for(project, "functions"), project, result) == []


async def test_divide_runs_the_generator_from_its_flow_designer(project):
    from divide.app import CM_FLOW_DESIGN, Divide
    from divide.ui.flow import FlowDialog, save_flow_settings
    from divide.ui.flowboard import FlowDesignWindow

    flow = project / FLOW
    save_flow_settings(flow.resolve(), {"context": "generate.json", "root": "functions", "save": ""})
    app = Divide(project, [flow])
    async with app.run_test(size=(160, 44)) as pilot:
        async def wait(condition, what):
            for _ in range(300):
                await pilot.pause(0.05)
                if condition():
                    return
            pytest.fail(what)

        await pilot.pause(0.3)
        app.run_command(CM_FLOW_DESIGN)
        await wait(lambda: isinstance(app.active_window(), FlowDesignWindow) and app.active_window().board is not None,
                   "no Flow Designer")
        window = app.active_window()
        assert [lane[0] for lane in window.board.lanes] == [("block", b) for b in ("main", "validate", "generate", "quality")]
        await pilot.press("ctrl+f9")
        await wait(lambda: isinstance(getattr(app.screen, "dialog", None), FlowDialog), "no Run Flow dialog")
        await pilot.press("enter")
        await wait(lambda: app.output_window() is not None and "State: done" in app.output_window().view.text,
                   "the generator did not run")
        assert "PackageInfo: generated, 2 files, 13 checks passed" in app.output_window().view.text
    assert (project / "build/src/PackageInfo.php").is_file()
