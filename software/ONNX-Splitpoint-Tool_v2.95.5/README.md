# ONNX Splitpoint Tool – v2.95.5

Bereinigtes Quellcode-Paket des aktuellen Tools (**Version 2.95.5**). Es enthält GUI, CLI, Benchmark-/Remote-Runner, benötigte Ressourcen und zugehörige Hilfsskripte. Historische Release-Berichte, alte Tests samt Fixtures und nicht mehr benötigte Versions-/Diagnoseskripte sind nicht enthalten.

## Start (Linux)

Voraussetzung: Python 3.8 oder neuer, `python3-venv` und `pip`.

```bash
./start_gui.sh
```

Beim ersten Start erstellt das Startskript eine virtuelle Umgebung und installiert die erforderlichen Basisabhängigkeiten. Alternativ:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
onnx-splitpoint-gui
```

Für CLI-Funktionen:

```bash
onnx-splitpoint --help
```

Je nach Backend/Funktion sind weitere optionale Python-Pakete, Hardware-SDKs, Modelle, Datensätze oder Remote-Setups erforderlich. Diese großen bzw. herstellerspezifischen Artefakte sind nicht Bestandteil der ZIP.

## Inhalt

- `onnx_splitpoint_tool/` – aktueller Programmcode einschließlich benötigter Kompatibilitäts- und Runtime-Module
- `scripts/` – operative Tools und weiterhin referenzierte Hilfsprogramme
- `analyse_and_split_gui.py`, `start_gui.sh` – GUI-Start
- `analyse_and_split.py`, `pt_to_onnx.py` – weitere Einstiegspunkte
- `pyproject.toml`, `requirements.txt`, `uv.lock` – Paket- und Abhängigkeitsdefinitionen
- `docs/QUICKSTART.md` – Kurzanleitung
- `docs/RELEASE_2.95.5.md` – Hinweise zur aktuellen Version; weitere erhaltene Dokumente erläutern wichtige Funktionen
- `SOURCE_MANIFEST.json`, `SHA256SUMS.txt` – neu erzeugte Datei- und Integritätsindizes

**Hinweis:** Die aktuelle Softwareversion ist 2.95.5. Der Quellstand ist nicht gleichbedeutend mit einer vollständigen Abnahme aller Hardware-Backends; technische Einschränkungen und der zuletzt dokumentierte Abnahmestand stehen in `docs/RELEASE_2.95.5.md`.
