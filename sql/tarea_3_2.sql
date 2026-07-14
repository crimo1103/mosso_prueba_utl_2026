-- Tarea 3.2
-- Candidatos que obtienen más del 60 % de los votos de su partido
-- en una mesa determinada.

WITH votos_candidato_mesa AS (
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
        rp.votos AS votos_partido
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
)
SELECT
    municipio,
    codigo_puesto,
    puesto,
    mesa,
    corporacion,
    codigo_partido,
    partido,
    codigo_candidato,
    candidato,
    votos_candidato,
    votos_partido,
    ROUND(
        CAST(votos_candidato AS REAL)
        / NULLIF(votos_partido, 0)
        * 100,
        2
    ) AS porcentaje_partido
FROM votos_candidato_mesa
WHERE
    CAST(votos_candidato AS REAL)
    / NULLIF(votos_partido, 0) > 0.60
ORDER BY
    porcentaje_partido DESC,
    municipio,
    codigo_puesto,
    mesa,
    corporacion,
    codigo_partido,
    codigo_candidato;