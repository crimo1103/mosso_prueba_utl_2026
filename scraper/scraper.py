"""Scraper electoral Boyacá 2026.

Descarga el nomenclátor oficial, identifica los puestos de Tunja, Paipa,
Sogamoso y Duitama, genera los códigos de mesa a partir del número de mesas
reportado por cada puesto y consulta Cámara y Senado.
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
    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    adapter = HTTPAdapter(max_retries=retry)
    sesion.mount("https://", adapter)
    sesion.mount("http://", adapter)
    return sesion


def solicitar_json(session: requests.Session, url: str, timeout: int = 45) -> Any:
    logging.debug("GET %s", url)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def entero(valor: Any, default: int = 0) -> int:
    if valor in (None, ""):
        return default
    return int(str(valor).replace(".", "").replace(",", ""))


def nombre_candidato(item: dict[str, Any]) -> str:
    partes = [item.get("nomcan", ""), item.get("nomcan2", ""), item.get("apecan", ""), item.get("apecan2", "")]
    return " ".join(str(p).strip() for p in partes if str(p).strip())


def obtener_ambitos(nomenclator: dict[str, Any], corporacion: str) -> list[dict[str, Any]]:
    eleccion = 1 if corporacion == "SE" else 2
    for bloque in nomenclator.get("amb", []):
        if entero(bloque.get("elec")) == eleccion:
            return list(bloque.get("ambitos", []))
    raise ValueError(f"No se encontraron ámbitos para {corporacion}")


def ids_hijos(nodo: dict[str, Any]) -> list[int]:
    return [entero(i) for grupo in nodo.get("h", []) for i in grupo.get("p", [])]


def puestos_del_municipio(
    nomenclator: dict[str, Any], corporacion: str, municipio_codigo: str
) -> list[dict[str, Any]]:
    ambitos = obtener_ambitos(nomenclator, corporacion)
    nodos = {entero(n["i"]): n for n in ambitos}
    municipio = next(
        (n for n in ambitos if str(n.get("c")) == municipio_codigo and entero(n.get("l")) == 3),
        None,
    )
    if municipio is None:
        raise ValueError(f"Municipio {municipio_codigo} no hallado en nomenclátor")

    encontrados: dict[int, dict[str, Any]] = {}
    pendientes = ids_hijos(municipio)
    visitados: set[int] = set()

    while pendientes:
        nodo_id = pendientes.pop(0)
        if nodo_id in visitados:
            continue
        visitados.add(nodo_id)
        nodo = nodos.get(nodo_id)
        if nodo is None:
            continue
        if entero(nodo.get("l")) == 6:
            encontrados[nodo_id] = nodo
        else:
            pendientes.extend(ids_hijos(nodo))

    # Respaldo: algunos puestos no aparecen enlazados como hijos, pero su código
    # siempre inicia con el código municipal y tienen nivel 6.
    for nodo_id, nodo in nodos.items():
        if entero(nodo.get("l")) == 6 and str(nodo.get("c", "")).startswith(municipio_codigo):
            encontrados[nodo_id] = nodo

    return sorted(encontrados.values(), key=lambda n: str(n.get("c", "")))


def generar_mesas(puestos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mesas: list[dict[str, Any]] = []
    for puesto in puestos:
        codigo_puesto = str(puesto.get("c", "")).strip()
        cantidad = entero(puesto.get("m"), 0)
        if not codigo_puesto or cantidad <= 0:
            continue
        for numero in range(1, cantidad + 1):
            mesas.append(
                {
                    "numero": numero,
                    "codigo": f"{codigo_puesto}{numero:06d}",
                    "puesto": puesto,
                }
            )
    return mesas


def parsear_resultado_mesa(
    payload: dict[str, Any],
    municipio: Municipio,
    corporacion: str,
    mesa: dict[str, Any],
) -> list[dict[str, Any]]:
    puesto = mesa["puesto"]
    ambito = str(payload.get("amb") or mesa["codigo"])
    totales = payload.get("totales", {}).get("act", {})
    potencial = entero(totales.get("centota"), 0)
    total_votantes = entero(totales.get("votant"), 0)
    registros: list[dict[str, Any]] = []

    for camara in payload.get("camaras", []):
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
            votos_partido = entero(partido.get("vot"), 0)
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
                        "puesto_codigo": str(puesto.get("c", "")),
                        "puesto": str(puesto.get("n", "PUESTO NO IDENTIFICADO")),
                        "zona": str(puesto.get("c", ""))[7:9],
                        "direccion": None,
                        "total_mesas": entero(puesto.get("m"), 0),
                        "mesa": entero(mesa["numero"], 1),
                        "corporacion": corporacion,
                        "partido_codigo": codpar,
                        "partido": partido_nombre,
                        "candidato_codigo": codcan,
                        "candidato": nombre,
                        "votos": entero(candidato.get("vot"), 0),
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
            puestos = puestos_del_municipio(nomenclator, corporacion, municipio.codigo)
            mesas = generar_mesas(puestos)
            logging.info(
                "%s | %s | puestos=%s | mesas=%s",
                municipio.nombre,
                corporacion,
                len(puestos),
                len(mesas),
            )
            if not mesas:
                raise ValueError(f"No se encontraron mesas para {municipio.nombre} | {corporacion}")
            if preflight:
                continue

            for indice, mesa in enumerate(mesas, start=1):
                payload = solicitar_json(
                    session,
                    RESULTADO_URL.format(corporacion=corporacion, ambito=mesa["codigo"]),
                )
                registros.extend(parsear_resultado_mesa(payload, municipio, corporacion, mesa))
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
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = construir_parser().parse_args()
    configurar_logging(args.verbose)
    try:
        municipios = validar_municipios(args.municipios)
        registros = extraer_desde_api(crear_sesion(), municipios, args.preflight)
        if args.preflight:
            logging.info("Preflight completado: %s municipio(s)", len(municipios))
            return 0
        guardar_salida(registros)
        return 0
    except (requests.RequestException, ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        logging.exception("Error en scraper: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
