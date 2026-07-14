# -*- coding: utf-8 -*-
"""Scatter de votos totales Cámara vs Senado por mesa."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "puestos_2026.db"
OUTPUT_PATH = ROOT / "viz" / "scatter_ca_se.png"

COLORES = {
    "TUNJA": "#007C34",
    "PAIPA": "#7B2D8B",
    "SOGAMOSO": "#1E477D",
    "DUITAMA": "#E07B00",
}


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró la base de datos: {DB_PATH}"
        )

    conexion = sqlite3.connect(DB_PATH)

    try:
        filas = conexion.execute(
            """
            WITH votos_mesa AS (
                SELECT
                    rp.mesa_id,
                    mu.nombre AS municipio,
                    SUM(
                        CASE
                            WHEN rp.corporacion = 'CA'
                            THEN rp.votos
                            ELSE 0
                        END
                    ) AS votos_ca,
                    SUM(
                        CASE
                            WHEN rp.corporacion = 'SE'
                            THEN rp.votos
                            ELSE 0
                        END
                    ) AS votos_se
                FROM resultados_partido rp
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                GROUP BY rp.mesa_id, mu.nombre
            )
            SELECT
                municipio,
                votos_ca,
                votos_se
            FROM votos_mesa
            WHERE votos_ca IS NOT NULL
              AND votos_se IS NOT NULL
            ORDER BY municipio, mesa_id;
            """
        ).fetchall()

    finally:
        conexion.close()

    if not filas:
        raise RuntimeError(
            "No se encontraron datos por mesa."
        )

    votos_ca = np.array(
        [float(fila[1] or 0) for fila in filas],
        dtype=float,
    )

    votos_se = np.array(
        [float(fila[2] or 0) for fila in filas],
        dtype=float,
    )

    municipios = [
        fila[0]
        for fila in filas
    ]

    if len(votos_ca) < 2:
        raise RuntimeError(
            "Se requieren al menos dos mesas."
        )

    pendiente, intercepto = np.polyfit(
        votos_ca,
        votos_se,
        1,
    )

    correlacion = float(
        np.corrcoef(votos_ca, votos_se)[0, 1]
    )

    figura, eje = plt.subplots(
        figsize=(11, 7)
    )

    for municipio in COLORES:
        mascara = np.array(
            [
                nombre == municipio
                for nombre in municipios
            ]
        )

        eje.scatter(
            votos_ca[mascara],
            votos_se[mascara],
            label=municipio.title(),
            alpha=0.65,
            s=28,
            color=COLORES[municipio],
            edgecolors="none",
        )

    x_linea = np.linspace(
        votos_ca.min(),
        votos_ca.max(),
        200,
    )

    y_linea = (
        pendiente * x_linea
        + intercepto
    )

    eje.plot(
        x_linea,
        y_linea,
        linestyle="--",
        linewidth=2,
        color="black",
        label="Regresión OLS",
    )

    texto = (
        f"r de Pearson = {correlacion:.3f}\n"
        f"Pendiente = {pendiente:.3f}\n"
        f"Mesas = {len(filas)}"
    )

    eje.text(
        0.03,
        0.96,
        texto,
        transform=eje.transAxes,
        va="top",
        ha="left",
        fontsize=11,
        bbox={
            "boxstyle": "round,pad=0.5",
            "facecolor": "white",
            "alpha": 0.9,
        },
    )

    eje.set_title(
        "Votos Cámara vs Senado por mesa - Boyacá 2026",
        fontsize=15,
        fontweight="bold",
        pad=18,
    )

    eje.set_xlabel(
        "Total de votos Cámara por mesa"
    )
    eje.set_ylabel(
        "Total de votos Senado por mesa"
    )

    eje.grid(
        alpha=0.2
    )

    eje.legend(
        title="Municipio",
        loc="lower right",
    )

    figura.tight_layout()

    figura.savefig(
        OUTPUT_PATH,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(figura)

    print(
        f"r={correlacion:.3f} | "
        f"pendiente={pendiente:.3f} | "
        f"n_mesas={len(filas)}"
    )

    print(
        f"Scatter generado: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()