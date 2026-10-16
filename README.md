# time_line

Digitalización de los registros de presión uretral (canal **Pura**, cm H2O) del
sistema urodinámico Goby (Laborie) a partir de capturas de pantalla, para la
tesis *Análisis mediante inteligencia artificial del comportamiento uretral
durante el estado basal y después de la aplicación de CGRP en la coneja*
(ver `Escrito/`).

## Estructura

```
time_line/
├── Escrito/                     tesis (docx, pdf)
├── scripts/
│   ├── extraer_pura.py          digitaliza una captura (única copia del script)
│   ├── procesar_sesiones.py     procesa todo el manifiesto y une las sesiones
│   └── generar_web.py           arma la base de datos del sitio (web/datos.js)
├── index.html                   redirección a web/ para GitHub Pages
├── web/                         sitio para consultar los resultados
│   ├── index.html               se abre con doble clic, sin servidor
│   ├── estilos.css
│   ├── app.js
│   └── datos.js                 generado; no editar a mano
├── create/
│   ├── manifiesto.csv           capturas, orden, rótulo de tiempo y valores en pantalla
│   ├── resumen_capturas.csv     calibración y validación de cada captura
│   ├── resumen_solapamientos.csv concordancia entre capturas consecutivas
│   └── H638UP_<Condición>/      Basal → Proximal → Medial → Distal (orden cronológico)
│       ├── pura_H638UP_<Condición>.csv   serie unida de la sesión (paso 0.1 s)
│       ├── sesion_H638UP_<Condición>.png capturas superpuestas y serie unida
│       └── a_NN/origin/
│           ├── a_NN.png                  captura completa de la pantalla
│           ├── a_NN_b.png                recorte de trabajo (regla, Vol. infundido, Pura)
│           ├── pura_a_NN_b.csv           serie digitalizada
│           ├── verificacion_a_NN_b.png   superposición y curva reconstruida
│           └── calibracion_a_NN_b.json   parámetros de calibración y validación
├── piloto/                      prueba inicial (versión antigua del script, no usar)
└── environment.yml
```

La numeración `a_NN` es la secuencia global de capturas del sujeto:
Basal `a_00–a_02`, Proximal `a_03–a_06`, Medial `a_07–a_10`, Distal `a_11–a_15`.

## Uso

```bash
conda env create -f environment.yml      # una sola vez
conda activate analisis_presion
python scripts/procesar_sesiones.py      # regenera todos los resultados
python3 scripts/generar_web.py           # actualiza el sitio con esos resultados
```

`generar_web.py` sólo usa la biblioteca estándar, así que puede ejecutarse sin
activar el entorno.

Una sola captura:

```bash
python scripts/extraer_pura.py create/H638UP_Medial/a_10/origin/a_10_b.png \
    -o pura.csv --plot verificacion.png --t-ref 450 --pura-pantalla 0
```

Para agregar un sujeto o captura: colocar el recorte `a_NN_b.png` y añadir una
fila al manifiesto con el rótulo de la **primera marca mayor visible** de la
regla (la que queda marcada en el PNG de verificación) en `rotulo_ref` y su
valor en segundos en `t_ref_s`, y el valor de Pura que muestra el equipo en
`pura_pantalla`.

## Sitio de resultados

`web/index.html` reúne todo lo que hay en `create/` en una sola página; se abre
con doble clic (no necesita servidor ni conexión) y tiene cinco secciones:

* **Resumen** — totales del sujeto, una tarjeta por sesión con la serie completa
  en miniatura y una tabla comparativa entre condiciones (media, mediana, DE,
  máximo y su instante, integral, porcentaje de muestras censuradas).
* **Curvas** — las cuatro series unidas superpuestas, con acercamiento con la
  rueda, desplazamiento arrastrando, valores al pasar el ratón, envolvente
  mín–máx, censura, límites de cada captura y cursores del equipo. El rango que
  se está viendo se descarga como CSV.
* **Capturas** — una fila por captura, con búsqueda, filtro por condición y
  orden por cualquier columna; al pulsar una fila se abren sus tres imágenes y
  toda su calibración, y se puede saltar a ese tramo en la gráfica.
* **Validación** — reconstruido frente a pantalla, concordancia entre capturas
  consecutivas y calibración de cada captura.
* **Guía** — diccionario de columnas y significado de cada estado.

El sitio no tiene nada escrito a mano: sale de `create/manifiesto.csv`, de los
dos resúmenes y de las series unidas, de modo que al agregar un sujeto o una
captura basta con volver a correr `generar_web.py`.

Si el navegador bloquea las imágenes al abrir el archivo directamente, se puede
servir la carpeta del proyecto:

```bash
python3 -m http.server 8000     # y abrir http://localhost:8000/web/
```

El sitio también está publicado con GitHub Pages desde la raíz de `main`:

**<https://said-tj.github.io/time_line/>**

La raíz tiene que ser la carpeta publicada porque `web/` lee las imágenes y los
CSV de `create/`; `index.html` de la raíz sólo redirige a `web/` y `.nojekyll`
evita que GitHub procese el repositorio con Jekyll. Cada `git push` a `main`
vuelve a publicar la página, así que después de reprocesar hay que acordarse de
correr `generar_web.py` y subir `web/datos.js`.

## Columnas de los CSV

| columna | descripción |
|---|---|
| `t_s` | tiempo del registro del equipo (s); `m:ss` en la regla |
| `pura_cmH2O` | centroide del trazo en la columna |
| `pura_min_cmH2O`, `pura_max_cmH2O` | envolvente del trazo (tramos verticales) |
| `censura` | `0` válida · `-1` piso (≤ ~5 cm H2O, incluye valores negativos) · `1` techo (≥ ~294, saturado en 300) |
| `x_px`, `y_px` | posición en la imagen (sólo en las capturas) |
| `n_capturas` | capturas promediadas en ese instante (sólo en la serie unida) |

## Calibración y validación

* Escala vertical: bordes del panel Pura (0 y 300 cm H2O), ≈ 2.97–3.00 cm H2O/px
  en los recortes `_b` (≈ 1 px de resolución = 3 cm H2O).
* Escala temporal: regla con marca menor de 1 s y mayor de 5 s,
  6.600 px/s (Basal, Proximal) y 6.620 px/s (Medial, Distal); error del
  ajuste ≤ 0.3 px en todas las capturas.
* El tiempo calculado para cada marca mayor se dibuja en azul bajo la regla en
  el PNG de verificación: debe coincidir con el rótulo impreso por el equipo.
* `resumen_capturas.csv` compara el valor final reconstruido con el que muestra
  el equipo; `resumen_solapamientos.csv` compara capturas consecutivas en su
  intervalo común (diferencia RMS ≤ 1.3 cm H2O y desfase 0.0 s en todos los
  pares del sujeto H638UP).
