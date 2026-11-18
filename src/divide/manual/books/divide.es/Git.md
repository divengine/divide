# Git

Cuando el proyecto es un repositorio git, divide muestra lo que cambió y deja trabajar con ello: preparar, hacer commit, ver el historial, cambiar de rama, fusionar, guardar cambios aparte (stash), hacer pull y push, y ver las pull requests e issues de GitHub o Gitea. Usa el `git` instalado en el sistema, con tu configuración y tus credenciales. Sin git, o fuera de un repositorio, el menú **Git** dice por qué.

![Git: las marcas, los cambios y su diff, un commit, el historial, las ramas](images/git.gif)

## Lo que cambió, de un vistazo

divide lee el estado del repositorio cada pocos segundos, después de guardar y después de cada comando git, así que lo que ves sigue también al trabajo hecho en una terminal.

![la ventana del proyecto y el margen del editor con los cambios](images/git-marks.png)

- La **ventana del proyecto** pone una letra tras cada archivo cambiado: `M` modificado, `A` añadido, `D` borrado, `R` renombrado, `?` nuevo (sin seguimiento), `U` un conflicto. Una carpeta con cambios muestra `•`; los archivos y carpetas ignorados se ven atenuados. Su borde inferior muestra la rama y cuántos archivos cambiaron.
- El **margen del editor** colorea los números de línea respecto al último commit: amarillo una línea cambiada, verde una añadida, rojo donde se borraron líneas. Sigue a la edición mientras escribes, antes de guardar.

## El menú Git

![el menú Git](images/git-menu.png)

| Opción | Qué hace |
|---|---|
| **Cambios** | los archivos que cambiaron y su diff: preparar, descartar, hacer commit |
| **Historial** | los commits de todas las ramas, con el grafo |
| **Ramas** | las ramas locales y remotas, y los stashes |
| **Commit...** | hacer commit de lo preparado |
| **Pull**, **Push**, **Fetch** | con la rama upstream (el primer push la fija); lo que dice git, en una caja de progreso |
| **Diff del archivo** | el archivo activo frente al último commit |
| **Historial del archivo** | los commits que tocaron el archivo activo (siguiendo sus renombres) |
| **Autoría (blame)** | quién escribió cada línea del archivo activo, y en qué commit |
| **Pull requests e issues** | la forja del proyecto: GitHub o Gitea |

## Git > Cambios

![Git > Cambios: las áreas y un diff unificado](images/git-changes.png)

A la izquierda, los archivos por área: **Conflictos** (durante una fusión), **Preparados (el próximo commit)**, **Cambios** y **Sin seguimiento**. A la derecha, el diff del archivo bajo la barra; debajo, la rama, su upstream (por delante, por detrás) y los totales.

| Tecla | Acción |
|---|---|
| **Espacio** | preparar el archivo, o quitarlo de lo preparado |
| **Enter** | abrir el archivo |
| **Supr** | descartar sus cambios (pregunta antes; un archivo sin seguimiento se borra) |
| **Ctrl+K** | hacer commit |
| **Tab** | al diff y de vuelta |
| **Alt+F10** | preparar o quitar todo, enmendar el último commit, guardar los cambios aparte, cancelar una fusión, pull, push, fetch |

## El diff

El diff muestra el código, no la salida de git: las líneas quitadas sobre rojo, las añadidas sobre verde, el resto con el color de la ventana, con los números de línea viejo y nuevo y los colores de la plantilla o del lenguaje. Dentro de una línea cambiada, las palabras que cambiaron se ven más brillantes.

**S** lo muestra lado a lado: el archivo viejo a la izquierda y el nuevo a la derecha, las líneas emparejadas, una trama donde un lado no tiene nada. **S** otra vez vuelve al unificado. divide recuerda la elección.

![el mismo diff lado a lado](images/git-diff-split.png)

| Tecla | Acción |
|---|---|
| **↑ ↓ RePág AvPág Inicio Fin** | moverse |
| **← →** | desplazar una línea larga |
| **N** / **P** | el cambio siguiente / anterior |
| **S** | lado a lado o unificado |
| **Enter** | abrir el archivo en esa línea |

El mismo diff se abre desde el historial (un commit), desde **Git > Diff del archivo** y desde la autoría.

## Commit

**Ctrl+K** (o **Git > Commit...**) pide el mensaje: su primera línea es el resumen, luego una línea en blanco y los detalles. **Ctrl+Enter** hace el commit; **Enter** empieza una línea nueva. Dos casillas: **Enmendar el último commit** (lo reemplaza, con su mensaje para editar) y **Preparar todos los cambios antes**. La respuesta de git queda en la ventana Git.

![el diálogo de commit](images/git-commit.png)

## Git > Historial

![Git > Historial: el grafo y los detalles de un commit](images/git-history.png)

Todas las ramas, de la más nueva a la más vieja, con el grafo de git, las ramas y etiquetas de cada commit, su autor y fecha; debajo, el commit bajo la barra: hash, autor, padres, mensaje y archivos. **Enter** abre su diff. **Alt+F10**: una rama nueva en ese commit, copiar el hash. **Historial del archivo** muestra lo mismo para un archivo.

## Git > Ramas

![Git > Ramas: las ramas locales y un stash](images/git-branches.png)

Las ramas locales (`*` la actual), las de cada remoto y los stashes; al lado, el último commit de la rama.

| Tecla | Acción |
|---|---|
| **Enter** | cambiar a la rama (una remota recibe su rama local); en un stash, recuperarlo y borrarlo |
| **Ins** | una rama nueva desde la que está bajo la barra |
| **Supr** | borrar la rama (pregunta; si no está fusionada, pregunta otra vez), o borrar el stash |
| **Alt+F10** | fusionar en la rama actual, aplicar un stash manteniéndolo, pull, push, fetch |

Un stash se hace desde **Git > Cambios** (Alt+F10 > Guardar los cambios aparte (stash)...).

## Fusiones y conflictos

**Fusionar en la rama actual** ejecuta `git merge`. Cuando git no puede fusionar un archivo por sí solo, este pasa a **Conflictos** y la ventana de cambios lo dice; el diff muestra el archivo con las marcas de git, nuestro lado y el suyo. Edita el archivo, **Espacio** lo marca resuelto y **Ctrl+K** hace el commit de la fusión (su mensaje ya está listo). **Alt+F10 > Cancelar la fusión** vuelve a como estaba antes.

## Autoría (blame)

**Git > Autoría (blame)** muestra cada línea del archivo activo con el commit, la fecha y el autor que la cambió por última vez; las líneas aún sin commit lo dicen. La línea de estado muestra el asunto del commit; **Enter** abre el diff de ese commit.

![la autoría de index.tpl](images/git-blame.png)

## Pull requests e issues

**Git > Pull requests e issues** las lee de la forja del remoto `origin`, con su herramienta de línea de comandos, con tu sesión:

- **GitHub**: [gh](https://cli.github.com), después de `gh auth login`;
- **Gitea**, Forgejo, Codeberg: [tea](https://gitea.com/gitea/tea), después de `tea login add`.

Si falta la herramienta, o el remoto no es ninguno de ellos, la ventana dice qué hacer.

![las pull requests e issues abiertas](images/git-forge.png)

| Tecla | Acción |
|---|---|
| **Enter** | abrirla en el navegador |
| **Ins** | una pull request nueva desde la rama actual (antes hace push); en las issues, una issue nueva |
| **Alt+F10** | copiar la dirección; en una pull request: traer su rama, fusionarla, fusionarla en un commit (squash), fusionarla con rebase |
| **Ctrl+R** | leerlas de nuevo |

Ver la [[Referencia de teclado|Keyboard Reference#ventanas-git]].
