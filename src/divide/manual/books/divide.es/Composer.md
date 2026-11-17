# Composer

**Herramientas > Paquetes Composer...** muestra los paquetes del proyecto y ejecuta [Composer](https://getcomposer.org) para ellos: añadir Div o cualquier paquete de Packagist, quitar, actualizar, instalar, buscar versiones más nuevas. divide nunca edita `composer.json` a espaldas de composer: composer hace cada cambio, bajo el cuadro de progreso, y su salida queda en la ventana **Composer**.

![Herramientas > Paquetes Composer: los paquetes por grupo y vendor, y el que está bajo la barra](images/composer.png)

![añadir un paquete: Packagist consultado, composer require bajo el cuadro de progreso](images/composer.gif)

## La ventana

- **Izquierda: los paquetes, como un árbol.** Primero lo que el proyecto necesita para ejecutarse (**Ejecución**, `require`), lo que necesita solo para desarrollar (**Desarrollo**, `require-dev`) y la **Plataforma** (`php`, extensiones); debajo de cada uno, el vendor (`divengine/`), y luego el paquete por su propio nombre con su versión instalada (de `composer.lock`), todo en orden alfabético. Un paquete que requiere `composer.json` se ve brillante; uno que composer instaló con ellos, tenue, y va bajo el grupo de la sección del lock en que vino. `↑` marca un paquete con una versión más nueva, una vez que las buscaste. **Espacio** pliega un grupo o un vendor (y siguen plegados tras recargar); la línea de filtro encima del árbol deja solo los paquetes cuyo nombre contiene lo que escribes (ver [[El escritorio|The Desktop]]).
- **Derecha: el paquete bajo la barra** (en un grupo o un vendor, lo que contiene). Su descripción, tipo, la versión requerida e instalada, la más nueva, tipo de paquete, licencia, web, fuente, lo que requiere y lo que lo requiere.
- **Debajo del árbol:** el proyecto (su nombre, cuántos paquetes), si está instalado, y cómo terminó la última orden.

| Tecla | |
|---|---|
| **Ins** | añadir un paquete (el asistente de abajo) |
| **Supr** | quitar el paquete (`composer remove`), tras confirmar. Solo los paquetes que requiere el proyecto: una dependencia se va cuando se va lo que la requiere. |
| **Enter** / doble clic | la carpeta del paquete (`vendor/...`) en la [[Ventana de proyecto\|Project Window]]; en un grupo o un vendor, plegarlo o desplegarlo |
| **Espacio** | plegar o desplegar un grupo o un vendor |
| **Ctrl+R** | leer de nuevo `composer.json` y `composer.lock` |
| **Alt+F10** / **Shift+F10** | menú local: actualizar el paquete (`composer update nombre --with-dependencies`), actualizar todos los paquetes, instalar, buscar versiones más nuevas (`composer outdated --direct`), validar `composer.json`, regenerar el autoloader, abrir `composer.json`, un `composer.json` nuevo, elegir el programa composer |

Cuando composer falla, la ventana Composer pasa al frente con sus palabras.

![las propias palabras de composer en la ventana Composer, bajo los paquetes](images/composer-log.png)

## Añadir un paquete

**Ins** abre un asistente:

1. **Buscar en Packagist:** escribe unas letras; divide pregunta a Packagist (`composer search`) cuando dejas de escribir. O escribe el nombre, `vendor/paquete`, tal cual.
2. **Paquetes:** Tab, y mueve la barra para elegir uno; su descripción se ve debajo. Enter (o un doble clic) lo añade.
3. **Versión:** divide pregunta a Packagist las versiones del paquete y sugiere una restricción a partir de la estable más nueva (`^6.1` para Div 6.1.3). Escribe la tuya si lo prefieres: divide deja de sugerir.
4. **Solo desarrollo:** `require-dev` en lugar de `require`.

![añadir un paquete: Packagist consultado mientras escribes, la versión sugerida](images/composer-add.png)

**Añadir** ejecuta `composer require` (con `--dev` para un paquete de desarrollo). Div es `divengine/div`.

## Un composer.json nuevo

Un proyecto sin `composer.json` recibe un asistente (también **Alt+F10 > Nuevo composer.json**) que lo escribe como lo haría `composer init`:

![el asistente de un composer.json nuevo](images/composer-new.png)

| Campo | |
|---|---|
| **Nombre** | `vendor/proyecto`, en minúsculas; sugerido a partir de la carpeta |
| **Descripción**, **Licencia** | MIT por defecto |
| **Versión de PHP** | `>=8.0` |
| **Versión de Div** | con **Requerir Div** marcado, se requiere `divengine/div` (`^6.1`) |
| **Espacio de nombres de las clases**, **Carpeta de las clases** | autoload PSR-4 de tus clases (`Acme\Shop\` en `src/`); la carpeta se crea |
| **Tipo** | un proyecto (una aplicación) o una biblioteca (un paquete para otros) |
| **Instalarlo ahora** | ejecuta `composer install` justo después |

Con Div instalado, divide encuentra el motor solo en `vendor/` (ver [[Instalación|Installation]]), y la [[configuración de Div|Div Setup]] puede decir cómo configurarlo.

## Qué composer

divide ejecuta el primero que encuentra: `$DIVIDE_COMPOSER`, el programa elegido con **Alt+F10 > Programa composer...**, un `composer.phar` en el proyecto (ejecutado con `php`), y después `composer` en el PATH. Sin composer, la ventana dice cómo instalarlo. Buscar y las versiones necesitan la red; listar los paquetes no.
