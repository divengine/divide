# Function simulation: proof of concept (#15)

Feasibility code for [docs/function-simulation.md](../../docs/function-simulation.md). It is not part of divide's package and is not wired to the UI.

The engine (harness, scenarios, doubles, limits, tripwire) is now `divide.run.funcsim` (#21). This prototype stays only for its line trace, until #22 promotes it; its tests are the line-trace cases of `tests/test_funcsim_poc.py`.

| File | What it is |
|---|---|
| `funcsim.php` | The PHP harness. It loads one Function file and calls it with the scenario's context. `_importer` and the service objects are doubles, and the project's autoload is off unless the scenario opts in. |
| `funcsim.py` | The driver. It checks the scenario, runs the harness (plain or with the line trace over DBGp, reusing `divide.run.dbgp.DebugSession`) and prints `divide.function-trace` v1. |
| `example/` | Functions and a scenario used by `tests/test_funcsim_poc.py`. |

Try it from the repository's root:

```bash
.venv/bin/python prototypes/function-simulation/funcsim.py prototypes/function-simulation/example \
    functions/checkout.php prototypes/function-simulation/example/checkout.scenario.json --trace
```

The command takes these options:

- `--trace` needs Xdebug (in php.ini, or `DIVIDE_XDEBUG=/path/xdebug.so`);
- `--tripwire` adds `disable_functions` and `open_basedir`.

**This runs the Function's real PHP code. It is not a sandbox.**
