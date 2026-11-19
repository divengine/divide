# Instalación

## Qué necesitas

| | Necesario para |
|---|---|
| **PHP 8** (el comando `php`) | renderizar y verificar includes |
| **Div** (`divengine/div`) | renderizar y verificar includes |
| **Xdebug** (opcional) | el [[depurador\|Debugging PHP]] de PHP |
| **Python 3.11+** | solo para instalar divide desde su código fuente |

La edición, el resaltado, el autocompletado y la mayoría de las verificaciones funcionan sin PHP. Todo lo que necesita saber qué haría Div (renderizar, resolver `{% includes %}`) le pregunta al motor real, así que necesita PHP y Div.

## Instalar divide

Cada [release](https://github.com/divengine/divide/releases/latest) trae divide listo para usar, con Python dentro: no hay nada más que instalar. Elige la vía que convenga a tu sistema.

### macOS y Linux: Homebrew

```bash
brew install divengine/tap/divide
```

`brew upgrade divide` lo actualiza.

### Windows: Scoop

```powershell
scoop install https://github.com/divengine/divide/releases/latest/download/divide.json
```

`scoop update divide` lo actualiza. O descarga de la release `divide-<versión>-windows-x86_64.msi`: el instalador pone divide en Archivos de programa y en el PATH (abre una terminal nueva después). El `.zip` trae solo `divide.exe`, para ponerlo donde quieras.

### Paquetes de Linux

De la release, para tu arquitectura (`amd64`/`x86_64` o `arm64`/`aarch64`):

| Sistema | Paquete | Instalar |
|---|---|---|
| Debian, Ubuntu | `divide_<versión>_amd64.deb` | `sudo apt install ./divide_<versión>_amd64.deb` |
| Fedora, RHEL, openSUSE | `divide-<versión>-1.x86_64.rpm` | `sudo dnf install ./divide-<versión>-1.x86_64.rpm` |
| Alpine | `divide_<versión>_x86_64.apk` | `sudo apk add --allow-untrusted divide_<versión>_x86_64.apk` |
| Arch | `divide-<versión>-1-x86_64.pkg.tar.zst` | `sudo pacman -U divide-<versión>-1-x86_64.pkg.tar.zst` |

Los paquetes ponen `divide` en `/usr/bin` y recomiendan `php-cli`.

### Linux: AppImage o el binario solo

```bash
chmod +x divide-<versión>-linux-x86_64.AppImage
./divide-<versión>-linux-x86_64.AppImage
```

O el binario independiente, en una carpeta de tu PATH:

```bash
curl -fLo ~/.local/bin/divide https://github.com/divengine/divide/releases/download/v<versión>/divide-<versión>-linux-x86_64
chmod +x ~/.local/bin/divide
```

### macOS: el archivo comprimido

`divide-<versión>-macos-arm64.tar.gz` (Apple silicon) o `-macos-x86_64.tar.gz` (Intel) trae el binario. No está firmado, así que macOS lo detiene la primera vez; permítelo con:

```bash
xattr -d com.apple.quarantine divide
```

(Con Homebrew no hace falta.) En Windows, SmartScreen pregunta lo mismo antes de la primera ejecución del `.exe` o del `.msi`: **Más información > Ejecutar de todas formas**.

Cada release tiene un archivo `SHA256SUMS` para comprobar lo que descargaste.

### Desde el código fuente

Con Python 3.11 o posterior, como comando para tu usuario:

```bash
git clone https://github.com/divengine/divide.git
cd divide
tools/install.sh
```

`tools/install.sh` crea el `.venv` del checkout si hace falta, instala divide ahí (en modo editable) y enlaza el comando `divide` en `~/.local/bin` (o en la carpeta que le indiques: `tools/install.sh /usr/local/bin`). `git pull` en el checkout actualiza el comando. Para quitarlo, borra el enlace.

O como comando aislado con [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/divengine/divide.git
```

### Comprobarlo

```bash
divide --version
cd ~/sites/my-project
divide .            # esta carpeta es el proyecto
divide page.tpl     # un archivo solo, sin carpeta
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
divide                    # nada abierto: la ventana de bienvenida (carpetas y archivos recientes)
divide .                  # la carpeta actual como proyecto, con la ventana del proyecto
divide ~/sites/shop       # otra carpeta como proyecto
divide index.tpl card.tpl # archivos solos, sin carpeta
divide ~/sites/shop index.tpl
divide --palette turbo-c  # empezar con un tema de colores: turbo-pascal, turbo-c, free-pascal, modern-dark
divide --colors truecolor # profundidad de color cuando el terminal dice menos de lo que puede: auto, truecolor, 256, 16
divide --language es      # la interfaz en español para esta ejecución: en, es
```

Las dos primeras opciones también están en **Opciones > Colores**, que las recuerda (ver [[El escritorio|The Desktop#colores]]); el idioma está en **Opciones > Idioma** (ver [[El escritorio|The Desktop#idioma]]).

Una carpeta se abre solo cuando la indicas, como en VS Code; **Archivo > Abrir carpeta** abre una después (ver [[El escritorio|The Desktop#una-carpeta-un-archivo-o-nada]]).

Usa un terminal de al menos 80×25; 120 columnas o más es cómodo para trabajar al lado de la salida.

Siguiente: [[Primeros pasos|Getting Started]].
