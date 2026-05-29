import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("rpa_bot.repository")

_VERSION_SUFFIX = re.compile(r"\.\d+\.\d+\.\d+.*$")


@dataclass
class RpaProcess:
    index: int
    name: str
    filename: str
    nupkg_path: str
    description: str = ""
    version: str = ""


class RpaRepository:
    def __init__(self, rpa_folder: str) -> None:
        self._rpa_folder = rpa_folder
        self._processes: List[RpaProcess] = []

    def load(self) -> List[RpaProcess]:
        """Scans the RPA folder for .nupkg files and loads them."""
        if not os.path.isdir(self._rpa_folder):
            logger.error("RPA folder does not exist: %s", self._rpa_folder)
            self._processes = []
            return []

        # Group by package ID → keep only the newest file per ID
        packages: Dict[str, Tuple[str, float]] = {}  # id → (filepath, mtime)

        for filename in os.listdir(self._rpa_folder):
            if not filename.lower().endswith(".nupkg"):
                continue

            filepath = os.path.join(self._rpa_folder, filename)
            if not os.path.isfile(filepath):
                continue

            # Derive package ID from filename (strip version suffix)
            base = filename[:-6]  # remove ".nupkg"
            package_id = _VERSION_SUFFIX.sub("", base) or base

            mtime = os.path.getmtime(filepath)
            if package_id not in packages or mtime > packages[package_id][1]:
                packages[package_id] = (filepath, mtime)

        processes: List[RpaProcess] = []
        index = 1

        for package_id, (filepath, _) in sorted(packages.items()):
            name, description, version = self._read_nupkg_metadata(filepath)
            display_name = name or package_id

            processes.append(
                RpaProcess(
                    index=index,
                    name=display_name,
                    filename=os.path.basename(filepath),
                    nupkg_path=filepath,
                    description=description,
                    version=version,
                )
            )
            logger.debug("Loaded package [%d] '%s' v%s", index, display_name, version)
            index += 1

        self._processes = processes
        logger.info(
            "Loaded %d package(s) from '%s'", len(processes), self._rpa_folder
        )
        return processes

    def get_all(self) -> List[RpaProcess]:
        return list(self._processes)

    def find_by_index(self, index: int) -> Optional[RpaProcess]:
        return next((p for p in self._processes if p.index == index), None)

    def find_exact(self, name: str) -> Optional[RpaProcess]:
        name_lower = name.strip().lower()
        return next(
            (p for p in self._processes if p.name.lower() == name_lower), None
        )

    def search(self, query: str) -> List[RpaProcess]:
        q = query.strip().lower()
        return [
            p for p in self._processes
            if q in p.name.lower() or q in p.filename.lower()
        ]

    # ------------------------------------------------------------------

    @staticmethod
    def _read_nupkg_metadata(path: str) -> Tuple[str, str, str]:
        """Reads id, description and version from the .nuspec inside the .nupkg."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                nuspec_files = [f for f in zf.namelist() if f.endswith(".nuspec")]
                if not nuspec_files:
                    return "", "", ""

                with zf.open(nuspec_files[0]) as f:
                    root = ET.parse(f).getroot()

                # Strip XML namespace for simpler querying
                ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
                meta = root.find(f"{ns}metadata")
                if meta is None:
                    return "", "", ""

                def _text(tag: str) -> str:
                    el = meta.find(f"{ns}{tag}")
                    return (el.text or "").strip() if el is not None else ""

                return _text("id"), _text("description"), _text("version")

        except Exception as exc:
            logger.warning("Could not read metadata from '%s': %s", path, exc)
            return "", "", ""
