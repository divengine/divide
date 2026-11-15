# Troubleshooting

**Ctrl+F9 on a template says "Div was not found".**
Install Div in the project (`composer require divengine/div`), or point divide at it with **Options > Div engine…** or `DIVIDE_DIV_PHP`. See [[Installation]].

**No warnings about includes, even for a missing one.**
Includes are checked by Div itself, so they need `php` and Div. Check that rendering (Ctrl+F9) works. An untitled template is not checked for includes until it is saved (see *Save first* in [[Checking Templates]]).

**An include is reported but Div finds it when rendering.**
Div also looks relative to the templates included before. divide gives Div the last template you rendered as that history: render from the main template (the one that includes this one) and check again.

**Ctrl+Enter does nothing.**
Some terminals do not send Ctrl+Enter at all. Use **Ctrl+J**, Ctrl+click, or Search > Go to included template.

**Ctrl+Space does nothing.**
Some terminals or desktop environments take Ctrl+Space for themselves (input method switching). Use Edit > Complete, or free the shortcut in your system settings.

**Alt+letter does not open the menus.**
Your terminal may be sending Alt as Meta differently, or the window manager may grab it. **F10** always opens the menu bar.

**Colours look wrong, or flat.**
divide shows colours as deep as the terminal says it can. Over ssh or inside tmux `COLORTERM` is often lost, and a true-colour terminal looks like a 256-colour one: choose **True colour** in **Options > Colors** (from the next start) or start with `divide --colors truecolor`; for tmux, also tell it the outer terminal has true colour (`set -as terminal-features ",xterm-256color:RGB"`). On a 16-colour terminal choose **16 colours**. The themes are also in **Options > Colors**.

**`$references` in my data come out empty.**
That is Div: a data file is decoded before any variable exists. Use them in JSON inside templates (`{= x: {"a": $b} =}`). divide adds a note when it renders data that uses references.

**The dialector marks a section with `≈` that looks right.**
Div translated the example back and got something else. The verdict shows the line you wrote and what Div read. If the difference is in a tag you did not change (for instance a `{%% path:data %%}` that loses its `:`), the cause is Div's translator, not your dialect. See [[Translating Templates]].

**The debugger says it needs Xdebug, or "PHP ended before Xdebug connected".**
`php -m` must list Xdebug, or **Options > Xdebug…** must name an `xdebug.so` built for your PHP version (`php -v`). The message shows what PHP printed when it failed to load it. See [[Debugging PHP]].

**A script waits forever under Ctrl+F9.**
It is not waiting for the keyboard (its input is closed): it is busy, or waiting on the network. **Esc** stops it. Interactive scripts go in **Run > Run in terminal**.

**The web server does not start.**
The box shows what `php -S` said. `Address already in use`: another program (or another divide) serves that port; choose another port in **Run > Web server**. See [[Web Server]].

**A page never loads.**
A request is paused in the debugger (the status line says `Paused at …`): Ctrl+F9 lets it go on, Ctrl+F2 ends it. While one request is paused the others wait, because `php -S` serves one at a time.

**I found a bug.**
Please open an issue at [divengine/divide](https://github.com/divengine/divide/issues), with the template if you can.
