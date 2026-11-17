# Web Server

**Run > Web server…** starts PHP's built-in web server (`php -S`) for the project. You open the pages in the browser, and the [[debugger|Debugging PHP]] stops their requests at your breakpoints, as it stops a script.

![Run > Web server: the address, the document root and the router](images/web-server-dialog.png)

![php -S from divide: a request stopped at a breakpoint, $_GET watched, the log](images/web-server.gif)

## Starting it

The dialog asks for:

- **Address**: `host:port`, `127.0.0.1:8000` at first. Use `0.0.0.0:8000` to reach it from other machines.
- **Document root**: the folder whose files are the site (`-t`). It starts as the project's folder. **Root…** picks another folder: in the list, enter folders with Enter, then OK on `.` (the name line) chooses the folder shown.
- **Router script** (optional): a PHP file that receives every request, as frameworks use (`public/index.php`). **Router…** picks it.
- **Open in the browser**: opens the site's address when the server starts.

**Start** runs `php -S address -t root [router]`. If PHP cannot serve (the port is taken, for example), a box shows what PHP said. These values are remembered per project.

Run > Web server again, while the server runs, offers **Open in browser** and **Stop server**. Leaving divide stops it too.

## The Web server window

The server's log opens at the bottom, under the page you were editing: each request (`127.0.0.1:50658 [200]: GET /?page=2`) and PHP's warnings and errors. Those errors also go to the **Messages** window with their place, so **Enter** opens the file at their line, as after [[Running PHP]].

What the pages print goes to the browser, not to the Output window.

## Debugging requests

With Xdebug (see [[Debugging PHP]] for installing it), every request that runs PHP connects to divide:

- **No breakpoint on its way**: the request runs through, at normal speed.
- **A breakpoint** (Ctrl+F8) on a line it runs: it pauses there. The cyan bar, F7, F8, Shift+F8, F4, Watches, Evaluate and the Call stack work as for a script. The status line says which request it is: `Paused at index.php:14 (GET /?page=2)`. The browser waits for the page until you let the request go on (Ctrl+F9).
- **F8 or F7 with no request paused**, in a file the server serves: the next request stops on its first line. **F4** makes it stop at the cursor's line. Ctrl+F2 cancels that.
- **Ctrl+F2** on a paused request ends it: the browser gets what the request printed so far.

![a request of the shop paused on a breakpoint, the server's log below](images/web-debug.png)

Without Xdebug the server runs all the same, and its pages just are not debugged.

## Ctrl+F9 on a page

While the server runs, **Ctrl+F9** in a PHP file under the document root (or the router's folder) does not run it from the command line: it opens its address in the browser (`/shop/cart.php`; `/` for `index.php`, and for everything when there is a router). The request then stops at its breakpoints. Stop the server to run those files from the command line again.

## Limits

- One request at a time: `php -S` has one worker, so while a request is paused the next ones wait, the page's images and styles too when a router sends them through PHP.
- Requests handled before you set a breakpoint are not stopped again: reload the page.
- It is a development server, as PHP says: not for production.

Back: [[Debugging PHP]].
