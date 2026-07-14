"""Genera una grafica comparativa de Alianza Verde por municipio."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "puestos_2026.db"
OUTPUT_PATH = ROOT / "viz" / "comparacion_verde.png"


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No se encontro la base de datos: {DB_PATH}"
        )

    conexion = sqlite3.connect(DB_PATH)

    try:
        cursor = conexion.execute(
            """
            WITH camara AS (
                SELECT
                    mu.nombre AS municipio,
                    SUM(rp.votos) AS votos_camara
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                WHERE rp.corporacion = 'CA'
                  AND pa.codigo = '5'
                GROUP BY mu.nombre
            ),
            senado AS (
                SELECT
                    mu.nombre AS municipio,
                    SUM(rp.votos) AS votos_senado
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                WHERE rp.corporacion = 'SE'
                  AND pa.codigo = '57'
                GROUP BY mu.nombre
            )
            SELECT
                mu.nombre AS municipio,
                COALESCE(c.votos_camara, 0) AS votos_camara,
                COALESCE(s.votos_senado, 0) AS votos_senado
            FROM municipios mu
            LEFT JOIN camara c
                ON c.municipio = mu.nombre
            LEFT JOIN senado s
                ON s.municipio = mu.nombre
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
    votos_camara = [int(fila[1] or 0) for fila in filas]
    votos_senado = [int(fila[2] or 0) for fila in filas]

    posiciones = list(range(len(municipios)))
    ancho = 0.36

    figura, eje = plt.subplots(figsize=(11, 6))

    barras_camara = eje.bar(
        [posicion - ancho / 2 for posicion in posiciones],
        votos_camara,
        width=ancho,
        label="Camara - codigo 5",
        edgecolor="black",
        linewidth=0.5,
    )

    barras_senado = eje.bar(
        [posicion + ancho / 2 for posicion in posiciones],
        votos_senado,
        width=ancho,
        label="Senado - codigo 57",
        edgecolor="black",
        linewidth=0.5,
    )

    eje.set_title(
        "Comparacion Alianza Verde por municipio - Boyaca 2026",
        fontsize=15,
        fontweight="bold",
        pad=18,
    )

    eje.set_xlabel("Municipio")
    eje.set_ylabel("Numero de votos")
    eje.set_xticks(posiciones)
    eje.set_xticklabels(municipios)
    eje.legend()
    eje.grid(axis="y", alpha=0.25)

    maximo = max(votos_camara + votos_senado)
    eje.set_ylim(0, maximo * 1.18 if maximo else 1)

    for barras in (barras_camara, barras_senado):
        for barra in barras:
            altura = barra.get_height()

            eje.text(
                barra.get_x() + barra.get_width() / 2,
                altura + maximo * 0.02,
                f"{int(altura):,}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
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