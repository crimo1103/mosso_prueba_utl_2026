"""Pipeline ETL para la prueba técnica UTL Senado 2026.

Responsabilidades:
- Crear la base SQLite a partir de ``schema.sql``.
- Normalizar municipios, partidos y candidatos.
- Cargar registros electorales desde JSON.
- Evitar duplicados mediante restricciones UNIQUE e INSERT OR IGNORE.
- Registrar filas leídas, insertadas y omitidas en ``carga_log``.

El formato JSON esperado es una lista de objetos con esta forma mínima:
{
  "municipio_codigo": "15001",
  "municipio": "TUNJA",
  "puesto_codigo": "001",
  "puesto": "PUESTO EJEMPLO",
  "zona": "01",
  "direccion": "...",
  "mesa": 1,
  "corporacion": "CA",
  "partido_codigo": "5",
  "partido": "ALIANZA VERDE",
  "candidato_codigo": "101",
  "candidato": "NOMBRE CANDIDATO",
  "votos": 123,
  "votos_partido": 456,
  "potencial_sufragantes": 500,
  "total_votantes": 350,
  "fuente": "API"
}

Cuando se conozca la respuesta definitiva de la API, el scraper será responsable
de transformarla a este contrato estable antes de invocar el ETL.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "puestos_2026.db"
DEFAULT_SCHEMA_PATH = BASE_DIR / "schema.sql"

CORPORACIONES_VALIDAS = {"CA", "SE"}
COLORES_PARTIDO = {
    "5": "#007C34",
    "57": "#007C34",
    "87": "#7B2D8B",
    "92": "#7B2D8B",
    "10": "#1E477D",
    "2": "#E07B00",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("etl")


@dataclass
class EstadisticasCarga:
    leidas: int = 0
    insertadas: int = 0
    omitidas: int = 0


def limpiar_texto(valor: Any) -> str:
    """Convierte un valor a texto, elimina espacios redundantes y extremos."""
    if valor is None:
        return ""
    return " ".join(str(valor).strip().split())


def normalizar_texto(valor: Any) -> str:
    """Normaliza texto para deduplicación sin perder el valor original visible."""
    texto = limpiar_texto(valor).upper()
    texto_sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    )
    return texto_sin_tildes


def entero_no_negativo(valor: Any, campo: str, permite_nulo: bool = False) -> int | None:
    """Convierte a entero y valida que no sea negativo."""
    if valor in (None, "") and permite_nulo:
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{campo} debe ser un entero: {valor!r}") from exc
    if numero < 0:
        raise ValueError(f"{campo} no puede ser negativo: {numero}")
    return numero


def validar_registro(registro: dict[str, Any]) -> dict[str, Any]:
    """Valida y transforma un registro al contrato interno del ETL."""
    corporacion = normalizar_texto(registro.get("corporacion"))
    if corporacion not in CORPORACIONES_VALIDAS:
        raise ValueError(f"Corporación inválida: {corporacion!r}")

    municipio = normalizar_texto(registro.get("municipio"))
    puesto = limpiar_texto(registro.get("puesto"))
    partido = limpiar_texto(registro.get("partido"))
    candidato = limpiar_texto(registro.get("candidato"))

    obligatorios = {
        "municipio": municipio,
        "municipio_codigo": limpiar_texto(registro.get("municipio_codigo")),
        "puesto": puesto,
        "puesto_codigo": limpiar_texto(registro.get("puesto_codigo")),
        "partido": partido,
        "partido_codigo": limpiar_texto(registro.get("partido_codigo")),
        "candidato": candidato,
        "candidato_codigo": limpiar_texto(registro.get("candidato_codigo")),
    }
    faltantes = [campo for campo, valor in obligatorios.items() if not valor]
    if faltantes:
        raise ValueError(f"Campos obligatorios vacíos: {', '.join(faltantes)}")

    mesa = entero_no_negativo(registro.get("mesa"), "mesa")
    if mesa == 0:
        raise ValueError("mesa debe ser mayor que cero")

    return {
        "municipio_codigo": obligatorios["municipio_codigo"],
        "municipio": municipio,
        "puesto_codigo": obligatorios["puesto_codigo"],
        "puesto": puesto,
        "zona": limpiar_texto(registro.get("zona")) or None,
        "direccion": limpiar_texto(registro.get("direccion")) or None,
        "total_mesas": entero_no_negativo(registro.get("total_mesas", 0), "total_mesas"),
        "mesa": mesa,
        "potencial_sufragantes": entero_no_negativo(
            registro.get("potencial_sufragantes"),
            "potencial_sufragantes",
            permite_nulo=True,
        ),
        "total_votantes": entero_no_negativo(
            registro.get("total_votantes"), "total_votantes", permite_nulo=True
        ),
        "corporacion": corporacion,
        "partido_codigo": obligatorios["partido_codigo"],
        "partido": partido,
        "partido_normalizado": normalizar_texto(partido),
        "candidato_codigo": obligatorios["candidato_codigo"],
        "candidato": candidato,
        "candidato_normalizado": normalizar_texto(candidato),
        "votos": entero_no_negativo(registro.get("votos", 0), "votos"),
        "votos_partido": entero_no_negativo(
            registro.get("votos_partido"), "votos_partido", permite_nulo=True
        ),
        "fuente": limpiar_texto(registro.get("fuente")) or "API",
    }


def conectar(db_path: Path) -> sqlite3.Connection:
    """Abre SQLite con claves foráneas y filas accesibles por nombre."""
    conexion = sqlite3.connect(db_path)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA journal_mode = WAL")
    return conexion


def inicializar_base(
    db_path: Path = DEFAULT_DB_PATH, schema_path: Path = DEFAULT_SCHEMA_PATH
) -> None:
    """Crea la base y ejecuta el esquema de forma idempotente."""
    if not schema_path.exists():
        raise FileNotFoundError(f"No existe el esquema: {schema_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with conectar(db_path) as conexion:
        conexion.executescript(schema_path.read_text(encoding="utf-8"))
    LOGGER.info("Base inicializada: %s", db_path)


def obtener_o_crear_id(
    conexion: sqlite3.Connection,
    select_sql: str,
    select_params: tuple[Any, ...],
    insert_sql: str,
    insert_params: tuple[Any, ...],
) -> tuple[int, bool]:
    """Obtiene un ID o inserta el registro. Retorna (id, fue_insertado)."""
    fila = conexion.execute(select_sql, select_params).fetchone()
    if fila:
        return int(fila[0]), False

    cursor = conexion.execute(insert_sql, insert_params)
    return int(cursor.lastrowid), True


def cargar_registro(conexion: sqlite3.Connection, dato: dict[str, Any]) -> bool:
    """Carga un registro. Retorna True solo si se insertó el resultado principal."""
    municipio_id, _ = obtener_o_crear_id(
        conexion,
        "SELECT id FROM municipios WHERE codigo = ?",
        (dato["municipio_codigo"],),
        "INSERT INTO municipios (codigo, nombre) VALUES (?, ?)",
        (dato["municipio_codigo"], dato["municipio"]),
    )

    puesto_id, _ = obtener_o_crear_id(
        conexion,
        "SELECT id FROM puestos WHERE municipio_id = ? AND codigo = ?",
        (municipio_id, dato["puesto_codigo"]),
        """
        INSERT INTO puestos
            (municipio_id, codigo, nombre, zona, direccion, total_mesas)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            municipio_id,
            dato["puesto_codigo"],
            dato["puesto"],
            dato["zona"],
            dato["direccion"],
            dato["total_mesas"],
        ),
    )

    mesa_id, _ = obtener_o_crear_id(
        conexion,
        "SELECT id FROM mesas WHERE puesto_id = ? AND numero = ?",
        (puesto_id, dato["mesa"]),
        """
        INSERT INTO mesas
            (puesto_id, numero, potencial_sufragantes, total_votantes)
        VALUES (?, ?, ?, ?)
        """,
        (
            puesto_id,
            dato["mesa"],
            dato["potencial_sufragantes"],
            dato["total_votantes"],
        ),
    )

    partido_id, _ = obtener_o_crear_id(
        conexion,
        "SELECT id FROM partidos WHERE codigo = ?",
        (dato["partido_codigo"],),
        """
        INSERT INTO partidos (codigo, nombre, nombre_normalizado, color_hex)
        VALUES (?, ?, ?, ?)
        """,
        (
            dato["partido_codigo"],
            dato["partido"],
            dato["partido_normalizado"],
            COLORES_PARTIDO.get(dato["partido_codigo"]),
        ),
    )

    candidato_id, _ = obtener_o_crear_id(
        conexion,
        """
        SELECT id FROM candidatos
        WHERE corporacion = ? AND partido_id = ? AND codigo = ?
        """,
        (dato["corporacion"], partido_id, dato["candidato_codigo"]),
        """
        INSERT INTO candidatos
            (partido_id, corporacion, codigo, nombre, nombre_normalizado)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            partido_id,
            dato["corporacion"],
            dato["candidato_codigo"],
            dato["candidato"],
            dato["candidato_normalizado"],
        ),
    )

    cursor = conexion.execute(
        """
        INSERT OR IGNORE INTO resultados
            (mesa_id, partido_id, candidato_id, corporacion, votos, fuente)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            mesa_id,
            partido_id,
            candidato_id,
            dato["corporacion"],
            dato["votos"],
            dato["fuente"],
        ),
    )
    insertado = cursor.rowcount == 1

    if dato["votos_partido"] is not None:
        conexion.execute(
            """
            INSERT OR IGNORE INTO resultados_partido
                (mesa_id, partido_id, corporacion, votos, fuente)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                mesa_id,
                partido_id,
                dato["corporacion"],
                dato["votos_partido"],
                dato["fuente"],
            ),
        )

    return insertado


def registrar_inicio(
    conexion: sqlite3.Connection, proceso: str, municipio: str | None = None
) -> int:
    cursor = conexion.execute(
        "INSERT INTO carga_log (proceso, municipio) VALUES (?, ?)",
        (proceso, municipio),
    )
    return int(cursor.lastrowid)


def registrar_fin(
    conexion: sqlite3.Connection,
    log_id: int,
    estado: str,
    estadisticas: EstadisticasCarga,
    mensaje: str | None = None,
) -> None:
    conexion.execute(
        """
        UPDATE carga_log
        SET fin = CURRENT_TIMESTAMP,
            estado = ?,
            filas_leidas = ?,
            filas_insertadas = ?,
            filas_omitidas = ?,
            mensaje = ?
        WHERE id = ?
        """,
        (
            estado,
            estadisticas.leidas,
            estadisticas.insertadas,
            estadisticas.omitidas,
            mensaje,
            log_id,
        ),
    )


def iterar_json(path: Path) -> Iterator[dict[str, Any]]:
    """Lee una lista JSON o un objeto con clave ``resultados`` o ``data``."""
    contenido = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(contenido, list):
        registros = contenido
    elif isinstance(contenido, dict):
        registros = contenido.get("resultados", contenido.get("data"))
        if registros is None:
            registros = [contenido]
    else:
        raise ValueError("El JSON debe contener una lista u objeto")

    if not isinstance(registros, list):
        raise ValueError("La clave resultados/data debe ser una lista")

    for registro in registros:
        if not isinstance(registro, dict):
            raise ValueError("Cada registro del JSON debe ser un objeto")
        yield registro


def cargar_datos(
    registros: Iterable[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
    proceso: str = "ETL_JSON",
) -> EstadisticasCarga:
    """Valida, normaliza y carga registros en una transacción SQLite."""
    inicializar_base(db_path)
    estadisticas = EstadisticasCarga()

    with conectar(db_path) as conexion:
        log_id = registrar_inicio(conexion, proceso)
        try:
            for numero, registro in enumerate(registros, start=1):
                estadisticas.leidas += 1
                try:
                    dato = validar_registro(registro)
                    if cargar_registro(conexion, dato):
                        estadisticas.insertadas += 1
                    else:
                        estadisticas.omitidas += 1
                except Exception as exc:
                    raise ValueError(f"Error en registro {numero}: {exc}") from exc

            registrar_fin(conexion, log_id, "COMPLETADO", estadisticas)
            conexion.commit()
        except Exception as exc:
            conexion.rollback()
            # Se registra el error en una transacción independiente para conservar trazabilidad.
            with conectar(db_path) as conexion_error:
                error_log_id = registrar_inicio(conexion_error, proceso)
                registrar_fin(
                    conexion_error,
                    error_log_id,
                    "ERROR",
                    estadisticas,
                    str(exc),
                )
                conexion_error.commit()
            raise

    LOGGER.info(
        "ETL completado | leídas=%s | insertadas=%s | omitidas=%s",
        estadisticas.leidas,
        estadisticas.insertadas,
        estadisticas.omitidas,
    )
    return estadisticas


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETL electoral Boyacá 2026")
    parser.add_argument(
        "archivo",
        nargs="?",
        type=Path,
        help="Archivo JSON normalizado que se desea cargar",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Ruta de SQLite (por defecto: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Solo crea o valida la base de datos",
    )
    return parser


def main() -> int:
    args = construir_parser().parse_args()
    try:
        inicializar_base(args.db)
        if args.init_only:
            return 0
        if args.archivo is None:
            raise ValueError("Debe indicar un archivo JSON o usar --init-only")
        if not args.archivo.exists():
            raise FileNotFoundError(f"No existe el archivo: {args.archivo}")
        cargar_datos(iterar_json(args.archivo), args.db)
        return 0
    except Exception as exc:
        LOGGER.error("ETL falló: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
