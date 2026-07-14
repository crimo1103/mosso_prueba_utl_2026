-- Tarea 3.1
-- Comparación de Alianza Verde por puesto:
-- Cámara código 5 frente a Senado código 57.
-- Razón solicitada: votos Senado / votos Cámara.

WITH votos_camara AS (
    SELECT
        p.id AS puesto_id,
        SUM(rp.votos) AS votos_verde_camara
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
votos_senado AS (
    SELECT
        p.id AS puesto_id,
        SUM(rp.votos) AS votos_verde_senado
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
    COALESCE(vc.votos_verde_camara, 0) AS votos_verde_camara,
    COALESCE(vs.votos_verde_senado, 0) AS votos_verde_senado,
    ROUND(
        CASE
            WHEN COALESCE(vc.votos_verde_camara, 0) = 0 THEN NULL
            ELSE
                CAST(COALESCE(vs.votos_verde_senado, 0) AS REAL)
                / vc.votos_verde_camara
        END,
        4
    ) AS razon_senado_camara
FROM puestos p
INNER JOIN municipios mu
    ON mu.id = p.municipio_id
LEFT JOIN votos_camara vc
    ON vc.puesto_id = p.id
LEFT JOIN votos_senado vs
    ON vs.puesto_id = p.id
ORDER BY
    mu.nombre,
    razon_senado_camara DESC,
    p.codigo;