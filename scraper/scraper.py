"""Scraper electoral Boyacá 2026.

Descarga el nomenclátor oficial y recorre sus ámbitos hasta nivel mesa para
Tunja, Paipa, Sogamoso y Duitama. Para cada mesa consulta Cámara y Senado,
normaliza la respuesta y genera el contrato consumido por ``db/etl.py``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://resultadospreccongreso2026.registraduria.gov.co"
NOMENCLATOR_URL = f"{BASE_URL}/json/nomenclator.json"
RESULTADO_URL = f"{BASE_URL}/json/ACT/{{corporacion}}/{{ambito}}.json"
DEFAULT_MUNICIPIOS = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]
CORPORACIONES = ("CA", "SE")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "sample_data"
OUTPUT_FILE = RAW_DIR / "resultados_normalizados.json"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
    "Referer": f"{BASE_URL}/",
}

PARTIDOS = {
    "2": "PARTIDO CONSERVADOR COLOMBIANO",
    "5": "ALIANZA VERDE",
    "10": "CENTRO DEMOCRATICO",
    "57": "ALIANZA VERDE",
    "87": "PACTO HISTORICO",
    "92": "PACTO HISTORICO",
}


@dataclass(frozen=True)
class Municipio:
    nombre: str
    codigo: str


MUNICIPIOS = {
    "TUNJA": Municipio("TUNJA", "0700001"),
    "PAIPA": Municipio("PAIPA", "0700181"),
    "SOGAMOSO": Municipio("SOGAMOSO", "0700277"),
    "DUITAMA": Municipio("DUITAMA", "0700079"),
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
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def solicitar_json(session: requests.Session, url: str, timeout: int = 45) -> Any:
    logging.debug("GET %s", url)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    try:
        return response.json()
    except requests.JSONDecodeError as exc:
        raise ValueError(f"Respuesta no JSON: {response.url}") from exc


def entero(valor: Any, default: int = 0) -> int:
    if valor in (None, ""):
        return default
    return int(str(valor).replace(".", "").replace(",", ""))


def nombre_candidato(item: dict[str, Any]) -> str:
    partes = [
        item.get("nomcan", ""),
        item.get("nomcan2", ""),
        item.get("apecan", ""),
        item.get("apecan2", ""),
    ]
    return " ".join(str(p).strip() for p in partes if str(p).strip())


def obtener_ambitos(nomenclator: dict[str, Any], corporacion: str) -> list[dict[str, Any]]:
    eleccion = 1 if corporacion == "SE" else 2
    for bloque in nomenclator.get("amb", []):
        if entero(bloque.get("elec")) == eleccion:
            return list(bloque.get("ambitos", []))
    raise ValueError(f"No se encontraron ámbitos para {corporacion}")


def es_descendiente(
    node_id: int,
    ancestor_id: int,
    nodos: dict[int, dict[str, Any]],
    memo: dict[tuple[int, int], bool],
) -> bool:
    clave = (node_id, ancestor_id)
    if clave in memo:
        return memo[clave]
    if node_id == ancestor_id:
        memo[clave] = True
        return True
    nodo = nodos[node_id]
    padres = [pid for grupo in nodo.get("p", []) for pid in grupo.get("p", [])]
    resultado = any(
        pid in nodos and es_descendiente(pid, ancestor_id, nodos, memo)
        for pid in padres
    )
    memo[clave] = resultado
    return resultado


def mesas_del_municipio(
    nomenclator: dict[str, Any], corporacion: str, municipio_codigo: str
) -> list[dict[str, Any]]:
    ambitos = obtener_ambitos(nomenclator, corporacion)
    nodos = {entero(n["i"]): n for n in ambitos}
    municipio = next(
        (n for n in ambitos if n.get("c") == municipio_codigo and entero(n.get("l")) == 3),
        None,
    )
    if municipio is None:
        raise ValueError(f"Municipio {municipio_codigo} no hallado en nomenclátor")

    municipio_id = entero(municipio["i"])
    memo: dict[tuple[int, int], bool] = {}
    mesas = [
        n
        for n in ambitos
        if entero(n.get("l")) == 7
        and es_descendiente(entero(n["i"]), municipio_id, nodos, memo)
    ]
    return sorted(mesas, key=lambda n: str(n.get("c", "")))


def ancestro_nivel(
    nodo: dict[str, Any], nivel: int, nodos: dict[int, dict[str, Any]]
) -> dict[str, Any] | None:
    visitados: set[int] = set()
    pendientes = [pid for grupo in nodo.get("p", []) for pid in grupo.get("p", [])]
    while pendientes:
        actual_id = pendientes.pop(0)
        if actual_id in visitados or actual_id not in nodos:
            continue
        visitados.add(actual_id)
        actual = nodos[actual_id]
        if entero(actual.get("l")) == nivel:
            return actual
        pendientes.extend(
            pid for grupo in actual.get("p", []) for pid in grupo.get("p", [])
        )
    return None


def parsear_resultado_mesa(
    payload: dict[str, Any],
    municipio: Municipio,
    corporacion: str,
    mesa_nodo: dict[str, Any],
    nodos: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    puesto = ancestro_nivel(mesa_nodo, 6, nodos)
    zona = ancestro_nivel(mesa_nodo, 4, nodos)
    ambito = str(payload.get("amb") or mesa_nodo.get("c"))
    mesa_numero = entero(str(mesa_nodo.get("n", "")).split()[-1], default=0)
    if mesa_numero <= 0:
        mesa_numero = entero(ambito[-6:], default=1)

    totales = payload.get("totales", {}).get("act", {})
    potencial = entero(totales.get("centota"), default=0)
    total_votantes = entero(totales.get("votant"), default=0)
    registros: list[dict[str, Any]] = []

    for camara in payload.get("camaras", []):
        # Cámara territorial=1 y Senado nacional=0. Se omiten circunscripciones
        # especiales para mantener comparabilidad en los retos analíticos.
        cam = str(camara.get("cam", ""))
        if corporacion == "CA" and cam != "1":
            continue
        if corporacion == "SE" and cam != "0":
            continue

        for partido_wrap in camara.get("partotabla", []):
            partido = partido_wrap.get("act", {})
            codpar = str(partido.get("codpar", "")).strip()
            if not codpar:
                continue
            votos_partido = entero(partido.get("vot"))
            partido_nombre = PARTIDOS.get(codpar, f"PARTIDO {codpar}")

            for candidato in partido.get("cantotabla", []):
                codcan = str(candidato.get("codcan", "")).strip()
                nombre = nombre_candidato(candidato)
                if not codcan or not nombre:
                    continue
                registros.append(
                    {
                        "municipio_codigo": municipio.codigo,
                        "municipio": municipio.nombre,
                        "puesto_codigo": str((puesto or {}).get("c", "SIN-PUESTO")),
                        "puesto": str((puesto or {}).get("n", "PUESTO NO IDENTIFICADO")),
                        "zona": str((zona or {}).get("n", "")),
                        "direccion": None,
                        "total_mesas": 0,
                        "mesa": mesa_numero,
                        "corporacion": corporacion,
                        "partido_codigo": codpar,
                        "partido": partido_nombre,
                        "candidato_codigo": codcan,
                        "candidato": nombre,
                        "votos": entero(candidato.get("vot")),
                        "votos_partido": votos_partido,
                        "potencial_sufragantes": potencial,
                        "total_votantes": total_votantes,
                        "fuente": f"API:{ambito}",
                    }
                )
    return registros


def extraer_desde_api(
    session: requests.Session, municipios: Iterable[str], preflight: bool
) -> list[dict[str, Any]]:
    nomenclator = solicitar_json(session, NOMENCLATOR_URL)
    registros: list[dict[str, Any]] = []

    for nombre_municipio in municipios:
        municipio = MUNICIPIOS[nombre_municipio]
        for corporacion in CORPORACIONES:
            ambitos = obtener_ambitos(nomenclator, corporacion)
            nodos = {entero(n["i"]): n for n in ambitos}
            mesas = mesas_del_municipio(nomenclator, corporacion, municipio.codigo)
            logging.info("%s | %s | mesas=%s", municipio.nombre, corporacion, len(mesas))
            if preflight:
                continue

            for indice, mesa in enumerate(mesas, start=1):
                ambito = str(mesa.get("c", ""))
                if not ambito:
                    continue
                payload = solicitar_json(
                    session,
                    RESULTADO_URL.format(corporacion=corporacion, ambito=ambito),
                )
                registros.extend(
                    parsear_resultado_mesa(payload, municipio, corporacion, mesa, nodos)
                )
                if indice % 25 == 0 or indice == len(mesas):
                    logging.info(
                        "%s | %s | progreso=%s/%s | filas=%s",
                        municipio.nombre,
                        corporacion,
                        indice,
                        len(mesas),
                        len(registros),
                    )
    return registros


def cargar_sample_data(municipios: Iterable[str]) -> list[dict[str, Any]]:
    if not SAMPLE_DIR.exists():
        raise FileNotFoundError("No existe sample_data/")
    solicitados = {m.upper() for m in municipios}
    registros: list[dict[str, Any]] = []
    for archivo in sorted(SAMPLE_DIR.glob("*.json")):
        contenido = json.loads(archivo.read_text(encoding="utf-8"))
        items = contenido if isinstance(contenido, list) else contenido.get("registros", [])
        registros.extend(
            item for item in items if str(item.get("municipio", "")).upper() in solicitados
        )
    if not registros:
        raise ValueError("sample_data/ no contiene registros compatibles")
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
        raise ValueError(f"Municipios no soportados: {invalidos}")
    return list(dict.fromkeys(resultado))


def guardar_salida(registros: list[dict[str, Any]], destino: Path = OUTPUT_FILE) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    temporal.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(destino)
    logging.info("Salida guardada: %s | filas=%s", destino, len(registros))


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extrae resultados electorales Boyacá 2026")
    parser.add_argument("--municipios", nargs="+", default=DEFAULT_MUNICIPIOS)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--sample-data", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = construir_parser().parse_args()
    configurar_logging(args.verbose)
    try:
        municipios = validar_municipios(args.municipios)
        if args.sample_data:
            registros = cargar_sample_data(municipios)
        else:
            registros = extraer_desde_api(crear_sesion(), municipios, args.preflight)
        if args.preflight:
            logging.info("Preflight completado: %s municipio(s)", len(municipios))
            return 0
        guardar_salida(registros)
        return 0
    except (requests.RequestException, ValueError, FileNotFoundError, KeyError) as exc:
        logging.exception("Error en scraper: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
