"""What a Function asks its context for, read from its file (divide.run.funcscan, #23): the doubles the
Mock Simulation dialog pre-fills. Nothing here runs PHP."""

from divide.run import funcscan as fs
from divide.run import funcsim

SOURCE = """<?php
return function (array &$ctx): string {
    $tax = $ctx["_importer"]("tax", "billing");
    $greet = $ctx['_importer'];
    $greet('greet');
    $greet($computed);
    $mail = $ctx['mailer'];
    $mail->send(1);
    $mail?->log("x");
    $mail->send(2);
    $ctx["repo"]->find(2)->save();
    $ctx['_logger']("INFO", "x");
    $ctx['_flow_state']->x();
    $rows[0]->save();
    $other['mailer']->forget();
    $method = "dyn";
    $ctx['repo']->$method();
    return "";
};
"""


def test_imports_and_services_are_found_through_variables_too():
    scan = fs.scan_text(SOURCE)
    assert scan.readable
    assert scan.imports == ["billing:tax", "greet"]
    assert scan.dynamic == [6]  # a name computed at run time: where, never a guess
    # the context's own variable only ($ctx), Runner's '_' keys left out, a method in a variable unknowable
    assert scan.services == {"mailer": ["send", "log"], "repo": ["find"]}


def test_the_doubles_are_placeholders_a_scenario_accepts():
    scan = fs.scan_text(SOURCE)
    doubles = scan.doubles()
    assert doubles == {"importer": {"billing:tax": {"returns": None}, "greet": {"returns": None}},
                       "services": {"mailer": {"send": {"returns": None}, "log": {"returns": None}},
                                    "repo": {"find": {"returns": None}}}}
    scenario = funcsim.new_scenario(None, "checkout")
    scenario["doubles"] = doubles
    assert funcsim.check_scenario(scenario) == []


def test_missing_and_merge_keep_what_the_user_wrote():
    scan = fs.scan_text(SOURCE)
    mine = {"importer": {"billing:tax": {"returns": 21}}, "services": {"mailer": {"send": {"throws": "down"}}}}
    assert scan.missing(mine) == ["greet", "mailer->log", "repo->find"]
    merged = fs.merge(mine, scan)
    assert merged["importer"]["billing:tax"] == {"returns": 21} and merged["services"]["mailer"]["send"] == {"throws": "down"}
    assert scan.missing(merged) == []
    assert mine == {"importer": {"billing:tax": {"returns": 21}}, "services": {"mailer": {"send": {"throws": "down"}}}}


def test_a_callable_without_a_context_parameter_and_unreadable_files():
    assert fs.scan_text("<?php\nreturn function () { $context['mailer']->send(); };\n").services == {}
    arrow = fs.scan_text("<?php\nreturn fn (array $c) => $c['clock']->now();\n")
    assert arrow.services == {"clock": ["now"]}
    assert not fs.scan_file(__import__("pathlib").Path("/no/such/file.php")).readable
