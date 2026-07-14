"""Genera el manifiesto de evaluación del proyecto."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = ROOT / "outputs" / "evaluation_manifest.json"
EXAMPLE_PATH = ROOT / "outputs" / "evaluation_manifest.example.json"


ARCHIVOS_REQUERIDOS = [
    "README.md",
    "requirements.txt",
    "scraper/scraper.py",
    "db/schema.sql",
    "db/etl.py",
    "sql/tarea_3_1.sql",
    "sql/tarea_3_2.sql",
    "sql/tarea_3_3.sql",
    "dashboard/export_data.py",
    "dashboard/data.json",
    "dashboard/index.html",
    "viz/participacion_municipio.py",
    "viz/participacion_municipio.png",
    "viz/comparacion_verde.py",
    "viz/comparacion_verde.png",
    "outputs/generar_manifest.py",
]


def calcular_sha256(ruta: Path) -> str | None:
    """Calcula el hash SHA-256 de un archivo."""
    if not ruta.exists() or not ruta.is_file():
        return None

    hash_archivo = hashlib.sha256()

    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            hash_archivo.update(bloque)

    return hash_archivo.hexdigest()


def obtener_informacion_archivo(
    ruta_relativa: str,
) -> dict[str, Any]:
    """Obtiene metadatos de un archivo requerido."""
    ruta = ROOT / ruta_relativa
    existe = ruta.exists() and ruta.is_file()

    return {
        "ruta": ruta_relativa.replace("\\", "/"),
        "existe": existe,
        "tamano_bytes": ruta.stat().st_size if existe else None,
        "sha256": calcular_sha256(ruta),
    }


def main() -> None:
    archivos = [
        obtener_informacion_archivo(ruta)
        for ruta in ARCHIVOS_REQUERIDOS
    ]

    faltantes = [
        archivo["ruta"]
        for archivo in archivos
        if not archivo["existe"]
    ]

    manifiesto = {
        "proyecto": "Prueba UTL Senado Boyaca 2026",
        "repositorio": "mosso_prueba_utl_2026",
        "autor": "Cristian Vidal Mosso Coy",
        "fecha_generacion_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "municipios": [
            "Tunja",
            "Paipa",
            "Sogamoso",
            "Duitama",
        ],
        "componentes": {
            "scraper": True,
            "base_datos_sqlite": True,
            "etl": True,
            "consultas_sql": 3,
            "dashboard": True,
            "visualizaciones": 2,
        },
        "archivos": archivos,
        "resumen": {
            "total_archivos_requeridos": len(archivos),
            "total_archivos_encontrados": (
                len(archivos) - len(faltantes)
            ),
            "total_archivos_faltantes": len(faltantes),
            "archivos_faltantes": faltantes,
            "estado": (
                "COMPLETO"
                if not faltantes
                else "INCOMPLETO"
            ),
        },
        "notas": [
            (
                "La base de datos db/puestos_2026.db se genera "
                "localmente mediante el proceso ETL."
            ),
            (
                "El archivo dashboard/data.json se genera con "
                "dashboard/export_data.py."
            ),
            (
                "Las imágenes PNG se generan ejecutando los "
                "scripts de la carpeta viz."
            ),
        ],
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            manifiesto,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    ejemplo = {
        "proyecto": manifiesto["proyecto"],
        "repositorio": manifiesto["repositorio"],
        "estado": manifiesto["resumen"]["estado"],
        "ejemplo_archivo": {
            "ruta": "README.md",
            "existe": True,
            "tamano_bytes": 1234,
            "sha256": "hash_sha256_de_ejemplo",
        },
    }

    EXAMPLE_PATH.write_text(
        json.dumps(
            ejemplo,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Manifiesto generado: {OUTPUT_PATH}")
    print(f"Ejemplo generado: {EXAMPLE_PATH}")
    print(
        "Estado:",
        manifiesto["resumen"]["estado"],
    )

    if faltantes:
        print("Archivos faltantes:")

        for archivo in faltantes:
            print(f"  - {archivo}")


if __name__ == "__main__":
    main()