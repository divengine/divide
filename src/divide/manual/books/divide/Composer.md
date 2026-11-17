# Composer

**Tools > Composer packages...** shows the project's packages and runs [Composer](https://getcomposer.org) for them: add Div or any package from Packagist, remove, update, install, look for newer versions. divide never edits `composer.json` behind composer's back: composer does every change, under the progress box, and its output stays in the **Composer** window.

![Tools > Composer packages: the packages, and the one under the bar](images/composer.png)

![adding a package: Packagist searched, composer require under the progress box](images/composer.gif)

## The window

- **Left: the packages.** What `composer.json` requires (`req`), its development packages (`dev`), the packages composer installed with them (`dep`) and the platform (`php`, extensions), each with its installed version (from `composer.lock`). `↑` marks a package with a newer version, once you looked for them.
- **Right: the package under the bar.** Its description, kind, the version required and installed, the newer one, type, license, homepage, source, what it requires and what requires it.
- **Below the list:** the project (its name, how many packages), whether it is installed, and how the last command ended.

| Key | |
|---|---|
| **Ins** | add a package (the assistant below) |
| **Del** | remove the package (`composer remove`), after confirming. Only packages the project requires: a dependency goes when what requires it goes. |
| **Enter** / double click | the package's folder (`vendor/...`) in the [[Project Window]] |
| **Ctrl+R** | read `composer.json` and `composer.lock` again |
| **Alt+F10** / **Shift+F10** | local menu: update the package (`composer update name --with-dependencies`), update every package, install, look for newer versions (`composer outdated --direct`), validate `composer.json`, dump the autoloader, open `composer.json`, a new `composer.json`, choose the composer program |

When composer fails, the Composer window comes to the front with its words.

![composer's own words in the Composer window, below the packages](images/composer-log.png)

## Adding a package

**Ins** opens an assistant:

1. **Search Packagist:** type a few letters; divide asks Packagist (`composer search`) once you stop typing. Or type the name, `vendor/package`, as it is.
2. **Packages:** Tab, then move the bar to choose one; its description shows below. Enter (or a double click) adds it.
3. **Version:** divide asks Packagist for the package's versions and suggests a constraint from the newest stable one (`^6.1` for Div 6.1.3). Type your own if you prefer: divide stops suggesting.
4. **Development only:** `require-dev` instead of `require`.

![adding a package: Packagist searched as you type, the version suggested](images/composer-add.png)

**Add** runs `composer require` (with `--dev` for a development package). Div itself is `divengine/div`.

## A new composer.json

A project without `composer.json` gets an assistant (also **Alt+F10 > New composer.json**) that writes it as `composer init` would:

![the assistant of a new composer.json](images/composer-new.png)

| Field | |
|---|---|
| **Name** | `vendor/project`, in lowercase; suggested from the folder |
| **Description**, **License** | MIT by default |
| **PHP version** | `>=8.0` |
| **Div version** | with **Require Div** checked, `divengine/div` is required (`^6.1`) |
| **Class namespace**, **Classes folder** | PSR-4 autoloading of your classes (`Acme\Shop\` in `src/`); the folder is created |
| **Kind** | a project (an application) or a library (a package for others) |
| **Install it now** | runs `composer install` right after |

With Div installed, divide finds the engine by itself in `vendor/` (see [[Installation]]), and the [[Div setup|Div Setup]] can say how to set it up.

## Which composer

divide runs, the first it finds: `$DIVIDE_COMPOSER`, the program chosen with **Alt+F10 > Composer program...**, a `composer.phar` in the project (run with `php`), then `composer` in the PATH. Without composer, the window says how to install it. Searching and versions need the network; listing the packages does not.
