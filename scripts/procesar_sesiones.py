#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STJ
"""
Procesamiento por lotes de las capturas listadas en create/manifiesto.csv.

Para cada captura escribe, junto a la imagen (carpeta origin/):
    pura_<captura>_b.csv          serie digitalizada (tiempo del registro)
    verificacion_<captura>_b.png  superposición y curva reconstruida
    calibracion_<captura>_b.json  parámetros de calibración y validación

Para cada condición (sesión de registro) une las capturas, que se traslapan
parcialmente, en una rejilla temporal común promediando los solapamientos:
    <sujeto>_<condicion>/pura_<sujeto>_<condicion>.csv
    <sujeto>_<condicion>/sesion_<sujeto>_<condicion>.png

Y en create/ escribe dos tablas de control:
    resumen_capturas.csv       calibración y validación contra la pantalla
    resumen_solapamientos.csv  concordancia entre capturas consecutivas

Uso:
    python3 scripts/procesar_sesiones.py [--raiz create] [--dt 0.1]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import warnings
from collections import OrderedDict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extraer_pura as ep  # noqa: E402

DT_DEFAULT = 0.1           # s, paso de la rejilla de unión
TOLERANCIA_PANTALLA = 3.0  # cm H2O (≈ 1 px del panel de 0–300)
PISO_CMH2O = 5.0           # valores en pantalla por debajo quedan en el piso
LAG_MAX = 3.0              # s, búsqueda de desfase entre capturas


def leer_manifiesto(ruta: str) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(v: str):
    return None if v is None or v.strip() == "" else float(v)


def procesar_captura(raiz: str, fila: dict) -> tuple[np.ndarray, dict]:
    ruta_img = os.path.join(raiz, fila["imagen"])
    carpeta = os.path.dirname(ruta_img)
    base = os.path.splitext(os.path.basename(ruta_img))[0]
    datos, rep, img = ep.procesar(ruta_img, t_ref=_num(fila["t_ref_s"]),
                                  pura_pantalla=_num(fila["pura_pantalla"]))
    rep["imagen"] = fila["imagen"]
    ep.guardar_csv(os.path.join(carpeta, f"pura_{base}.csv"), datos)
    with open(os.path.join(carpeta, f"calibracion_{base}.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    ep.verificar(os.path.join(carpeta, f"verificacion_{base}.png"), img, datos,
                 rep, ep.P_TOP_DEFAULT, ep.P_BOT_DEFAULT)
    return datos, rep


def a_rejilla(datos: np.ndarray, rejilla: np.ndarray):
    """
    Interpola Pura (y su envolvente) en la rejilla dentro del intervalo
    cubierto por la captura; fuera de él devuelve NaN. La censura se toma de
    la muestra más cercana.
    """
    t = datos[:, 0]
    dentro = (rejilla >= t[0]) & (rejilla <= t[-1])
    out = np.full((len(rejilla), 4), np.nan)
    for j, k in enumerate((1, 2, 3)):
        out[dentro, j] = np.interp(rejilla[dentro], t, datos[:, k])
    idx = np.clip(np.searchsorted(t, rejilla[dentro]), 0, len(t) - 1)
    out[dentro, 3] = datos[idx, 4]
    return out


def comparar(a: np.ndarray, b: np.ndarray, dt: float) -> dict:
    """
    Concordancia de dos capturas en su solapamiento (muestras no censuradas):
    diferencia media, RMS y desfase temporal que maximiza la correlación.
    """
    comun = ~np.isnan(a[:, 0]) & ~np.isnan(b[:, 0])
    validas = comun & (a[:, 3] == 0) & (b[:, 3] == 0)
    res = {"solape_s": float(comun.sum() * dt), "solape_valido_s": float(validas.sum() * dt),
           "dif_media": None, "dif_rms": None, "desfase_s": None, "correlacion": None}
    if validas.sum() < 20:
        return res
    d = b[validas, 0] - a[validas, 0]
    res["dif_media"] = float(d.mean())
    res["dif_rms"] = float(np.sqrt(np.mean(d ** 2)))
    # desfase: se desplaza b respecto de a dentro de ±LAG_MAX
    ia = np.where(comun)[0]
    xa, xb = a[:, 0], b[:, 0]
    mejor = (-np.inf, 0)
    pasos = int(round(LAG_MAX / dt))
    for k in range(-pasos, pasos + 1):
        j = ia + k
        ok = (j >= 0) & (j < len(xb))
        j, i = j[ok], ia[ok]
        ok = ~np.isnan(xb[j])
        if ok.sum() < 20:
            continue
        u, v = xa[i[ok]], xb[j[ok]]
        if u.std() == 0 or v.std() == 0:
            continue
        r = float(np.corrcoef(u, v)[0, 1])
        if r > mejor[0]:
            mejor = (r, k)
    if np.isfinite(mejor[0]):
        res["correlacion"] = mejor[0]
        res["desfase_s"] = mejor[1] * dt
    return res


def unir_sesion(capturas: list[tuple[str, np.ndarray]], dt: float):
    t_ini = min(d[0, 0] for _, d in capturas)
    t_fin = max(d[-1, 0] for _, d in capturas)
    rejilla = np.round(np.arange(np.floor(t_ini / dt) * dt, t_fin + dt / 2, dt), 6)
    series = [a_rejilla(d, rejilla) for _, d in capturas]
    pila = np.stack(series)                       # (capturas, tiempo, 4)
    n = (~np.isnan(pila[:, :, 0])).sum(0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        prom = np.nanmean(pila[:, :, :3], axis=0)
        cens = np.nanmax(np.abs(pila[:, :, 3]), axis=0) * np.sign(np.nansum(pila[:, :, 3], axis=0))
    ok = n > 0
    return rejilla[ok], prom[ok], cens[ok], n[ok], series, rejilla


def guardar_sesion(ruta: str, t, prom, cens, n) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "pura_cmH2O", "pura_min_cmH2O", "pura_max_cmH2O",
                    "censura", "n_capturas"])
        for i in range(len(t)):
            w.writerow([f"{t[i]:.1f}", f"{prom[i, 0]:.2f}", f"{prom[i, 1]:.2f}",
                        f"{prom[i, 2]:.2f}", int(cens[i]), int(n[i])])


def graficar_sesion(ruta, titulo, capturas, t, prom, cens):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    fig, ax = plt.subplots(2, 1, figsize=(16, 7), sharex=True,
                           gridspec_kw={"height_ratios": [1, 1]})
    colores = plt.cm.tab10.colors
    for i, (nombre, d) in enumerate(capturas):
        ax[0].plot(d[:, 0], d[:, 1], lw=0.8, color=colores[i % 10], label=nombre)
    ax[0].set_title(f"{titulo}: capturas superpuestas en el tiempo del registro")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[1].plot(t, prom[:, 0], "r-", lw=0.8, label="Pura (promedio en solapes)")
    sel = cens != 0
    if sel.any():
        ax[1].plot(t[sel], prom[sel, 0], ".", ms=1.5, color="gray", label="censurado")
    ax[1].set_title(f"{titulo}: serie unida")
    ax[1].legend(loc="upper right", fontsize=8)
    for a in ax:
        a.set_ylabel("Pura (cm H2O)")
        a.set_ylim(-5, 305)
        a.grid(alpha=0.3)
    ax[1].xaxis.set_major_locator(MultipleLocator(60))
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: ep.mmss(v)))
    ax[1].set_xlabel("Tiempo del registro (m:ss)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=110)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Digitaliza y une todas las capturas del manifiesto.")
    ap.add_argument("--raiz", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "create"))
    ap.add_argument("--manifiesto", default=None)
    ap.add_argument("--dt", type=float, default=DT_DEFAULT)
    args = ap.parse_args(argv)
    manifiesto = args.manifiesto or os.path.join(args.raiz, "manifiesto.csv")
    filas = leer_manifiesto(manifiesto)

    resumen, solapes = [], []
    sesiones: OrderedDict[tuple, list] = OrderedDict()
    for fila in filas:
        datos, rep = procesar_captura(args.raiz, fila)
        dif = rep["dif_final_vs_pantalla"]
        pantalla = _num(fila["pura_pantalla"])
        estado = "OK"
        if pantalla is not None and pantalla <= PISO_CMH2O and datos[-1, 4] == -1:
            estado = "OK_PISO"      # ambos en el piso: valor real ≤ ~5 cm H2O
        elif dif is not None and abs(dif) > TOLERANCIA_PANTALLA:
            estado = "REVISAR"
        if rep["regla_rms_px"] > 0.5 or rep["regla_coherencia_mayores"] < 0.9:
            estado = "REVISAR"
        print(f"{fila['captura']:5s} {fila['condicion']:9s} "
              f"{rep['cmH2O_por_px']:.3f} cmH2O/px  {rep['px_por_seg']:.3f} px/s  "
              f"rms {rep['regla_rms_px']:.2f}  t [{ep.mmss(rep['t_inicio_s'])}, "
              f"{ep.mmss(rep['t_fin_s'])}]  final {rep['pura_final']:6.1f} vs "
              f"{fila['pura_pantalla']:>4s}  {estado}")
        resumen.append({
            "sujeto": fila["sujeto"], "condicion": fila["condicion"],
            "captura": fila["captura"],
            "panel_y_top": rep["panel_presion"][0], "panel_y_bot": rep["panel_presion"][1],
            "cmH2O_por_px": round(rep["cmH2O_por_px"], 4),
            "px_por_seg": round(rep["px_por_seg"], 4),
            "regla_rms_px": round(rep["regla_rms_px"], 3),
            "regla_coherencia_mayores": round(rep["regla_coherencia_mayores"], 3),
            "x_inicio": rep["columnas_utiles"][0], "x_fin": rep["columnas_utiles"][1],
            "x_separador": rep["x_separador_rotulos"],
            "t_inicio_s": round(rep["t_inicio_s"], 2), "t_fin_s": round(rep["t_fin_s"], 2),
            "muestras": rep["muestras"], "piso": rep["muestras_piso"],
            "techo": rep["muestras_techo"],
            "pura_max_valida": round(rep["pura_max_valida"], 1),
            "pura_final": round(rep["pura_final"], 1),
            "pura_pantalla": fila["pura_pantalla"],
            "dif_final_vs_pantalla": None if dif is None else round(dif, 1),
            "estado": estado,
        })
        clave = (fila["sujeto"], fila["condicion"])
        sesiones.setdefault(clave, []).append((fila["captura"], datos))

    for (sujeto, cond), capturas in sesiones.items():
        nombre = f"{sujeto}_{cond}"
        carpeta = os.path.join(args.raiz, nombre)
        t, prom, cens, n, series, _ = unir_sesion(capturas, args.dt)
        guardar_sesion(os.path.join(carpeta, f"pura_{nombre}.csv"), t, prom, cens, n)
        graficar_sesion(os.path.join(carpeta, f"sesion_{nombre}.png"), nombre,
                        capturas, t, prom, cens)
        for i in range(len(capturas) - 1):
            c = comparar(series[i], series[i + 1], args.dt)
            solapes.append({"sujeto": sujeto, "condicion": cond,
                            "captura_a": capturas[i][0], "captura_b": capturas[i + 1][0],
                            **{k: (None if v is None else round(v, 3)) for k, v in c.items()}})

    for ruta, tabla in ((os.path.join(args.raiz, "resumen_capturas.csv"), resumen),
                        (os.path.join(args.raiz, "resumen_solapamientos.csv"), solapes)):
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(tabla[0].keys()))
            w.writeheader()
            w.writerows(tabla)

    print("\nSolapamientos (b - a):")
    for s in solapes:
        print(f"  {s['condicion']:9s} {s['captura_a']}→{s['captura_b']}: "
              f"{s['solape_s']:5.1f} s (válido {s['solape_valido_s']:5.1f} s)  "
              f"dif media {s['dif_media']}  rms {s['dif_rms']}  "
              f"desfase {s['desfase_s']} s  r {s['correlacion']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
