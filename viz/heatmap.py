# -*- coding: utf-8 -*-
"""Heatmap de los 8 candidatos de Cámara con mayor votación."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "puestos_2026.db"
OUTPUT_PATH = ROOT / "viz" / "heatmap_municipios.png"

MUNICIPIOS_ORDEN = [
    "TUNJA",
    "PAIPA",
    "SOGAMOSO",
    "DUITAMA",
]


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró la base de datos: {DB_PATH}"
        )

    conexion = sqlite3.connect(DB_PATH)

    try:
        top_candidatos = conexion.execute(
            """
            SELECT
                c.id,
                c.nombre,
                SUM(r.votos) AS total_votos
            FROM resultados r
            INNER JOIN candidatos c
                ON c.id = r.candidato_id
            WHERE r.corporacion = 'CA'
              AND c.codigo <> '0'
              AND UPPER(c.nombre) <> 'SOLO POR LA LISTA'
            GROUP BY c.id, c.nombre
            ORDER BY total_votos DESC, c.nombre
            LIMIT 8;
            """
        ).fetchall()

        if not top_candidatos:
            raise RuntimeError(
                "No se encontraron candidatos de Cámara."
            )

        candidatos_ids = [fila[0] for fila in top_candidatos]
        candidatos_nombres = [
            fila[1].title()
            for fila in top_candidatos
        ]

        placeholders = ",".join(
            "?" for _ in candidatos_ids
        )

        filas = conexion.execute(
            f"""
            WITH totales_municipio AS (
                SELECT
                    mu.nombre AS municipio,
                    SUM(r.votos) AS total_votos
                FROM resultados r
                INNER JOIN candidatos c
                    ON c.id = r.candidato_id
                INNER JOIN mesas m
                    ON m.id = r.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                WHERE r.corporacion = 'CA'
                  AND c.codigo <> '0'
                  AND UPPER(c.nombre) <> 'SOLO POR LA LISTA'
                GROUP BY mu.nombre
            ),
            votos_candidato AS (
                SELECT
                    c.id AS candidato_id,
                    mu.nombre AS municipio,
                    SUM(r.votos) AS votos
                FROM resultados r
                INNER JOIN candidatos c
                    ON c.id = r.candidato_id
                INNER JOIN mesas m
                    ON m.id = r.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                WHERE r.corporacion = 'CA'
                  AND c.id IN ({placeholders})
                GROUP BY c.id, mu.nombre
            )
            SELECT
                vc.candidato_id,
                vc.municipio,
                vc.votos,
                tm.total_votos,
                ROUND(
                    100.0 * vc.votos
                    / NULLIF(tm.total_votos, 0),
                    2
                ) AS porcentaje
            FROM votos_candidato vc
            INNER JOIN totales_municipio tm
                ON tm.municipio = vc.municipio;
            """,
            candidatos_ids,
        ).fetchall()

    finally:
        conexion.close()

    indices_candidatos = {
        candidato_id: indice
        for indice, candidato_id
        in enumerate(candidatos_ids)
    }

    indices_municipios = {
        municipio: indice
        for indice, municipio
        in enumerate(MUNICIPIOS_ORDEN)
    }

    matriz = np.zeros(
        (
            len(candidatos_ids),
            len(MUNICIPIOS_ORDEN),
        ),
        dtype=float,
    )

    for candidato_id, municipio, _, _, porcentaje in filas:
        if (
            candidato_id in indices_candidatos
            and municipio in indices_municipios
        ):
            matriz[
                indices_candidatos[candidato_id],
                indices_municipios[municipio],
            ] = float(porcentaje or 0)

    figura, eje = plt.subplots(figsize=(12, 8))

    imagen = eje.imshow(
        matriz,
        aspect="auto",
        cmap="YlGn",
    )

    eje.set_xticks(
        range(len(MUNICIPIOS_ORDEN))
    )
    eje.set_xticklabels(
        [nombre.title() for nombre in MUNICIPIOS_ORDEN],
        fontsize=11,
    )

    eje.set_yticks(
        range(len(candidatos_nombres))
    )
    eje.set_yticklabels(
        candidatos_nombres,
        fontsize=9,
    )

    eje.set_title(
        "Top 8 candidatos Cámara: porcentaje por municipio",
        fontsize=15,
        fontweight="bold",
        pad=18,
    )

    eje.set_xlabel("Municipio")
    eje.set_ylabel("Candidato")

    limite = matriz.max() / 2 if matriz.size else 0

    for fila in range(matriz.shape[0]):
        for columna in range(matriz.shape[1]):
            valor = matriz[fila, columna]

            eje.text(
                columna,
                fila,
                f"{valor:.2f}%",
                ha="center",
                va="center",
                fontsize=9,
                color="white" if valor > limite else "black",
                fontweight="bold",
            )

    barra = figura.colorbar(
        imagen,
        ax=eje,
        fraction=0.035,
        pad=0.03,
    )
    barra.set_label(
        "% del total de votos CA del municipio"
    )

    figura.tight_layout()

    figura.savefig(
        OUTPUT_PATH,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(figura)

    print(f"Heatmap generado: {OUTPUT_PATH}")
    print(f"candidatos=8 | municipios=4")


if __name__ == "__main__":
    main()