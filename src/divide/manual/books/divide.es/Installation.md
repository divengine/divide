# Instalación

## Qué necesitas

| | Necesario para |
|---|---|
| **Python 3.11+** | divide en sí |
| **PHP 8** (el comando `php`) | renderizar y verificar includes |
| **Div** (`divengine/div`) | renderizar y verificar includes |
| **Xdebug** (opcional) | el [[depurador\|Debugging PHP]] de PHP |

La edición, el resaltado, el autocompletado y la mayoría de las verificaciones funcionan solo con Python. Todo lo que necesita saber qué haría Div (renderizar, resolver `{% includes %}`) le pregunta al motor real, así que necesita PHP y Div.

## Instalar divide

Desde el repositorio, como comando para tu usuario:

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh
```

`tools/install.sh` crea el `.venv` del checkout si hace falta, instala divide ahí (en modo editable) y enlaza el comando `divide` en `~/.local/bin` (o en la carpeta que le indiques: `tools/install.sh /usr/local/bin`). Después, en cualquier carpeta:

```bash
cd ~/sites/my-project
divide              # the folder is the project
divide page.tpl     # a file: its folder is the project
```

`git pull` en el checkout actualiza el comando. Para quitarlo, borra el enlace.

O como comando aislado con [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/divengine/divide.git
divide --help
```

## Instalar Div para tu proyecto

Lo habitual es Composer, en el proyecto que contiene tus plantillas:

```bash
composer require divengine/div
```

divide encuentra el motor por sí solo, en este orden:

1. la variable de entorno `DIVIDE_DIV_PHP`: un `vendor/autoload.php`, o el `src/div.php` de un checkout de Div (con su `vendor/` instalado);
2. el `engine` de la [[configuración de Div|Div Setup]] del proyecto (`.div/setup.json`), y después de la tuya (`~/.div/setup.json`);
3. la ruta definida en **Opciones > Motor Div…** (guardada en `~/.config/divide/config.json`);
4. un `vendor/autoload.php` con `vendor/divengine/div`, buscando hacia arriba desde la plantilla y desde la carpeta del proyecto.

Si no encuentra ninguno, **Ctrl+F9** en una plantilla explica qué hacer, y las verificaciones de includes simplemente se omiten.

## Arrancarlo

```bash
divide                    # the current folder as the project, project window open
divide ~/sites/shop       # another folder as the project
divide index.tpl card.tpl # open files (their folder becomes the project)
divide ~/sites/shop index.tpl
divide --palette turbo-c  # start with a colour theme: turbo-pascal, turbo-c, free-pascal, modern-dark
divide --colors truecolor # colour depth when the terminal says less than it can: auto, truecolor, 256, 16
divide --language es      # the interface in Spanish for this run: en, es
```

Las dos primeras opciones también están en **Opciones > Colores**, que las recuerda (ver [[El escritorio|The Desktop#colores]]); el idioma está en **Opciones > Idioma** (ver [[El escritorio|The Desktop#idioma]]).

Usa un terminal de al menos 80×25; 120 columnas o más es cómodo para trabajar al lado de la salida.

Siguiente: [[Primeros pasos|Getting Started]].
