#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STJ
"""
Digitalización de la curva roja (canal «Pura», cm H2O) de un trazo urodinámico
Goby (Laborie) exportado como imagen.

El procedimiento consta de cuatro etapas:

  1. Geometría: se localizan los bordes horizontales de los paneles y la
     línea vertical que separa el área del trazo de la zona de rótulos
     (valores numéricos, triángulo marcador). Las columnas a la derecha de
     esa línea se excluyen; de lo contrario los rótulos rojos «Pura»,
     «0», «132 ^» se confunden con la curva.
  2. Calibración vertical: el panel de presión es el que contiene más píxeles
     rojos entre dos bordes consecutivos. Su borde superior corresponde a
     P_TOP y el inferior a P_BOT (rótulos 300 y 0); la conversión es afín.
  3. Calibración horizontal: se localizan las marcas de la regla temporal
     (1 s por marca menor, marca mayor cada 5 s) y se ajusta por mínimos
     cuadrados x(n) = s*n + x0. Si se indica el valor de la primera marca
     mayor rotulada (--t-ref), el tiempo es el del registro del equipo; de lo
     contrario t = 0 en esa marca.
  4. Extracción: para cada columna se calcula el centroide ponderado por
     «rojez», lo que otorga resolución subpíxel; además se registran los
     extremos superior e inferior (envolvente de los tramos verticales) y si
     la muestra está censurada (trazo en el techo o en el piso del panel).

Uso:
    python3 extraer_pura.py imagen.png -o salida.csv --plot verificacion.png \
        [--t-ref 450] [--pura-pantalla 0] [--reporte calibracion.json]

Notas sobre la versión anterior (piloto/extraer_pura.py):
  * Los bordes entre paneles son grises (~145–160), no negros; con el umbral
    de 140 el borde Vol. Infundido/Pura no se detectaba y el «panel de
    presión» abarcaba dos paneles, lo que reducía la escala a la mitad
    (1.49 en lugar de 2.97 cm H2O/px).
  * El límite derecho se buscaba con el mismo umbral y casi nunca se
    encontraba, de modo que los rótulos se digitalizaban como señal (la
    curva «se pasaba»); en otras capturas se tomaba una línea interior y la
    curva se cortaba antes de tiempo.
  * Las marcas menores de la regla dibujadas con antialiasing son grises
    claras; al perderse, el paso estimado se duplicaba (≈10.8 en lugar de
    ≈6.6 px/s).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# Parámetros por omisión (modificables por línea de comandos)
# --------------------------------------------------------------------------
P_TOP_DEFAULT = 300.0       # cm H2O en el borde superior del panel de presión
P_BOT_DEFAULT = 0.0         # cm H2O en el borde inferior del panel de presión
TICK_SECONDS_DEFAULT = 1.0  # segundos entre marcas menores de la regla
MAYOR_CADA = 5              # marcas menores por cada marca mayor rotulada

# La línea de Pura mide ~2 px; cuando el valor es ≤ 0 el equipo la dibuja
# recortada contra el borde inferior, con el centroide a ~1.7 px del borde.
# Por debajo de este margen el valor real no es recuperable (piso).
MARGEN_PISO_PX = 2.0
MARGEN_TECHO_PX = 2.0


# --------------------------------------------------------------------------
# Utilidades de detección
# --------------------------------------------------------------------------
def cargar(ruta: str) -> np.ndarray:
    """Devuelve la imagen como arreglo entero de forma (alto, ancho, 3)."""
    return np.array(Image.open(ruta).convert("RGB")).astype(int)


def mascara_gris(img: np.ndarray, vmax: int = 200, tol: int = 30) -> np.ndarray:
    """
    Píxeles neutros (R ≈ G ≈ B) más oscuros que el fondo.

    Detecta tanto las líneas negras como las grises claras producto del
    antialiasing, y excluye los trazos de color y los fondos blanco y verde.
    """
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    neutro = (np.abs(r - g) < tol) & (np.abs(g - b) < tol)
    return neutro & (np.maximum(np.maximum(r, g), b) < vmax)


def mascara_roja(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Devuelve (máscara booleana, peso de rojez).

    Se considera rojo todo píxel cuyo canal R domine claramente sobre G y B.
    El peso, proporcional a R - max(G, B), permite un centroide subpíxel que
    aprovecha el antialiasing del trazo.
    """
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    dominancia = r - np.maximum(g, b)
    mask = (r > 120) & (dominancia > 40)
    peso = np.where(mask, dominancia, 0).astype(float)
    return mask, peso


def _agrupar(idx) -> list[list[int]]:
    """Agrupa índices enteros contiguos."""
    grupos: list[list[int]] = []
    for i in idx:
        if grupos and i - grupos[-1][-1] <= 1:
            grupos[-1].append(int(i))
        else:
            grupos.append([int(i)])
    return grupos


def bordes_horizontales(img: np.ndarray, frac: float = 0.85) -> list[int]:
    """Filas que constituyen bordes de panel (línea gris casi completa)."""
    gris = mascara_gris(img)
    ancho = img.shape[1]
    # se evalúa la parte izquierda para no depender de la zona de rótulos
    cobertura = gris[:, 5:int(ancho * 0.8)].mean(1)
    filas = np.where(cobertura > frac)[0]
    return [int(round(np.mean(g))) for g in _agrupar(filas)]


def limite_derecho(img: np.ndarray, y0: int, y1: int) -> int:
    """
    Primera columna de la línea vertical que separa el trazo de la zona de
    rótulos. Se busca en el 15 % derecho de la imagen la última columna cuya
    luminancia mediana entre y0 e y1 sea propia de una línea; los cursores
    punteados y las bandas sombreadas no alteran la mediana.
    """
    ancho = img.shape[1]
    lum = np.median(img[y0 + 2:y1 - 1].mean(2), axis=0)
    cand = [x for x in range(int(ancho * 0.85), ancho - 15) if lum[x] < 215]
    if not cand:
        raise RuntimeError("No se detectó la línea que separa el trazo de los rótulos.")
    return _agrupar(cand)[-1][0]


def panel_presion(img: np.ndarray, bordes: list[int], x_sep: int) -> tuple[int, int]:
    """(y_top, y_bot) del panel con la mayor cantidad de píxeles rojos."""
    rojo = mascara_roja(img)[0][:, :x_sep]
    mejor, conteo_max = None, -1
    for y0, y1 in zip(bordes[:-1], bordes[1:]):
        if y1 - y0 < 40:
            continue
        c = int(rojo[y0 + 1:y1].sum())
        if c > conteo_max:
            conteo_max, mejor = c, (y0, y1)
    if mejor is None:
        raise RuntimeError("No se identificó el panel de presión.")
    return mejor


# --------------------------------------------------------------------------
# Regla temporal
# --------------------------------------------------------------------------
def marcas_regla(img: np.ndarray, y_regla: int, x_sep: int):
    """
    Posiciones subpíxel de las marcas de la regla (sobre la línea y_regla) y
    bandera de marca mayor. Las marcas menores ocupan las ~3 filas inmediatas
    a la línea; las mayores se prolongan hacia arriba.
    """
    gris = mascara_gris(img)
    oscuridad = 255.0 - img.mean(2)
    menor = gris[y_regla - 3:y_regla].sum(0) >= 2
    alta = gris[y_regla - 7:y_regla - 4].sum(0) >= 2
    xs, mayores = [], []
    for g in _agrupar(np.where(menor)[0]):
        if g[0] < 4 or g[-1] >= x_sep - 1:
            continue                       # marco izquierdo y separador
        cols = np.array(g)
        w = oscuridad[y_regla - 3:y_regla, cols].sum(0)
        xs.append(float((cols * w).sum() / w.sum()))
        mayores.append(bool(alta[cols].any()))
    return np.array(xs), np.array(mayores)


def calibrar_tiempo(xs: np.ndarray, mayores: np.ndarray, tick_seg: float):
    """
    Ajusta x(n) = s*n + x0 a las marcas en dos pasos:

      1. Sólo con marcas «limpias», cuyas separaciones con ambas vecinas son
         múltiplos enteros del paso. Las líneas verticales de los cursores
         que cruzan la regla generan marcas espurias a media separación; si
         se incluyeran, la asignación incremental de índices se desfasaría.
         Los índices se asignan acumulando separaciones, lo que evita la
         deriva que produciría redondear (x - x0)/paso con un paso sesgado.
      2. Con la escala ya precisa, cada marca recibe el índice de la rejilla
         más cercana; se descartan las que distan más de 1 px y se reajusta.

    Devuelve un diccionario con la escala (px/s), el error cuadrático medio
    del ajuste (px), las marcas descartadas y la coherencia de las mayores.
    """
    if len(xs) < 10:
        raise RuntimeError("No se detectó la regla temporal.")
    s = float(np.median(np.diff(xs)))

    def es_multiplo(d):
        k = np.round(d / s)
        return (k >= 1) & (np.abs(d / s - k) < 0.2)

    sep = np.diff(xs)
    ok = es_multiplo(sep)
    limpia = np.concatenate([[ok[0]], ok[:-1] & ok[1:], [ok[-1]]])
    xl = xs[limpia]
    for _ in range(10):
        n = np.concatenate([[0.0], np.cumsum(np.maximum(np.round(np.diff(xl) / s), 1))])
        A = np.vstack([n, np.ones(len(n))]).T
        (s_new, x0), *_ = np.linalg.lstsq(A, xl, rcond=None)
        if abs(s_new - s) < 1e-9:
            break
        s = float(s_new)

    usar = np.ones(len(xs), bool)
    for _ in range(3):
        n = np.round((xs - x0) / s)
        resid = xs - (s * n + x0)
        usar = np.abs(resid) <= 1.0
        A = np.vstack([n[usar], np.ones(usar.sum())]).T
        (s, x0), *_ = np.linalg.lstsq(A, xs[usar], rcond=None)
    n = np.round((xs - x0) / s)
    resid = (xs - (s * n + x0))[usar]
    # las marcas mayores deben repetirse cada MAYOR_CADA índices
    n_may = n[mayores & usar].astype(int)
    if len(n_may):
        fase = int(np.bincount(n_may % MAYOR_CADA).argmax())
        coherencia = float(np.mean(n_may % MAYOR_CADA == fase))
    else:
        fase, coherencia = 0, 0.0
    return {
        "px_por_seg": float(s / tick_seg), "paso_px": float(s), "x0": float(x0),
        "descartadas": int((~usar).sum()),
        "rms_px": float(np.sqrt(np.mean(resid ** 2))),
        "res_max_px": float(np.abs(resid).max()),
        "fase_mayor": fase, "coherencia_mayores": coherencia,
    }


def marca_referencia(cal: dict, xs: np.ndarray, margen: float = 15.0) -> float:
    """
    Columna (según el ajuste) de la primera marca mayor cuyo rótulo es
    completamente visible, es decir, separada al menos `margen` px del borde
    izquierdo. Es la marca a la que se asigna el valor --t-ref.
    """
    s, x0 = cal["paso_px"], cal["x0"]
    n_ini = int(np.floor((max(xs[0], margen) - x0) / s))
    n = n_ini
    while (n % MAYOR_CADA) != cal["fase_mayor"] or s * n + x0 < margen:
        n += 1
    return float(s * n + x0)


# --------------------------------------------------------------------------
# Extracción
# --------------------------------------------------------------------------
def extraer(img: np.ndarray, y_top: int, y_bot: int,
            p_top: float, p_bot: float, px_por_seg: float, x_ref: float,
            t_ref: float, x_ini: int, x_fin: int):
    """
    Recorre las columnas [x_ini, x_fin) del panel y devuelve un arreglo con
    tiempo, presión (centroide), envolvente mínima/máxima, censura (-1 piso,
    +1 techo, 0 válida), columna y fila del centroide.
    """
    mask, peso = mascara_roja(img)
    # se incluyen las filas de los bordes: cuando la presión satura, el
    # trazo se dibuja sobre el propio borde
    interior = slice(y_top, y_bot + 1)
    ys = np.arange(img.shape[0])[interior]

    def a_presion(y):
        return p_bot + (y_bot - y) * (p_top - p_bot) / (y_bot - y_top)

    filas = []
    for x in range(x_ini, x_fin):
        col_m = mask[interior, x]
        if not col_m.any():
            continue
        col_w = peso[interior, x]
        y_c = float((ys * col_w).sum() / col_w.sum())
        y_hi = float(ys[col_m].min())   # píxel superior  -> presión máxima
        y_lo = float(ys[col_m].max())   # píxel inferior  -> presión mínima
        if y_hi <= y_top + MARGEN_TECHO_PX:
            censura = 1
        elif y_c >= y_bot - MARGEN_PISO_PX:
            censura = -1
        else:
            censura = 0
        filas.append((
            t_ref + (x - x_ref) / px_por_seg,
            a_presion(y_c),
            a_presion(y_lo),
            a_presion(y_hi),
            censura,
            x, y_c,
        ))
    return np.array(filas, dtype=float)


def remuestrear(datos: np.ndarray, dt: float) -> np.ndarray:
    """Interpolación lineal de la señal a paso temporal constante dt."""
    t = datos[:, 0]
    nuevo_t = np.arange(t[0], t[-1] + 1e-9, dt)
    cols = [nuevo_t]
    for k in (1, 2, 3):
        cols.append(np.interp(nuevo_t, t, datos[:, k]))
    # la censura se toma de la muestra original más cercana
    idx = np.clip(np.searchsorted(t, nuevo_t), 0, len(t) - 1)
    cols.append(datos[idx, 4])
    return np.column_stack(cols)


ENCABEZADO = ["t_s", "pura_cmH2O", "pura_min_cmH2O", "pura_max_cmH2O",
              "censura", "x_px", "y_px"]


def guardar_csv(ruta: str, datos: np.ndarray) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ENCABEZADO[:datos.shape[1]])
        for fila in datos:
            w.writerow([f"{fila[0]:.4f}", f"{fila[1]:.2f}",
                        f"{fila[2]:.2f}", f"{fila[3]:.2f}", f"{int(fila[4])}"]
                       + [f"{v:.2f}" for v in fila[5:]])


def leer_csv(ruta: str) -> np.ndarray:
    return np.loadtxt(ruta, delimiter=",", skiprows=1, ndmin=2)


def marcas_verticales(img: np.ndarray, y_top: int, y_bot: int, x_fin: int,
                      a_tiempo):
    """
    Devuelve (cursores, bandas): instantes de las líneas verticales punteadas
    azules (marcas de evento) y extremos temporales de las regiones
    sombreadas en verde, en segundos.
    """
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    azul = (b > 150) & (b - np.maximum(r, g) > 40)
    conteo = azul[y_top + 3:y_bot - 1, :x_fin].sum(0)
    cursores = [a_tiempo(np.mean(gr))
                for gr in _agrupar(np.where(conteo > 0.12 * (y_bot - y_top))[0])]
    verde = (r == 230) & (g == 255) & (b == 230)
    fila = verde[(y_top + y_bot) // 2, :x_fin]
    bandas = [(a_tiempo(gr[0]), a_tiempo(gr[-1]))
              for gr in _agrupar(np.where(fila)[0]) if len(gr) > 3]
    return cursores, bandas


def mmss(t: float) -> str:
    """Formato del equipo: m:ss (o s si es menor a un minuto)."""
    signo = "-" if t < 0 else ""
    t = abs(t)
    m, s = divmod(int(round(t)), 60)
    return f"{signo}{m}:{s:02d}" if m else f"{signo}{s}"


# --------------------------------------------------------------------------
# Procesamiento de una imagen
# --------------------------------------------------------------------------
def procesar(ruta_img: str, p_top=P_TOP_DEFAULT, p_bot=P_BOT_DEFAULT,
             tick_seg=TICK_SECONDS_DEFAULT, t_ref: float | None = None,
             pura_pantalla: float | None = None):
    """
    Ejecuta las cuatro etapas sobre una imagen y devuelve (datos, reporte,
    img). El reporte resume la calibración y la validación.
    """
    img = cargar(ruta_img)
    alto, ancho = img.shape[:2]

    # --- geometría ------------------------------------------------------
    bordes = bordes_horizontales(img)
    if len(bordes) < 3:
        raise RuntimeError(f"Bordes horizontales insuficientes: {bordes}")
    x_sep = limite_derecho(img, bordes[0], bordes[-1])
    y_top, y_bot = panel_presion(img, bordes, x_sep)
    y_regla = min(y for y in bordes if y > 10)

    # --- calibración horizontal ------------------------------------------
    xs, mayores = marcas_regla(img, y_regla, x_sep)
    cal = calibrar_tiempo(xs, mayores, tick_seg)
    x_ref = marca_referencia(cal, xs)
    t0 = 0.0 if t_ref is None else float(t_ref)
    px_s = cal["px_por_seg"]

    def a_tiempo(x):
        return t0 + (x - x_ref) / px_s

    # columnas útiles: donde existe regla (en algunas capturas el registro
    # empieza a mitad de pantalla y a la izquierda sólo hay relleno) y hasta
    # el separador de rótulos
    x_ini = 0 if xs[0] < 2 * cal["paso_px"] + 4 else int(np.ceil(xs[0]))
    x_fin = x_sep

    datos = extraer(img, y_top, y_bot, p_top, p_bot, px_s, x_ref, t0,
                    x_ini, x_fin)
    cursores, bandas = marcas_verticales(img, y_top, y_bot, x_fin, a_tiempo)

    validas = datos[datos[:, 4] == 0]
    final = float(np.median(datos[-3:, 1]))
    rep = {
        "imagen": ruta_img,
        "tamano_px": [ancho, alto],
        "bordes_horizontales": bordes,
        "panel_presion": [y_top, y_bot],
        "cmH2O_por_px": (p_top - p_bot) / (y_bot - y_top),
        "x_separador_rotulos": x_sep,
        "columnas_utiles": [int(datos[0, 5]), int(datos[-1, 5])],
        "regla_fila": y_regla,
        "regla_marcas": int(len(xs)),
        "regla_marcas_descartadas": cal["descartadas"],
        "regla_marcas_mayores": int(mayores.sum()),
        "px_por_seg": px_s,
        "regla_rms_px": cal["rms_px"],
        "regla_residuo_max_px": cal["res_max_px"],
        "regla_coherencia_mayores": cal["coherencia_mayores"],
        "x_marca_referencia": x_ref,
        "t_ref_s": t_ref,
        "t_inicio_s": float(datos[0, 0]),
        "t_fin_s": float(datos[-1, 0]),
        "muestras": int(len(datos)),
        "muestras_piso": int((datos[:, 4] == -1).sum()),
        "muestras_techo": int((datos[:, 4] == 1).sum()),
        "pura_final": final,
        "pura_max_valida": float(validas[:, 3].max()) if len(validas) else None,
        "pura_pantalla": pura_pantalla,
        "dif_final_vs_pantalla": (None if pura_pantalla is None
                                  else final - max(pura_pantalla, 0.0)),
        "cursores_s": [round(c, 2) for c in cursores],
        "bandas_s": [[round(a, 2), round(b, 2)] for a, b in bandas],
    }
    return datos, rep, img


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Digitaliza la curva roja Pura de un trazo Laborie.")
    ap.add_argument("imagen")
    ap.add_argument("-o", "--salida", default="pura.csv")
    ap.add_argument("--p-top", type=float, default=P_TOP_DEFAULT,
                    help="cm H2O en el borde superior del panel (def. 300)")
    ap.add_argument("--p-bot", type=float, default=P_BOT_DEFAULT,
                    help="cm H2O en el borde inferior del panel (def. 0)")
    ap.add_argument("--tick-seg", type=float, default=TICK_SECONDS_DEFAULT,
                    help="segundos entre marcas menores de la regla (def. 1)")
    ap.add_argument("--t-ref", type=float, default=None,
                    help="valor (s) del rótulo de la primera marca mayor visible")
    ap.add_argument("--pura-pantalla", type=float, default=None,
                    help="valor de Pura que muestra el equipo (validación)")
    ap.add_argument("--dt", type=float, default=None,
                    help="si se indica, remuestrea a paso constante dt (s)")
    ap.add_argument("--plot", default=None, help="ruta del PNG de verificación")
    ap.add_argument("--reporte", default=None, help="ruta del JSON de calibración")
    args = ap.parse_args(argv)

    datos, rep, img = procesar(args.imagen, args.p_top, args.p_bot,
                               args.tick_seg, args.t_ref, args.pura_pantalla)
    imprimir_reporte(rep)

    salida = remuestrear(datos, args.dt) if args.dt else datos
    guardar_csv(args.salida, salida)
    print(f"CSV escrito      : {args.salida}  ({len(salida)} filas)")

    if args.reporte:
        with open(args.reporte, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
    if args.plot:
        verificar(args.plot, img, datos, rep, args.p_top, args.p_bot)
        print(f"Verificación     : {args.plot}")
    return 0


def imprimir_reporte(rep: dict) -> None:
    y_top, y_bot = rep["panel_presion"]
    print(f"Panel de presión : filas {y_top}–{y_bot}  "
          f"({rep['cmH2O_por_px']:.4f} cm H2O/px)")
    print(f"Escala temporal  : {rep['px_por_seg']:.4f} px/s  "
          f"({rep['regla_marcas']} marcas, {rep['regla_marcas_descartadas']} descartadas, "
          f"rms {rep['regla_rms_px']:.2f} px, "
          f"coherencia mayores {rep['regla_coherencia_mayores']:.0%})")
    c0, c1 = rep["columnas_utiles"]
    print(f"Columnas útiles  : {c0}–{c1} (separador en x = {rep['x_separador_rotulos']})"
          f"  → t ∈ [{mmss(rep['t_inicio_s'])}, {mmss(rep['t_fin_s'])}]")
    print(f"Censura          : {rep['muestras_piso']} en piso, "
          f"{rep['muestras_techo']} en techo de {rep['muestras']}")
    linea = f"Pura final       : {rep['pura_final']:.1f} cm H2O"
    if rep["pura_pantalla"] is not None:
        linea += (f"  (pantalla {rep['pura_pantalla']:g}, "
                  f"dif {rep['dif_final_vs_pantalla']:+.1f})")
    print(linea)
    if rep["cursores_s"]:
        print("Cursores         : " + ", ".join(mmss(t) for t in rep["cursores_s"]))


def verificar(ruta, img, datos, rep, p_top, p_bot):
    """
    Superpone la curva reconstruida sobre la imagen original y anota, bajo la
    regla, el tiempo calculado para cada marca mayor: debe coincidir con el
    rótulo impreso por el equipo encima de la marca.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    y_top, y_bot = rep["panel_presion"]
    x_sep = rep["x_separador_rotulos"]
    px_s, x_ref = rep["px_por_seg"], rep["x_marca_referencia"]
    t0 = rep["t_ref_s"] or 0.0

    fig, ax = plt.subplots(2, 1, figsize=(16, 7.5),
                           gridspec_kw={"height_ratios": [1.15, 1]})
    ax[0].imshow(img.astype(np.uint8), interpolation="nearest")
    ax[0].plot(datos[:, 5], datos[:, 6], "b-", lw=0.7)
    for y in (y_top, y_bot):
        ax[0].axhline(y, color="orange", lw=0.6, ls="--")
    ax[0].axvline(x_sep, color="magenta", lw=0.8, ls="--")
    ax[0].axvline(datos[0, 5], color="magenta", lw=0.8, ls=":")
    # tiempos calculados de las marcas mayores
    paso = px_s * MAYOR_CADA
    k_min = int(np.ceil((datos[0, 5] - x_ref) / paso))
    k_max = int(np.floor((x_sep - x_ref) / paso))
    for k in range(k_min, k_max + 1):
        x = x_ref + k * paso
        ax[0].text(x, rep["regla_fila"] + 9, mmss(t0 + k * MAYOR_CADA),
                   color="blue", fontsize=5.5, ha="center", va="top")
    ax[0].set_title("Superposición (azul) · panel (naranja) · límites útiles (magenta) · "
                    "tiempo calculado bajo la regla", fontsize=9)
    ax[0].axis("off")

    t = datos[:, 0]
    ax[1].fill_between(t, datos[:, 2], datos[:, 3], color="red", alpha=0.25, lw=0)
    ax[1].plot(t, datos[:, 1], "r-", lw=0.9, label="Pura")
    for valor, color, nombre in ((-1, "gray", "piso (≤ ~5 cm H2O)"),
                                 (1, "black", "techo (≥ 300 cm H2O)")):
        sel = datos[:, 4] == valor
        if sel.any():
            ax[1].plot(t[sel], datos[sel, 1], ".", ms=2, color=color,
                       label=f"censurado: {nombre}")
    if rep["pura_pantalla"] is not None:
        ax[1].plot(t[-1], max(rep["pura_pantalla"], 0.0), "kD", ms=6, mfc="none",
                   label=f"valor en pantalla ({rep['pura_pantalla']:g})")
    ax[1].xaxis.set_major_locator(MultipleLocator(15))
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: mmss(v)))
    ax[1].set_xlim(t[0], t[-1])
    ax[1].set_xlabel("Tiempo del registro (m:ss)" if rep["t_ref_s"] is not None
                     else "Tiempo relativo (m:ss)")
    ax[1].set_ylabel("Pura (cm H2O)")
    ax[1].set_ylim(p_bot - 5, p_top + 5)
    ax[1].grid(alpha=0.3)
    ax[1].legend(loc="upper right", fontsize=8)
    ax[1].set_title(f"Curva reconstruida  ·  {rep['cmH2O_por_px']:.3f} cm H2O/px, "
                    f"{px_s:.3f} px/s", fontsize=9)
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
