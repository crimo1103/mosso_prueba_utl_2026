"""Genera una grafica de participacion electoral por municipio."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "puestos_2026.db"
OUTPUT_PATH = ROOT / "viz" / "participacion_municipio.png"


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No se encontro la base de datos: {DB_PATH}"
        )

    conexion = sqlite3.connect(DB_PATH)

    try:
        cursor = conexion.execute(
            """
            SELECT
                mu.nombre AS municipio,
                SUM(COALESCE(m.potencial_sufragantes, 0)) AS potencial,
                SUM(COALESCE(m.total_votantes, 0)) AS votantes
            FROM municipios mu
            INNER JOIN puestos p
                ON p.municipio_id = mu.id
            INNER JOIN mesas m
                ON m.puesto_id = p.id
            GROUP BY mu.id, mu.nombre
            ORDER BY mu.nombre;
            """
        )

        filas = cursor.fetchall()

    finally:
        conexion.close()

    if not filas:
        raise RuntimeError(
            "La consulta no devolvio informacion."
        )

    municipios = [fila[0].title() for fila in filas]
    potenciales = [int(fila[1] or 0) for fila in filas]
    votantes = [int(fila[2] or 0) for fila in filas]

    porcentajes = [
        (votante / potencial * 100) if potencial else 0
        for potencial, votante in zip(potenciales, votantes)
    ]

    figura, eje = plt.subplots(figsize=(11, 6))

    barras = eje.bar(
        municipios,
        porcentajes,
        edgecolor="black",
        linewidth=0.6,
    )

    eje.set_title(
        "Participaci\u00f3n electoral por municipio - Boyac\u00e1 2026",
        fontsize=15,
        fontweight="bold",
        pad=18,
    )

    eje.set_xlabel("Municipio")
    eje.set_ylabel("Participaci\u00f3n electoral (%)")
    eje.set_ylim(0, max(porcentajes) + 12)
    eje.grid(axis="y", alpha=0.25)

    for barra, porcentaje, votante, potencial in zip(
        barras,
        porcentajes,
        votantes,
        potenciales,
    ):
        eje.text(
            barra.get_x() + barra.get_width() / 2,
            barra.get_height() + 1,
            f"{porcentaje:.2f}%",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

        eje.text(
            barra.get_x() + barra.get_width() / 2,
            barra.get_height() / 2,
            f"{votante:,}\nde {potencial:,}",
            ha="center",
            va="center",
            fontsize=9,
        )

    figura.tight_layout()
    figura.savefig(
        OUTPUT_PATH,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(figura)

    print(f"Grafica generada: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()