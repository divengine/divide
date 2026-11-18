# Git

When the project is a git repository, divide shows what changed and lets you work with it: stage, commit, see the history, switch branches, merge, stash, pull and push, and the pull requests and issues on GitHub or Gitea. It uses the `git` installed on the system, with your settings and credentials. Without git, or outside a repository, the **Git** menu says why.

![Git: the marks, the changes and their diff, a commit, the history, the branches](images/git.gif)

## What changed, at a glance

divide reads the repository's state every few seconds, after a save and after each git command, so what you see follows the work done in a terminal too.

![the project window and the editor's margin with the changes](images/git-marks.png)

- The **project window** puts a letter after each changed file: `M` modified, `A` added, `D` deleted, `R` renamed, `?` new (untracked), `U` a conflict. A folder holding changes shows `•`; ignored files and folders are dimmed. Its bottom border shows the branch and how many files changed.
- The **editor's margin** colours the line numbers against the last commit: yellow a changed line, green an added one, red where lines were deleted. It follows the edits as you type, before saving.

## The Git menu

![the Git menu](images/git-menu.png)

| Item | What it does |
|---|---|
| **Changes** | the files that changed and their diff: stage, discard, commit |
| **History** | the commits of every branch, with the graph |
| **Branches** | local and remote branches, and the stashes |
| **Commit...** | commit what is staged |
| **Pull**, **Push**, **Fetch** | with the branch's upstream (a first push sets it); git's words in a progress box |
| **Diff of the file** | the active file against the last commit |
| **File history** | the commits that touched the active file (following its renames) |
| **Blame** | who wrote each line of the active file, and in which commit |
| **Pull requests and issues** | the project's forge: GitHub or Gitea |

## Git > Changes

![Git > Changes: the areas and a unified diff](images/git-changes.png)

On the left, the files by area: **Conflicts** (during a merge), **Staged (the next commit)**, **Changes** and **Untracked**. On the right, the diff of the file under the bar; below, the branch, its upstream (ahead, behind) and the counts.

| Key | Action |
|---|---|
| **Space** | stage the file, or unstage it |
| **Enter** | open the file |
| **Del** | discard its changes (asks first; an untracked file is deleted) |
| **Ctrl+K** | commit |
| **Tab** | to the diff and back |
| **Alt+F10** | stage or unstage everything, amend the last commit, stash, abort a merge, pull, push, fetch |

## The diff

The diff shows the code, not git's output: the removed lines on red, the added ones on green, the rest on the window's colour, with the old and new line numbers and the template's or the language's colours. Inside a changed line, the words that changed are brighter.

**S** shows it side by side: the old file on the left and the new one on the right, lines paired, a hatch where one side has nothing. **S** again goes back to unified. divide remembers the choice.

![the same diff side by side](images/git-diff-split.png)

| Key | Action |
|---|---|
| **↑ ↓ PgUp PgDn Home End** | move |
| **← →** | scroll a long line |
| **N** / **P** | the next / previous change |
| **S** | side by side or unified |
| **Enter** | open the file at that line |

The same diff opens from the history (a commit), from **Git > Diff of the file** and from Blame.

## Commit

**Ctrl+K** (or **Git > Commit...**) asks for the message: its first line is the summary, then a blank line and the details. **Ctrl+Enter** commits; **Enter** starts a new line. Two boxes: **Amend the last commit** (it replaces it, its message to edit) and **Stage every change first**. git's answer stays in the Git window.

![the commit dialog](images/git-commit.png)

## Git > History

![Git > History: the graph and a commit's details](images/git-history.png)

Every branch, newest first, with git's graph, the branches and tags of each commit, its author and date; below, the commit under the bar: hash, author, parents, message and files. **Enter** opens its diff. **Alt+F10**: a new branch at that commit, copy the hash. **File history** shows the same for one file.

## Git > Branches

![Git > Branches: local branches and a stash](images/git-branches.png)

The local branches (`*` the current one), each remote's, and the stashes; beside, the branch's last commit.

| Key | Action |
|---|---|
| **Enter** | switch to the branch (a remote one gets its local branch); on a stash, bring it back and drop it |
| **Ins** | a new branch from the one under the bar |
| **Del** | delete the branch (asks; a branch not merged asks again), or drop the stash |
| **Alt+F10** | merge into the current branch, apply a stash keeping it, pull, push, fetch |

A stash is made from **Git > Changes** (Alt+F10 > Stash the changes...).

## Merging and conflicts

**Merge into the current branch** runs `git merge`. When git cannot merge a file by itself, it goes to **Conflicts** and the Changes window says so; the diff shows the file with git's markers, our side and theirs. Edit the file, **Space** marks it solved, and **Ctrl+K** commits the merge (its message is ready). **Alt+F10 > Abort the merge** goes back to before it.

## Blame

**Git > Blame** shows each line of the active file with the commit, date and author that last changed it; lines not committed yet say so. The status line shows the commit's subject; **Enter** opens that commit's diff.

![Blame of index.tpl](images/git-blame.png)

## Pull requests and issues

**Git > Pull requests and issues** reads them from the forge of the `origin` remote, with its command line tool, signed in as you are:

- **GitHub**: [gh](https://cli.github.com), after `gh auth login`;
- **Gitea**, Forgejo, Codeberg: [tea](https://gitea.com/gitea/tea), after `tea login add`.

If the tool is missing, or the remote is neither, the window says what to do.

![the open pull requests and issues](images/git-forge.png)

| Key | Action |
|---|---|
| **Enter** | open it in the browser |
| **Ins** | a new pull request from the current branch (pushed first); on the issues, a new issue |
| **Alt+F10** | copy the address; on a pull request: check out its branch, merge, squash and merge, rebase and merge |
| **Ctrl+R** | read them again |

See the [[Keyboard Reference#git-windows]].
