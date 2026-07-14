-- Tarea 3.3 — Atribución determinística
-- Top 5 candidatos CA según la votación atribuida desde Senado.
--
-- Fórmula:
-- A_ij = (votos_candidato_CA / votos_partido_CA) * votos_partido_SE
--
-- Homologaciones:
-- Alianza Verde: CA 5 -> SE 57
-- Pacto Histórico: CA 87 -> SE 92
-- Los demás partidos conservan su código.

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
        COALESCE(pse.votos_partido_se, 0) AS votos_partido_se,
        CASE
            WHEN pca.votos_partido_ca = 0 THEN 0
            ELSE
                CAST(cc.votos_candidato_ca AS REAL)
                / pca.votos_partido_ca
                * COALESCE(pse.votos_partido_se, 0)
        END AS atribucion_se
    FROM candidatos_ca cc
    INNER JOIN partidos_ca pca
        ON pca.codigo_partido_ca = cc.codigo_partido_ca
    LEFT JOIN partidos_se pse
        ON pse.codigo_partido_se = CASE
            WHEN cc.codigo_partido_ca = '5' THEN '57'
            WHEN cc.codigo_partido_ca = '87' THEN '92'
            ELSE cc.codigo_partido_ca
        END
),
clasificacion AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY
                atribucion_se DESC,
                votos_candidato_ca DESC,
                CAST(codigo_partido_ca AS INTEGER),
                CAST(codigo_candidato AS INTEGER),
                codigo_candidato
        ) AS posicion
    FROM atribucion
)
SELECT
    posicion,
    codigo_partido_ca,
    codigo_partido_se,
    partido,
    codigo_candidato,
    candidato,
    votos_candidato_ca,
    votos_partido_ca,
    votos_partido_se,
    ROUND(atribucion_se, 2) AS atribucion_se
FROM clasificacion
WHERE posicion <= 5
ORDER BY posicion;