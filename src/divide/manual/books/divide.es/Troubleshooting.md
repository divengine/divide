# Solución de problemas

**Ctrl+F9 en una plantilla dice "Div was not found".**
Instala Div en el proyecto (`composer require divengine/div`), o indícale a divide dónde está con **Opciones > Motor Div…** o `DIVIDE_DIV_PHP`. Consulta [[Instalación|Installation]].

**No hay avisos sobre los includes, ni siquiera de uno que falta.**
Los includes los verifica el propio Div, así que necesitan `php` y Div. Comprueba que renderizar (Ctrl+F9) funciona. Una plantilla sin título no se verifica en cuanto a includes hasta que se guarda (consulta *Primero guardar* en [[Verificación de plantillas|Checking Templates]]).

**Se informa de un include pero Div lo encuentra al renderizar.**
Div también busca relativo a las plantillas incluidas antes. divide le da a Div la última plantilla que renderizaste como ese historial: renderiza desde la plantilla principal (la que incluye esta) y verifica de nuevo.

**Ctrl+Enter no hace nada.**
Algunos terminales no envían Ctrl+Enter en absoluto. Usa **Ctrl+J**, Ctrl+clic o Buscar > Ir a la plantilla incluida.

**Ctrl+Space no hace nada.**
Algunos terminales o entornos de escritorio se quedan Ctrl+Space para sí (cambio de método de entrada). Usa Editar > Completar, o libera el atajo en la configuración de tu sistema.

**Alt+letra no abre los menús.**
Puede que tu terminal envíe Alt como Meta de otra forma, o que el gestor de ventanas lo capture. **F10** siempre abre la barra de menús.

**Los colores se ven mal, o planos.**
divide muestra los colores con tanta profundidad como el terminal dice que admite. Por ssh o dentro de tmux `COLORTERM` se pierde a menudo, y un terminal de color real parece uno de 256 colores: elige **Color real** en **Opciones > Colores** (desde el próximo inicio) o arranca con `divide --colors truecolor`; para tmux, dile también que el terminal exterior tiene color real (`set -as terminal-features ",xterm-256color:RGB"`). En un terminal de 16 colores elige **16 colores**. Los temas también están en **Opciones > Colores**.

**Las `$references` de mis datos salen vacías.**
Es cosa de Div: un archivo de datos se decodifica antes de que exista ninguna variable. Úsalas en JSON dentro de las plantillas (`{= x: {"a": $b} =}`). divide añade una nota cuando renderiza datos que usan referencias.

**El dialector marca con `≈` una sección que parece correcta.**
Div tradujo el ejemplo de vuelta y obtuvo otra cosa. El veredicto muestra la línea que escribiste y lo que leyó Div. Si la diferencia está en una etiqueta que no cambiaste (por ejemplo un `{%% path:data %%}` que pierde su `:`), la causa es el traductor de Div, no tu dialecto. Consulta [[Traducir plantillas|Translating Templates]].

**El depurador dice que necesita Xdebug, o "PHP ended before Xdebug connected".**
`php -m` debe listar Xdebug, o **Opciones > Xdebug…** debe indicar un `xdebug.so` compilado para tu versión de PHP (`php -v`). El mensaje muestra lo que PHP imprimió cuando no pudo cargarlo. Consulta [[Depurar PHP|Debugging PHP]].

**Un script espera para siempre con Ctrl+F9.**
No está esperando al teclado (su entrada está cerrada): está ocupado, o esperando a la red. **Esc** lo detiene. Los scripts interactivos van en **Ejecutar > Ejecutar en terminal**.

**El servidor web no arranca.**
La caja muestra lo que dijo `php -S`. `Address already in use`: otro programa (u otro divide) sirve ese puerto; elige otro puerto en **Ejecutar > Servidor web**. Consulta [[Servidor web|Web Server]].

**Una página no termina de cargar nunca.**
Hay una petición pausada en el depurador (la línea de estado dice `Paused at …`): Ctrl+F9 deja que siga, Ctrl+F2 la termina. Mientras una petición está pausada las demás esperan, porque `php -S` atiende de una en una.

**He encontrado un error.**
Abre una incidencia en [divengine/divide](https://github.com/divengine/divide/issues), con la plantilla si puedes.
