PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================
-- Catálogo de municipios
-- ============================================================
CREATE TABLE IF NOT EXISTS municipios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    departamento TEXT NOT NULL DEFAULT 'BOYACA',
    UNIQUE (codigo),
    UNIQUE (nombre)
);

-- ============================================================
-- Puestos de votación
-- ============================================================
CREATE TABLE IF NOT EXISTS puestos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    municipio_id INTEGER NOT NULL,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    zona TEXT,
    direccion TEXT,
    total_mesas INTEGER NOT NULL DEFAULT 0 CHECK (total_mesas >= 0),
    FOREIGN KEY (municipio_id) REFERENCES municipios(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (municipio_id, codigo)
);

-- ============================================================
-- Mesas de votación
-- ============================================================
CREATE TABLE IF NOT EXISTS mesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puesto_id INTEGER NOT NULL,
    numero INTEGER NOT NULL CHECK (numero > 0),
    potencial_sufragantes INTEGER CHECK (potencial_sufragantes IS NULL OR potencial_sufragantes >= 0),
    total_votantes INTEGER CHECK (total_votantes IS NULL OR total_votantes >= 0),
    FOREIGN KEY (puesto_id) REFERENCES puestos(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (puesto_id, numero)
);

-- ============================================================
-- Partidos y movimientos políticos
-- El mismo nombre normalizado puede tener códigos distintos según
-- la corporación (ej.: Alianza Verde CA=5 y SE=57), por lo que la
-- deduplicación técnica se realiza por código oficial.
-- ============================================================
CREATE TABLE IF NOT EXISTS partidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    nombre_normalizado TEXT NOT NULL,
    color_hex TEXT,
    UNIQUE (codigo)
);

-- ============================================================
-- Candidatos
-- ============================================================
CREATE TABLE IF NOT EXISTS candidatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partido_id INTEGER NOT NULL,
    corporacion TEXT NOT NULL CHECK (corporacion IN ('CA', 'SE')),
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    nombre_normalizado TEXT NOT NULL,
    FOREIGN KEY (partido_id) REFERENCES partidos(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (corporacion, partido_id, codigo),
    UNIQUE (corporacion, partido_id, nombre_normalizado)
);

-- ============================================================
-- Resultados electorales por mesa y candidato
-- ============================================================
CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa_id INTEGER NOT NULL,
    partido_id INTEGER NOT NULL,
    candidato_id INTEGER NOT NULL,
    corporacion TEXT NOT NULL CHECK (corporacion IN ('CA', 'SE')),
    votos INTEGER NOT NULL CHECK (votos >= 0),
    fuente TEXT NOT NULL DEFAULT 'API',
    fecha_extraccion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mesa_id) REFERENCES mesas(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (partido_id) REFERENCES partidos(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (candidato_id) REFERENCES candidatos(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (mesa_id, corporacion, partido_id, candidato_id)
);

-- ============================================================
-- Totales agregados de partido por mesa
-- Se conserva separado para validar contra la fuente y facilitar
-- consultas de dominancia y arrastre electoral.
-- ============================================================
CREATE TABLE IF NOT EXISTS resultados_partido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa_id INTEGER NOT NULL,
    partido_id INTEGER NOT NULL,
    corporacion TEXT NOT NULL CHECK (corporacion IN ('CA', 'SE')),
    votos INTEGER NOT NULL CHECK (votos >= 0),
    fuente TEXT NOT NULL DEFAULT 'API',
    fecha_extraccion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mesa_id) REFERENCES mesas(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (partido_id) REFERENCES partidos(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (mesa_id, corporacion, partido_id)
);

-- ============================================================
-- Registro de ejecuciones del pipeline ETL
-- ============================================================
CREATE TABLE IF NOT EXISTS carga_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proceso TEXT NOT NULL,
    inicio TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fin TEXT,
    estado TEXT NOT NULL DEFAULT 'INICIADO'
        CHECK (estado IN ('INICIADO', 'COMPLETADO', 'ERROR')),
    municipio TEXT,
    corporacion TEXT CHECK (corporacion IS NULL OR corporacion IN ('CA', 'SE')),
    filas_leidas INTEGER NOT NULL DEFAULT 0 CHECK (filas_leidas >= 0),
    filas_insertadas INTEGER NOT NULL DEFAULT 0 CHECK (filas_insertadas >= 0),
    filas_omitidas INTEGER NOT NULL DEFAULT 0 CHECK (filas_omitidas >= 0),
    mensaje TEXT
);

-- ============================================================
-- Índices para optimizar las consultas de la prueba
-- ============================================================

-- Optimiza agregaciones y filtros por corporación y partido.
CREATE INDEX IF NOT EXISTS idx_resultados_corporacion_partido
    ON resultados (corporacion, partido_id);

-- Optimiza consultas por mesa, necesarias para dominancia extrema.
CREATE INDEX IF NOT EXISTS idx_resultados_mesa_partido
    ON resultados (mesa_id, partido_id, corporacion);

-- Optimiza recorridos municipio -> puesto -> mesa.
CREATE INDEX IF NOT EXISTS idx_puestos_municipio
    ON puestos (municipio_id);

CREATE INDEX IF NOT EXISTS idx_mesas_puesto
    ON mesas (puesto_id);

-- Optimiza el cálculo de arrastre electoral por partido y corporación.
CREATE INDEX IF NOT EXISTS idx_resultados_partido_lookup
    ON resultados_partido (partido_id, corporacion, mesa_id);

-- Optimiza búsquedas por nombre normalizado durante el ETL.
CREATE INDEX IF NOT EXISTS idx_partidos_nombre_normalizado
    ON partidos (nombre_normalizado);

CREATE INDEX IF NOT EXISTS idx_candidatos_nombre_normalizado
    ON candidatos (nombre_normalizado);
