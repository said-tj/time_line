#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STJ
"""
Construye la base de datos del sitio web a partir de los resultados de
create/ (manifiesto, resúmenes, series unidas y calibraciones).

Escribe:
    web/datos.js    window.DATOS = {...}  (un solo archivo, sin servidor)

El sitio (web/index.html) se abre directamente con doble clic: datos.js se
carga como script, de modo que no hace falta ningún servidor local ni
conexión a internet.

Uso:
    python3 scripts/generar_web.py [--raiz create] [--salida web/datos.js]

Sólo usa la biblioteca estándar: puede ejecutarse sin activar el entorno
conda del análisis.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import statistics as st

PISO, TECHO, VALIDO = -1, 1, 0
CENSURA_CHAR = {VALIDO: "0", PISO: "-", TECHO: "+"}

# Orden cronológico de las condiciones y color asignado en todo el sitio.
COLORES = {
    "Basal":    "#2f6f9f",
    "Proximal": "#1f9d8f",
    "Medial":   "#d98a2b",
    "Distal":   "#b4495f",
}

DICCIONARIO = [
    ("t_s", "Tiempo del registro del equipo (s); se muestra como m:ss, igual que en la regla de la pantalla."),
    ("pura_cmH2O", "Presión uretral: centroide del trazo en esa columna de píxeles."),
    ("pura_min_cmH2O / pura_max_cmH2O", "Envolvente del trazo; se separan del centroide en los tramos verticales rápidos."),
    ("censura", "0 válida · −1 piso (≤ ~5 cm H₂O, incluye valores negativos) · 1 techo (≥ ~294, el equipo satura en 300)."),
    ("x_px, y_px", "Posición en la imagen; sólo en los CSV de cada captura."),
    ("n_capturas", "Cuántas capturas se promediaron en ese instante; sólo en la serie unida de la sesión."),
]

ESTADOS = [
    ("OK", "El valor final reconstruido coincide con el que muestra el equipo dentro de ~1 px del panel (3 cm H₂O)."),
    ("OK_PISO", "La captura termina con el trazo en el piso del panel: el valor del equipo no es comparable y sólo se verifica que la serie también esté en el piso."),
    ("REVISAR", "La diferencia con la pantalla supera la tolerancia; conviene revisar el PNG de verificación de esa captura."),
]


def leer_csv(ruta: str) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    """Convierte a float/int los campos de texto de los CSV; '' → None."""
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f == int(f) and abs(f) < 1e15 and "." not in v and "e" not in v.lower() else f


def fila_num(fila: dict, textos=()) -> dict:
    return {k: (v if k in textos else num(v)) for k, v in fila.items()}


def leer_serie(ruta: str) -> dict:
    """Serie unida de una sesión → arreglos paralelos compactos."""
    t, p, lo, hi, cen = [], [], [], [], []
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t.append(float(r["t_s"]))
            p.append(round(float(r["pura_cmH2O"]), 2))
            lo.append(round(float(r["pura_min_cmH2O"]), 2))
            hi.append(round(float(r["pura_max_cmH2O"]), 2))
            cen.append(int(float(r["censura"])))

    # La rejilla es uniforme (paso dt); se guarda t0 y dt en vez del vector.
    paso = round(t[1] - t[0], 6)
    uniforme = all(abs(t[i] - (t[0] + i * paso)) < 1e-6 for i in range(len(t)))
    serie = {"t0": round(t[0], 3), "dt": paso, "n": len(t),
             "p": p, "lo": lo, "hi": hi,
             "c": "".join(CENSURA_CHAR[c] for c in cen)}
    if not uniforme:                      # resguardo: rejilla con huecos
        serie["t"] = [round(v, 3) for v in t]
    return serie


def estadisticos(serie: dict) -> dict:
    """Descriptores de la sesión; los de presión sólo sobre muestras válidas."""
    p, c = serie["p"], serie["c"]
    n = serie["n"]
    dur = (n - 1) * serie["dt"]
    val = [p[i] for i in range(n) if c[i] == "0"]
    n_piso = c.count("-")
    n_techo = c.count("+")

    i_max = max(range(n), key=lambda i: p[i])
    res = {
        "duracion_s": round(dur, 1),
        "muestras": n,
        "n_validas": len(val),
        "pct_piso": round(100 * n_piso / n, 1),
        "pct_techo": round(100 * n_techo / n, 1),
        "pura_max": round(max(p), 1),
        "t_pura_max": round(serie["t0"] + i_max * serie["dt"], 1),
    }
    if val:
        val_ord = sorted(val)
        res.update({
            "pura_media": round(st.fmean(val), 1),
            "pura_mediana": round(st.median(val), 1),
            "pura_de": round(st.pstdev(val), 1) if len(val) > 1 else 0.0,
            "pura_min": round(val_ord[0], 1),
            "pura_p5": round(val_ord[int(0.05 * (len(val) - 1))], 1),
            "pura_p95": round(val_ord[int(0.95 * (len(val) - 1))], 1),
        })
    # Integral de toda la serie (cm H2O·s), regla del trapecio sobre la rejilla.
    res["auc"] = round((sum(p) - 0.5 * (p[0] + p[-1])) * serie["dt"], 1)
    return res


def leer_calibracion(ruta: str) -> dict:
    """Parámetros de calibración de una captura, sin los vectores largos."""
    with open(ruta, encoding="utf-8") as f:
        cal = json.load(f)
    return {
        "tamano_px": cal.get("tamano_px"),
        "regla_marcas": cal.get("regla_marcas"),
        "regla_marcas_mayores": cal.get("regla_marcas_mayores"),
        "regla_residuo_max_px": round(cal.get("regla_residuo_max_px", 0), 3),
        "x_marca_referencia": round(cal.get("x_marca_referencia", 0), 1),
        "cursores_s": cal.get("cursores_s", []),
        "n_bandas": len(cal.get("bandas_s", [])),
    }


def construir(raiz: str, rel_web: str) -> dict:
    manifiesto = leer_csv(os.path.join(raiz, "manifiesto.csv"))
    capturas = {r["captura"]: fila_num(r, textos=("sujeto", "condicion", "captura", "estado"))
                for r in leer_csv(os.path.join(raiz, "resumen_capturas.csv"))}
    solapes = [fila_num(r, textos=("sujeto", "condicion", "captura_a", "captura_b"))
               for r in leer_csv(os.path.join(raiz, "resumen_solapamientos.csv"))]

    sesiones = []
    for fila in manifiesto:
        suj, cond = fila["sujeto"], fila["condicion"]
        ses = next((s for s in sesiones if s["sujeto"] == suj and s["condicion"] == cond), None)
        if ses is None:
            base = f"{suj}_{cond}"
            ses = {
                "id": base,
                "sujeto": suj,
                "condicion": cond,
                "orden": int(fila["orden_condicion"]),
                "color": COLORES.get(cond, "#6b7280"),
                "png": f"{rel_web}/{base}/sesion_{base}.png",
                "csv": f"{rel_web}/{base}/pura_{base}.csv",
                "capturas": [],
                "solapamientos": [s for s in solapes
                                  if s["sujeto"] == suj and s["condicion"] == cond],
            }
            ses["serie"] = leer_serie(os.path.join(raiz, base, f"pura_{base}.csv"))
            ses["resumen"] = estadisticos(ses["serie"])
            sesiones.append(ses)

        nom = fila["captura"]
        carpeta = os.path.dirname(fila["imagen"])          # <base>/a_NN/origin
        cap = dict(capturas.get(nom, {}))
        cap.update({
            "captura": nom,
            "rotulo_ref": fila["rotulo_ref"],
            "t_ref_s": num(fila["t_ref_s"]),
            "pura_pantalla": num(fila["pura_pantalla"]),
            "pura_max_pantalla": num(fila["pura_max_pantalla"]),
            "notas": fila["notas"],
            "img": {
                "pantalla": f"{rel_web}/{carpeta}/{nom}.png",
                "recorte": f"{rel_web}/{carpeta}/{nom}_b.png",
                "verificacion": f"{rel_web}/{carpeta}/verificacion_{nom}_b.png",
            },
            "csv": f"{rel_web}/{carpeta}/pura_{nom}_b.csv",
            "calib": leer_calibracion(os.path.join(raiz, carpeta,
                                                   f"calibracion_{nom}_b.json")),
        })
        ses["capturas"].append(cap)

    sesiones.sort(key=lambda s: (s["sujeto"], s["orden"]))
    return {
        "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "titulo": "Presión uretral (Pura) · digitalización de registros Goby",
        "subtitulo": ("Análisis del comportamiento uretral durante el estado basal "
                      "y después de la aplicación de CGRP en la coneja"),
        "sujetos": sorted({s["sujeto"] for s in sesiones}),
        "sesiones": sesiones,
        "diccionario": [{"columna": c, "descripcion": d} for c, d in DICCIONARIO],
        "estados": [{"estado": e, "descripcion": d} for e, d in ESTADOS],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default="create", help="carpeta de resultados")
    ap.add_argument("--salida", default="web/datos.js", help="archivo JS a escribir")
    args = ap.parse_args()

    # Ruta de create/ vista desde web/index.html
    rel_web = os.path.relpath(args.raiz, os.path.dirname(args.salida) or ".")
    datos = construir(args.raiz, rel_web.replace(os.sep, "/"))

    os.makedirs(os.path.dirname(args.salida) or ".", exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as f:
        f.write("// Generado por scripts/generar_web.py — no editar a mano.\n")
        f.write("window.DATOS = ")
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    kb = os.path.getsize(args.salida) / 1024
    print(f"{args.salida}  ({kb:.0f} kB)")
    for s in datos["sesiones"]:
        r = s["resumen"]
        print(f"  {s['id']:22s} {len(s['capturas']):2d} capturas  "
              f"{r['muestras']:5d} muestras  {r['duracion_s']:7.1f} s  "
              f"máx {r['pura_max']:6.1f} cm H2O")


if __name__ == "__main__":
    main()
