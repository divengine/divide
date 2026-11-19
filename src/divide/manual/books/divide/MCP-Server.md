# MCP Server

`divide --mcp PROJECT` serves divide's own [Model Context Protocol](https://modelcontextprotocol.io) server for one project, over stdio and without the interface. It lets an AI coding agent, or any MCP client, use what divide does while you develop a generator: the project's [[Div setup|Div Setup]], the editor's [[checks of a template|Checking Templates]], a [[render|Rendering]] and the [[render trace|Render Trace]], through the real Div engine and the same code the IDE runs.

It is the IDE's MCP, not a generator's. A generator that should be used by agents implements its own CLI, HTTP API or MCP server in its own project, and runs without divide.

## Install

The MCP server needs the official MCP SDK for Python, an optional dependency (the `mcp` extra). The ready-made packages (Homebrew, Scoop, the installers) do not include it yet: install divide from the source code with the extra.

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh                    # the divide command, as in Installation
.venv/bin/pip install -e ".[mcp]"   # and the MCP SDK in its .venv
```

Or with pipx:

```bash
pipx install "divide[mcp] @ git+https://github.com/divengine/divide.git"
```

Without the SDK, `divide --mcp` says so and exits. Rendering needs PHP and Div, as in the IDE ([[Installation]]).

## Start it

```bash
divide --mcp /path/to/project
```

The folder is the project: every file the server takes must be inside it. The protocol goes on stdout; anything the server has to say goes to stderr. It ends when the client closes its stdin. Your MCP client starts it; most clients take a configuration like this one:

```json
{
  "mcpServers": {
    "divide": {
      "command": "divide",
      "args": ["--mcp", "/path/to/project"],
      "env": {"DIVIDE_LANGUAGE": "en"}
    }
  }
}
```

`DIVIDE_LANGUAGE` is optional. The server's own texts are in English; the findings of divide's checks and of the Div setup are in divide's language, as in the IDE, and `en` gives everything in English. `DIVIDE_DIV_PHP` chooses the engine, as everywhere in divide.

## Tools

Paths are relative to the project. Where a tool takes `source`, the text is checked or rendered instead of the saved file (the file need not exist yet), with includes and the data file still found from the template's path, as Div does.

| Tool | What it does | Parameters |
|---|---|---|
| `project_info` | The project's folder, PHP's version, the Div engine and where it was found (`DIVIDE_DIV_PHP`, the setup, Options > Div engine, `vendor/`), the Div setup in effect and its files, the project's dialect, the template and data extensions, what divide left out of the setup (file, line, column, why), the project's PHP settings waiting for your trust, and Div's verdict on the setup. Of the simulated request and the globals it gives only the names. | none |
| `div_check` | The checks of the editor (Alt+F8): unclosed blocks, tags Div would leave as text, broken JSON in `{= =}`, a broken `@_DIALECT`, includes Div cannot find. Each finding with its severity, message, offsets, line and column. The dialect and the includes are Div's answers; without PHP or Div the checks still run, on divide's guess of the dialect, and includes are not checked (the answer says so). | `template`, `source` |
| `div_render` | Renders as Ctrl+F9 does: the output, Div's and PHP's messages (with the setup file's line when they are about the setup), `status` (`ok`, `warnings`, `fatal`), Div's version and the time. | `template`, `data_file` (default: the template's, by Div's convention), `source`, `data` (Div JSON text), `use_data_file`, `max_output_chars` (default 20000, up to 200000), `timeout_seconds` (default 20, up to 120) |
| `div_trace` | Renders keeping every mutation Div made on its way to the fixed point, as the render trace: a summary (mutations, changes, sub-parses, the deepest parse level, the cycles of each fixed point), the output and the first page of mutations. Each change says what was removed and inserted (where, and up to 400 characters of it), Div's steps behind it, its parse level, its run (1 the template, 2... its sub-parses) and its cycle. Returns a `trace_id`. | as `div_render`, plus `limit` (the first page, default 50, up to 200); `timeout_seconds` defaults to 60 |
| `div_trace_page` | Another page of a trace, optionally only one kind (`start`, `change`, `end`) or one run. | `trace_id`, `offset`, `limit`, `kind`, `run` |
| `div_trace_mutation` | One mutation in full: the template's text before and after it, and Div's steps. | `trace_id`, `index`, `max_chars` |
| `div_check_dialect` | Div's verdict on a dialect, as the [[Dialector]] asks it: a dialect file of the project (decoded by Div), `DIV_TAG_*` overrides, or the project's dialect. | `dialect_file` or `tags` |

The server keeps the last four traces for paging; an older `trace_id` asks for `div_trace` again.

## Trust and security

- **A render runs the project's PHP.** Div is PHP: the engine the project names, the functions and modifiers its setup allows. That is trusted code running with your rights, not a sandbox. Start the server only on projects you trust, as you would open them in divide.
- **Your trust decisions stay yours.** A project's `php` settings that you have not trusted in **Options > Div setup** stay left out: renders go without them, and `project_info` and every render say so (`untrusted_php`) and how to trust them in divide. The server never trusts them, never writes `~/.div/trust.json`, never asks.
- **Confined to the project.** Templates, data files and dialect files must be inside the project's folder, after following symbolic links: `../`, an absolute path elsewhere or a link that leads out is refused. Div itself still resolves includes and dialects as it does in production, with the setup's include paths.
- **Nothing is written.** The server reads the project; it does not save templates, data or settings. Text you pass as `source` or `data` is rendered, not saved. (What a trusted PHP function of yours does when a template calls it is up to it.)
- **Bounded.** PHP is stopped after the timeout, and when the client cancels a call; outputs, messages, trace pages and texts are cut to the limits above, and the answer says when something was cut. Templates and data of more than 4 million characters are refused.
- **No shell, no files, no network.** There is no tool to run commands, list or edit files, or use git, and the server listens on no port: only stdio.

## Limitations

- It works on the files of the project and on the text you pass. It does not see divide's open editors, their unsaved changes, the active template or its selection, and it does not edit anything.
- A data file you chose for a template in **Run > Data file** is not known to the server: pass `data_file`.
- One project per server. Start one per project.
- The ready-made packages do not include the MCP SDK yet (see Install).
