#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digitalización de la curva roja (canal «Pura», cm H2O) de un trazo urodinámico
Laborie exportado como imagen.

El procedimiento consta de tres etapas:

  1. Calibración vertical: se localizan las líneas horizontales oscuras que
     delimitan los paneles del trazo. El panel de presión queda acotado por
     y_top (valor P_TOP) e y_bot (valor P_BOT); la conversión es afín.
  2. Calibración horizontal: se localizan las marcas de la regla temporal
     superior y se ajusta por mínimos cuadrados x(n) = s*n + x0, donde n es el
     índice de marca (1 s por marca menor) y s la escala en px/s.
  3. Extracción: para cada columna de píxeles se calcula el centroide
     ponderado por «rojez» de los píxeles rojos dentro del panel, lo que
     otorga resolución subpíxel; además se registran los extremos superior e
     inferior de la columna (envolvente de los tramos verticales).

Uso:
    python3 extraer_pura.py imagen.png -o salida.csv --plot verificacion.png

Parámetros de calibración por omisión ajustados a la captura de 1366 px de
ancho: panel inferior 0–300 cm H2O, regla temporal con marcas menores de 1 s.
"""

from __future__ import annotations

import argparse
import csv
import sys

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# Parámetros por omisión (modificables por línea de comandos)
# --------------------------------------------------------------------------
P_TOP_DEFAULT = 300.0      # cm H2O en el borde superior del panel de presión
P_BOT_DEFAULT = 0.0        # cm H2O en el borde inferior del panel de presión
TICK_SECONDS_DEFAULT = 1.0  # segundos entre marcas menores de la regla


# --------------------------------------------------------------------------
# Utilidades de detección
# --------------------------------------------------------------------------
def cargar(ruta: str) -> np.ndarray:
    """Devuelve la imagen como arreglo entero de forma (alto, ancho, 3)."""
    return np.array(Image.open(ruta).convert("RGB")).astype(int)


def mascara_oscura(img: np.ndarray, umbral: int = 140) -> np.ndarray:
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    return (r < umbral) & (g < umbral) & (b < umbral)


def lineas_horizontales(img: np.ndarray, frac: float = 0.85) -> list[int]:
    """Filas que constituyen bordes de panel (línea oscura casi completa)."""
    oscuro = mascara_oscura(img)
    ancho = img.shape[1]
    filas = [int(y) for y in range(img.shape[0])
             if oscuro[y].sum() > frac * ancho]
    # se agrupan filas contiguas (los bordes pueden tener 2 px de grosor)
    grupos, actual = [], [filas[0]] if filas else []
    for y in filas[1:]:
        if y - actual[-1] <= 1:
            actual.append(y)
        else:
            grupos.append(int(round(np.mean(actual))))
            actual = [y]
    if actual:
        grupos.append(int(round(np.mean(actual))))
    return grupos


def panel_presion(img: np.ndarray) -> tuple[int, int]:
    """(y_top, y_bot) del panel que contiene la mayor cantidad de píxeles rojos."""
    bordes = lineas_horizontales(img)
    if len(bordes) < 2:
        raise RuntimeError("No se detectaron los bordes horizontales del trazo.")
    rojo = mascara_roja(img)[0]
    mejor, conteo_max = None, -1
    for y0, y1 in zip(bordes[:-1], bordes[1:]):
        if y1 - y0 < 20:
            continue
        c = rojo[y0 + 1:y1].sum()
        if c > conteo_max:
            conteo_max, mejor = c, (y0, y1)
    if mejor is None:
        raise RuntimeError("No se identificó el panel de presión.")
    return mejor


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


def calibrar_tiempo(img: np.ndarray, y_regla_max: int,
                    tick_seg: float) -> tuple[float, float]:
    """
    Ajusta la escala temporal a partir de las marcas de la regla superior.

    Devuelve (px_por_segundo, x_en_t0).
    """
    oscuro = mascara_oscura(img)
    banda = oscuro[:y_regla_max]
    # la fila de la regla con mayor número de marcas separadas
    mejor_fila, mejor_grupos = None, []
    for y in range(banda.shape[0]):
        g = _grupos(np.where(banda[y])[0])
        if len(g) > len(mejor_grupos):
            mejor_fila, mejor_grupos = y, g
    if len(mejor_grupos) < 10:
        raise RuntimeError("No se detectó la regla temporal.")
    # se descartan los bordes verticales del marco
    ancho = img.shape[1]
    marcas = np.array([x for x in mejor_grupos if 3 < x < ancho - 40])
    # escala aproximada: mediana de las separaciones más pequeñas
    sep = np.diff(marcas)
    paso = float(np.median(sep[sep <= np.percentile(sep, 60)]))
    # Índices enteros acumulados: cada separación es un múltiplo entero del
    # paso. La asignación incremental evita la deriva que produciría redondear
    # (x - x0)/paso con un paso ligeramente sesgado.
    s = paso
    x_prim = float(marcas[0])
    for _ in range(5):
        n = np.concatenate([[0.0], np.cumsum(np.maximum(np.round(sep / s), 1))])
        A = np.vstack([n, np.ones(len(n))]).T
        (s_new, x_prim), *_ = np.linalg.lstsq(A, marcas, rcond=None)
        if abs(s_new - s) < 1e-6:
            s = float(s_new)
            break
        s = float(s_new)
    px_por_seg = s / tick_seg
    return float(px_por_seg), float(x_prim)


def _grupos(xs: np.ndarray) -> list[float]:
    """Centros de grupos de píxeles contiguos."""
    if len(xs) == 0:
        return []
    out, ini, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > 1:
            out.append((ini + prev) / 2.0)
            ini = x
        prev = x
    out.append((ini + prev) / 2.0)
    return out


# --------------------------------------------------------------------------
# Extracción
# --------------------------------------------------------------------------
def extraer(img: np.ndarray, y_top: int, y_bot: int,
            p_top: float, p_bot: float,
            px_por_seg: float, x_t0: float,
            x_min: int | None = None, x_max: int | None = None):
    """
    Recorre las columnas del panel y devuelve un arreglo estructurado con
    tiempo, presión (centroide) y envolvente mínima/máxima por columna.
    """
    mask, peso = mascara_roja(img)
    interior = slice(y_top + 1, y_bot)
    ys = np.arange(img.shape[0])[interior]

    x_ini = 0 if x_min is None else x_min
    x_fin = img.shape[1] if x_max is None else x_max

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
        filas.append((
            (x - x_t0) / px_por_seg,
            a_presion(y_c),
            a_presion(y_lo),
            a_presion(y_hi),
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
    return np.column_stack(cols)


def guardar_csv(ruta: str, datos: np.ndarray, encabezado: list[str]) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(encabezado)
        for fila in datos:
            w.writerow([f"{fila[0]:.4f}", f"{fila[1]:.2f}",
                        f"{fila[2]:.2f}", f"{fila[3]:.2f}"]
                       + ([f"{v:.2f}" for v in fila[4:]] if len(fila) > 4 else []))


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
    ap.add_argument("--y-top", type=int, default=None, help="fila del borde superior (opcional)")
    ap.add_argument("--y-bot", type=int, default=None, help="fila del borde inferior (opcional)")
    ap.add_argument("--tick-seg", type=float, default=TICK_SECONDS_DEFAULT,
                    help="segundos entre marcas menores de la regla (def. 1)")
    ap.add_argument("--px-por-seg", type=float, default=None,
                    help="escala temporal forzada, en px/s")
    ap.add_argument("--x-t0", type=float, default=None,
                    help="columna correspondiente a t = 0 s")
    ap.add_argument("--x-max", type=int, default=None,
                    help="última columna útil (excluye el marcador triangular derecho)")
    ap.add_argument("--recortar-negativos", action="store_true",
                    help="descarta las muestras anteriores a t = 0 s")
    ap.add_argument("--dt", type=float, default=None,
                    help="si se indica, remuestrea a paso constante dt (s)")
    ap.add_argument("--plot", default=None, help="ruta del PNG de verificación")
    args = ap.parse_args(argv)

    img = cargar(args.imagen)

    # --- calibración vertical -------------------------------------------
    if args.y_top is None or args.y_bot is None:
        y_top, y_bot = panel_presion(img)
    else:
        y_top, y_bot = args.y_top, args.y_bot

    # --- calibración horizontal -----------------------------------------
    if args.px_por_seg is None or args.x_t0 is None:
        px_s, x_t0 = calibrar_tiempo(img, y_regla_max=y_top, tick_seg=args.tick_seg)
    else:
        px_s, x_t0 = args.px_por_seg, args.x_t0

    x_max = args.x_max
    if x_max is None:
        # se excluye la zona de rótulos: última línea vertical del marco
        x_max = _limite_derecho(img, y_top, y_bot)

    datos = extraer(img, y_top, y_bot, args.p_top, args.p_bot,
                    px_s, x_t0, x_max=x_max)

    if args.recortar_negativos:
        datos = datos[datos[:, 0] >= 0.0]

    print(f"Panel de presión : filas {y_top}–{y_bot}  "
          f"({args.p_bot:g}–{args.p_top:g} cm H2O, "
          f"{(args.p_top - args.p_bot) / (y_bot - y_top):.4f} cm H2O/px)")
    print(f"Escala temporal  : {px_s:.4f} px/s  (t = 0 en x = {x_t0:.2f})")
    print(f"Columnas útiles  : {int(datos[0,4])}–{int(datos[-1,4])}  "
          f"→ t ∈ [{datos[0,0]:.2f}, {datos[-1,0]:.2f}] s")
    print(f"Presión          : mín {datos[:,2].min():.1f}, "
          f"máx {datos[:,3].max():.1f}, final {datos[-1,1]:.1f} cm H2O")

    cursores, banda = marcas_verticales(img, y_top, y_bot, px_s, x_t0, x_max)
    if cursores:
        print("Cursores (s)     : " + ", ".join(f"{t:.2f}" for t in cursores))
    if banda:
        print(f"Banda sombreada  : {banda[0]:.2f} – {banda[1]:.2f} s")

    if args.dt:
        salida = remuestrear(datos, args.dt)
        encabezado = ["t_s", "pura_cmH2O", "pura_min_cmH2O", "pura_max_cmH2O"]
    else:
        salida = datos
        encabezado = ["t_s", "pura_cmH2O", "pura_min_cmH2O", "pura_max_cmH2O",
                      "x_px", "y_px"]
    guardar_csv(args.salida, salida, encabezado)
    print(f"CSV escrito      : {args.salida}  ({len(salida)} filas)")

    if args.plot:
        _verificar(args.plot, img, datos, y_top, y_bot,
                   args.p_top, args.p_bot, px_s, x_t0)
        print(f"Verificación     : {args.plot}")
    return 0


def marcas_verticales(img: np.ndarray, y_top: int, y_bot: int,
                      px_s: float, x_t0: float, x_max: int):
    """
    Devuelve (cursores, banda): instantes de las líneas verticales punteadas
    azules y extremos temporales de la región sombreada en verde, en segundos.
    """
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    azul = (b > 150) & (b - np.maximum(r, g) > 40)
    conteo = azul[y_top + 3:y_bot - 1, :x_max].sum(0)
    cursores = [(x - x_t0) / px_s
                for x in _grupos(np.where(conteo > 0.12 * (y_bot - y_top))[0])]
    verde = (r == 230) & (g == 255) & (b == 230)
    cols = np.where(verde[(y_top + y_bot) // 2, :x_max])[0]
    banda = ((cols.min() - x_t0) / px_s, (cols.max() - x_t0) / px_s) if len(cols) else None
    return cursores, banda


def _limite_derecho(img: np.ndarray, y_top: int, y_bot: int) -> int:
    """Columna de la línea vertical que separa el trazo de la zona de rótulos."""
    oscuro = mascara_oscura(img)
    alto = y_bot - y_top - 2
    cols = [x for x in range(img.shape[1])
            if oscuro[y_top + 1:y_bot, x].sum() > 0.9 * alto]
    interiores = [x for x in cols if x > img.shape[1] * 0.6]
    if len(interiores) >= 2:
        return interiores[-2]          # se descarta el marco exterior
    return img.shape[1] - 1


def _verificar(ruta, img, datos, y_top, y_bot, p_top, p_bot, px_s, x_t0):
    """Superpone la curva reconstruida sobre la imagen original."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 1, figsize=(16, 6),
                           gridspec_kw={"height_ratios": [1, 1.4]})
    ax[0].imshow(img.astype(np.uint8))
    ax[0].plot(datos[:, 4], datos[:, 5], "b-", lw=0.7)
    ax[0].set_title("Superposición sobre la imagen original")
    ax[0].axis("off")

    ax[1].fill_between(datos[:, 0], datos[:, 2], datos[:, 3],
                       color="red", alpha=0.25, lw=0)
    ax[1].plot(datos[:, 0], datos[:, 1], "r-", lw=0.9)
    ax[1].set_xlabel("Tiempo (s)")
    ax[1].set_ylabel("Pura (cm H2O)")
    ax[1].set_ylim(p_bot, p_top)
    ax[1].grid(alpha=0.3)
    ax[1].set_title("Curva reconstruida a partir del CSV")
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
