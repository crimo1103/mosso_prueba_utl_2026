"""Exporta información resumida desde SQLite para el dashboard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "puestos_2026.db"
OUTPUT_PATH = Path(__file__).resolve().parent / "data.json"


def consultar(
    conexion: sqlite3.Connection,
    sql: str,
    parametros: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    """Ejecuta una consulta y devuelve filas como diccionarios."""
    cursor = conexion.execute(sql, parametros)
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró la base de datos: {DB_PATH}"
        )

    conexion = sqlite3.connect(DB_PATH)

    try:
        resumen_municipios = consultar(
            conexion,
            """
            SELECT
                mu.nombre AS municipio,
                COUNT(DISTINCT p.id) AS puestos,
                COUNT(DISTINCT m.id) AS mesas,
                SUM(COALESCE(m.potencial_sufragantes, 0))
                    AS potencial_sufragantes,
                SUM(COALESCE(m.total_votantes, 0))
                    AS total_votantes
            FROM municipios mu
            INNER JOIN puestos p
                ON p.municipio_id = mu.id
            INNER JOIN mesas m
                ON m.puesto_id = p.id
            GROUP BY mu.id, mu.nombre
            ORDER BY mu.nombre;
            """,
        )

        votos_por_municipio = consultar(
            conexion,
            """
            SELECT
                mu.nombre AS municipio,
                rp.corporacion,
                SUM(rp.votos) AS votos
            FROM resultados_partido rp
            INNER JOIN mesas m
                ON m.id = rp.mesa_id
            INNER JOIN puestos p
                ON p.id = m.puesto_id
            INNER JOIN municipios mu
                ON mu.id = p.municipio_id
            GROUP BY mu.nombre, rp.corporacion
            ORDER BY mu.nombre, rp.corporacion;
            """,
        )

        top_partidos = consultar(
            conexion,
            """
            WITH votos AS (
                SELECT
                    mu.nombre AS municipio,
                    rp.corporacion,
                    pa.codigo AS codigo_partido,
                    pa.nombre AS partido,
                    pa.color_hex,
                    SUM(rp.votos) AS votos
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                INNER JOIN municipios mu
                    ON mu.id = p.municipio_id
                GROUP BY
                    mu.nombre,
                    rp.corporacion,
                    pa.codigo,
                    pa.nombre,
                    pa.color_hex
            ),
            clasificacion AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY municipio, corporacion
                        ORDER BY votos DESC, codigo_partido
                    ) AS posicion
                FROM votos
            )
            SELECT
                municipio,
                corporacion,
                codigo_partido,
                partido,
                color_hex,
                votos,
                posicion
            FROM clasificacion
            WHERE posicion <= 5
            ORDER BY municipio, corporacion, posicion;
            """,
        )

        alianza_verde = consultar(
            conexion,
            """
            WITH camara AS (
                SELECT
                    p.id AS puesto_id,
                    SUM(rp.votos) AS votos_camara
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                WHERE rp.corporacion = 'CA'
                  AND pa.codigo = '5'
                GROUP BY p.id
            ),
            senado AS (
                SELECT
                    p.id AS puesto_id,
                    SUM(rp.votos) AS votos_senado
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                INNER JOIN mesas m
                    ON m.id = rp.mesa_id
                INNER JOIN puestos p
                    ON p.id = m.puesto_id
                WHERE rp.corporacion = 'SE'
                  AND pa.codigo = '57'
                GROUP BY p.id
            )
            SELECT
                mu.nombre AS municipio,
                p.codigo AS codigo_puesto,
                p.nombre AS puesto,
                COALESCE(c.votos_camara, 0) AS votos_camara,
                COALESCE(s.votos_senado, 0) AS votos_senado,
                ROUND(
                    CASE
                        WHEN COALESCE(c.votos_camara, 0) = 0 THEN NULL
                        ELSE CAST(s.votos_senado AS REAL)
                             / c.votos_camara
                    END,
                    4
                ) AS razon_senado_camara
            FROM puestos p
            INNER JOIN municipios mu
                ON mu.id = p.municipio_id
            LEFT JOIN camara c
                ON c.puesto_id = p.id
            LEFT JOIN senado s
                ON s.puesto_id = p.id
            ORDER BY
                mu.nombre,
                razon_senado_camara DESC,
                p.codigo;
            """,
        )

        dominancia = consultar(
            conexion,
            """
            SELECT
                mu.nombre AS municipio,
                p.codigo AS codigo_puesto,
                p.nombre AS puesto,
                m.numero AS mesa,
                r.corporacion,
                pa.codigo AS codigo_partido,
                pa.nombre AS partido,
                c.codigo AS codigo_candidato,
                c.nombre AS candidato,
                r.votos AS votos_candidato,
                rp.votos AS votos_partido,
                ROUND(
                    CAST(r.votos AS REAL)
                    / NULLIF(rp.votos, 0)
                    * 100,
                    2
                ) AS porcentaje
            FROM resultados r
            INNER JOIN candidatos c
                ON c.id = r.candidato_id
            INNER JOIN partidos pa
                ON pa.id = r.partido_id
            INNER JOIN resultados_partido rp
                ON rp.mesa_id = r.mesa_id
               AND rp.partido_id = r.partido_id
               AND rp.corporacion = r.corporacion
            INNER JOIN mesas m
                ON m.id = r.mesa_id
            INNER JOIN puestos p
                ON p.id = m.puesto_id
            INNER JOIN municipios mu
                ON mu.id = p.municipio_id
            WHERE c.codigo <> '0'
              AND UPPER(c.nombre) <> 'SOLO POR LA LISTA'
              AND CAST(r.votos AS REAL)
                  / NULLIF(rp.votos, 0) > 0.60
            ORDER BY
                porcentaje DESC,
                municipio,
                codigo_puesto,
                mesa
            LIMIT 250;
            """,
        )

        top_atribucion = consultar(
            conexion,
            """
            WITH candidatos_ca AS (
                SELECT
                    pa.codigo AS codigo_partido_ca,
                    pa.nombre AS partido,
                    c.codigo AS codigo_candidato,
                    c.nombre AS candidato,
                    SUM(r.votos) AS votos_candidato_ca
                FROM resultados r
                INNER JOIN candidatos c
                    ON c.id = r.candidato_id
                INNER JOIN partidos pa
                    ON pa.id = r.partido_id
                WHERE r.corporacion = 'CA'
                  AND c.codigo <> '0'
                  AND UPPER(c.nombre) <> 'SOLO POR LA LISTA'
                GROUP BY
                    pa.codigo,
                    pa.nombre,
                    c.codigo,
                    c.nombre
            ),
            partidos_ca AS (
                SELECT
                    pa.codigo AS codigo_partido_ca,
                    SUM(rp.votos) AS votos_partido_ca
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                WHERE rp.corporacion = 'CA'
                GROUP BY pa.codigo
            ),
            partidos_se AS (
                SELECT
                    pa.codigo AS codigo_partido_se,
                    SUM(rp.votos) AS votos_partido_se
                FROM resultados_partido rp
                INNER JOIN partidos pa
                    ON pa.id = rp.partido_id
                WHERE rp.corporacion = 'SE'
                GROUP BY pa.codigo
            ),
            atribucion AS (
                SELECT
                    cc.codigo_partido_ca,
                    CASE
                        WHEN cc.codigo_partido_ca = '5' THEN '57'
                        WHEN cc.codigo_partido_ca = '87' THEN '92'
                        ELSE cc.codigo_partido_ca
                    END AS codigo_partido_se,
                    cc.partido,
                    cc.codigo_candidato,
                    cc.candidato,
                    cc.votos_candidato_ca,
                    pca.votos_partido_ca,
                    COALESCE(pse.votos_partido_se, 0)
                        AS votos_partido_se,
                    CASE
                        WHEN pca.votos_partido_ca = 0 THEN 0
                        ELSE
                            CAST(cc.votos_candidato_ca AS REAL)
                            / pca.votos_partido_ca
                            * COALESCE(pse.votos_partido_se, 0)
                    END AS atribucion_se
                FROM candidatos_ca cc
                INNER JOIN partidos_ca pca
                    ON pca.codigo_partido_ca =
                       cc.codigo_partido_ca
                LEFT JOIN partidos_se pse
                    ON pse.codigo_partido_se = CASE
                        WHEN cc.codigo_partido_ca = '5' THEN '57'
                        WHEN cc.codigo_partido_ca = '87' THEN '92'
                        ELSE cc.codigo_partido_ca
                    END
            )
            SELECT
                codigo_partido_ca,
                codigo_partido_se,
                partido,
                codigo_candidato,
                candidato,
                votos_candidato_ca,
                votos_partido_ca,
                votos_partido_se,
                ROUND(atribucion_se, 2) AS atribucion_se
            FROM atribucion
            ORDER BY
                atribucion_se DESC,
                votos_candidato_ca DESC,
                codigo_partido_ca,
                codigo_candidato
            LIMIT 5;
            """,
        )

        datos = {
            "titulo": "Resultados electorales Boyacá 2026",
            "municipios": [
                "TUNJA",
                "PAIPA",
                "SOGAMOSO",
                "DUITAMA",
            ],
            "resumen_municipios": resumen_municipios,
            "votos_por_municipio": votos_por_municipio,
            "top_partidos": top_partidos,
            "alianza_verde": alianza_verde,
            "dominancia_60": dominancia,
            "top_atribucion": top_atribucion,
        }

        OUTPUT_PATH.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"Archivo generado: {OUTPUT_PATH}")
        print(
            "Municipios exportados:",
            len(resumen_municipios),
        )
        print(
            "Puestos Alianza Verde:",
            len(alianza_verde),
        )
        print(
            "Casos de dominancia exportados:",
            len(dominancia),
        )

    finally:
        conexion.close()


if __name__ == "__main__":
    main()