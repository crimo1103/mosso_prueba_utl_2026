# MOSSO — Prueba Técnica UTL Senado 2026

## Candidato

- **Nombre:** Cristian Vidal Mosso Coy
- **Email:** PENDIENTE
- **Repositorio:** https://github.com/crimo1103/mosso_prueba_utl_2026

## Instalación

> Proyecto en construcción.

Requisitos iniciales:

- Python 3.11 o superior
- Git
- SQLite 3

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Pipeline de ejecución

El pipeline previsto es:

1. Extraer resultados electorales de Cámara y Senado para Tunja, Paipa, Sogamoso y Duitama.
2. Normalizar y cargar la información en SQLite.
3. Ejecutar las tres consultas analíticas solicitadas.
4. Exportar los datos del dashboard.
5. Generar las visualizaciones en Python.
6. Ejecutar el manifest de evaluación.

Comandos definitivos pendientes de implementación.

## API

Pendiente documentar después de inspeccionar la API oficial de resultados de la Registraduría:

- Patrón de URL.
- Nomenclátor.
- Cabeceras HTTP necesarias.
- Campos JSON utilizados.
- Estrategia de reintentos y manejo de indisponibilidad.

## Municipios en la BD

Municipios obligatorios:

- TUNJA
- PAIPA
- SOGAMOSO
- DUITAMA

Los conteos se incorporarán una vez se ejecute el proceso ETL.

## Hallazgos principales

Pendiente completar con resultados verificables obtenidos de la base de datos y las consultas SQL.

## Bonus implementados

Planeados:

- Flag `--preflight`.
- Tres o más índices SQLite justificados.
- Explicación de la atribución determinística Cámara–Senado.
- Modo oscuro en el dashboard.
- Exportación CSV.
