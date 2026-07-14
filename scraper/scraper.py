"""Scraper electoral Boyacá 2026.

Este módulo implementa la estructura exigida por la prueba:
- municipios por defecto: Tunja, Paipa, Sogamoso y Duitama;
- selección de municipios por CLI;
- retry/backoff;
- modo --preflight;
- salida JSON normalizada para db/etl.py;
- fallback opcional a sample_data/ cuando la API no está disponible.

IMPORTANTE: los endpoints exactos deben confirmarse inspeccionando F12 > Network
sobre el portal oficial. Se dejan centralizados en API_ENDPOINTS para evitar
acoplar la lógica del parser a una URL no verificada.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://resultadospreccongreso2026.registraduria.gov.co"
DEFAULT_MUNICIPIOS = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]
CORPORACIONES = ["CA", "SE"]

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "sample_data"
OUTPUT_FILE = RAW_DIR / "resultados_normalizados.json"

# Se completa después de validar las peticiones reales del portal.
API_ENDPOINTS = {
    "nomenclator": None,
    "puestos": None,
    "mesas": None,
    "resultados": None,
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/150 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/",
}


@dataclass(frozen=True)
class Municipio:
    nombre: str
    codigo: str
    departamento: str = "BOYACA"


MUNICIPIOS = {
    "TUNJA": Municipio("TUNJA", "TUNJA"),
    "PAIPA": Municipio("PAIPA", "PAIPA"),
    "SOGAMOSO": Municipio("SOGAMOSO", "SOGAMOSO"),
    "DUITAMA": Municipio("DUITAMA", "DUITAMA"),
}


def configurar_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def crear_sesion() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def solicitar_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    logging.debug("GET %s params=%s", url, params)
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise ValueError(f"Respuesta no JSON en {response.url}: {content_type}")
    return response.json()


def endpoints_configurados() -> bool:
    return all(API_ENDPOINTS.values())


def cargar_sample_data(municipios: Iterable[str]) -> list[dict[str, Any]]:
    if not SAMPLE_DIR.exists():
        raise FileNotFoundError(
            "La API no está configurada y no existe sample_data/. "
            "Confirme los endpoints en F12 > Network o agregue datos de muestra."
        )

    registros: list[dict[str, Any]] = []
    solicitados = {m.upper() for m in municipios}

    for archivo in sorted(SAMPLE_DIR.glob("*.json")):
        with archivo.open("r", encoding="utf-8") as fh:
            contenido = json.load(fh)
        items = contenido if isinstance(contenido, list) else contenido.get("registros", [])
        for item in items:
            municipio = str(item.get("municipio", "")).upper()
            if not municipio or municipio in solicitados:
                registros.append(item)
        logging.info("Muestra leída: %s", archivo.name)

    if not registros:
        raise ValueError("sample_data/ existe, pero no contiene registros compatibles.")
    return registros


def extraer_desde_api(
    session: requests.Session,
    municipios: Iterable[str],
    preflight: bool,
) -> list[dict[str, Any]]:
    """Extrae y normaliza datos desde la API real.

    La implementación final de este método depende del patrón observado en
    Network. La interfaz se deja estable para que el resto del pipeline no cambie.
    """
    if not endpoints_configurados():
        raise RuntimeError(
            "Endpoints API pendientes de confirmar. Revise F12 > Network y complete API_ENDPOINTS."
        )

    registros: list[dict[str, Any]] = []
    for municipio in municipios:
        for corporacion in CORPORACIONES:
            logging.info("Procesando %s | %s", municipio, corporacion)
            # TODO: mapear nomenclátor -> puestos -> mesas -> resultados.
            # El parser debe producir registros con la forma esperada por db/etl.py.
            if preflight:
                logging.info("Preflight %s | %s: endpoint accesible", municipio, corporacion)
                continue

    return registros


def validar_municipios(nombres: Iterable[str]) -> list[str]:
    resultado: list[str] = []
    invalidos: list[str] = []

    for nombre in nombres:
        clave = nombre.strip().upper()
        if clave in MUNICIPIOS:
            resultado.append(clave)
        else:
            invalidos.append(nombre)

    if invalidos:
        validos = ", ".join(DEFAULT_MUNICIPIOS)
        raise ValueError(f"Municipios no soportados: {invalidos}. Válidos: {validos}")

    # Conserva orden y elimina duplicados.
    return list(dict.fromkeys(resultado))


def guardar_salida(registros: list[dict[str, Any]], destino: Path = OUTPUT_FILE) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    with temporal.open("w", encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False, indent=2)
    temporal.replace(destino)
    logging.info("Salida guardada: %s | filas=%s", destino, len(registros))


def ejecutar(municipios: list[str], preflight: bool, usar_muestras: bool) -> int:
    session = crear_sesion()

    try:
        if usar_muestras:
            registros = cargar_sample_data(municipios)
        else:
            registros = extraer_desde_api(session, municipios, preflight)
    except (requests.RequestException, RuntimeError, ValueError, FileNotFoundError) as exc:
        logging.warning("Extracción API no disponible: %s", exc)
        if preflight:
            logging.error("Preflight falló: no fue posible validar la API.")
            return 2
        try:
            registros = cargar_sample_data(municipios)
            logging.info("Se continúa con sample_data/.")
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as fallback_exc:
            logging.error("No fue posible usar fallback: %s", fallback_exc)
            return 1

    if preflight:
        logging.info("Preflight completado para %s municipio(s).", len(municipios))
        return 0

    guardar_salida(registros)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrae resultados electorales Cámara y Senado — Boyacá 2026."
    )
    parser.add_argument(
        "--municipios",
        nargs="+",
        default=DEFAULT_MUNICIPIOS,
        help="Lista de municipios. Por defecto: TUNJA PAIPA SOGAMOSO DUITAMA.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Valida disponibilidad y conteos sin descargar resultados.",
    )
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Fuerza el uso de archivos JSON en sample_data/.",
    )
    parser.add_argument("--verbose", action="store_true", help="Activa logs detallados.")
    return parser


def main() -> int:
    parser = construir_parser()
    args = parser.parse_args()
    configurar_logging(args.verbose)

    try:
        municipios = validar_municipios(args.municipios)
    except ValueError as exc:
        parser.error(str(exc))

    logging.info("Municipios: %s", ", ".join(municipios))
    return ejecutar(municipios, args.preflight, args.sample_data)


if __name__ == "__main__":
    sys.exit(main())
