"""PubChem GHS hazard data loader (WP5.3).

Loads GHS (Globally Harmonized System) hazard classifications from
PubChem's PUG REST API. Populates onto.hazard_data with H-codes,
signal words, and pictograms per molecule.

Two modes:
  1. API mode (default): query PUG VIEW for molecules that already have a
     pubchem_cid in chem.molecules. Rate-limited to 5 req/s.
  2. File mode: parse a pre-downloaded PubChem GHS classifications JSON file.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import httpx
import structlog
from sqlalchemy import Connection, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chemworldmodel.db.schema import hazard_data
from chemworldmodel.loaders.base import BaseLoader, LoadStats

log = structlog.get_logger()

PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
RATE_LIMIT_DELAY = 0.21


class GHSLoader(BaseLoader):
    """Load GHS hazard classifications from PubChem.

    Overrides run() for API mode because each molecule requires a
    separate PUG VIEW request (no batch endpoint for GHS). File mode
    uses the standard BaseLoader pipeline.
    """

    source_name = "pubchem_ghs"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._http_client: httpx.Client | None = None

    def extract(self, **kwargs: Any) -> Iterator[Any]:
        """Yield items for GHS enrichment.

        File mode: yields parsed records from JSON lines file.
        API mode: yields (cid, inchikey) dicts for molecules with pubchem_cid.
        """
        ghs_file: Path | None = kwargs.get("ghs_file")
        if ghs_file:
            yield from self._extract_from_file(ghs_file, kwargs.get("limit"))
            return

        limit: int | None = kwargs.get("limit")

        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT pubchem_cid, inchikey FROM chem.molecules "
                    "WHERE pubchem_cid IS NOT NULL "
                    "AND inchikey NOT IN ("
                    "  SELECT inchikey FROM onto.hazard_data "
                    "  WHERE source = 'pubchem_ghs'"
                    ") "
                    "ORDER BY pubchem_cid"
                )
            )
            count = 0
            for cid, inchikey in result:
                yield {"cid": cid, "inchikey": inchikey, "mode": "api"}
                count += 1
                if limit and count >= limit:
                    return

    def _extract_from_file(
        self, path: Path, limit: int | None
    ) -> Iterator[dict]:
        """Parse a PubChem GHS JSON lines file."""
        count = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    yield {**record, "mode": "file"}
                    count += 1
                    if limit and count >= limit:
                        return
                except json.JSONDecodeError:
                    continue

    def transform_one(self, raw_item: Any) -> dict | None:
        """Transform a raw item into a hazard_data record.

        For file mode: parses the record directly.
        For API mode: fetches GHS data from PUG VIEW (rate-limited).
        """
        if raw_item.get("mode") == "file":
            return self._transform_file_record(raw_item)

        # API mode: fetch GHS data now (during transform, not load)
        ghs = self._fetch_ghs_for_cid(raw_item["cid"])
        if not ghs:
            return None

        return {
            "inchikey": raw_item["inchikey"],
            "ghs_codes": ghs.get("ghs_codes", []),
            "signal_word": ghs.get("signal_word"),
            "pictograms": ghs.get("pictograms", []),
        }

    def _transform_file_record(self, record: dict) -> dict | None:
        """Parse a file-mode record into hazard_data format."""
        inchikey = record.get("inchikey")
        if not inchikey:
            return None

        return {
            "inchikey": inchikey,
            "ghs_codes": record.get("ghs_codes", []),
            "signal_word": record.get("signal_word"),
            "pictograms": record.get("pictograms", []),
        }

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Insert GHS data into onto.hazard_data."""
        stats = LoadStats()

        for record in batch:
            try:
                conn.execute(
                    pg_insert(hazard_data)
                    .values(
                        inchikey=record["inchikey"],
                        ghs_codes=record.get("ghs_codes", []),
                        signal_word=record.get("signal_word"),
                        pictograms=record.get("pictograms", []),
                        source="pubchem_ghs",
                    )
                    .on_conflict_do_update(
                        index_elements=["inchikey", "source"],
                        set_={
                            "ghs_codes": record.get("ghs_codes", []),
                            "signal_word": record.get("signal_word"),
                            "pictograms": record.get("pictograms", []),
                        },
                    )
                )
                stats.loaded += 1
            except Exception as e:
                stats.add_error(str(e), record.get("inchikey"))

        return stats

    def run(self, **kwargs: Any) -> uuid.UUID:
        """Override run to manage a shared httpx client for API mode."""
        ghs_file = kwargs.get("ghs_file")
        if ghs_file:
            # File mode: use standard BaseLoader pipeline
            return super().run(**kwargs)

        # API mode: create a shared client for the full run
        self._http_client = httpx.Client(timeout=15.0)
        try:
            return super().run(**kwargs)
        finally:
            self._http_client.close()
            self._http_client = None

    def _fetch_ghs_for_cid(self, cid: int) -> dict | None:
        """Fetch GHS classification for a single CID from PUG VIEW."""
        url = f"{PUG_VIEW}/data/compound/{cid}/JSON"
        client = self._http_client or httpx.Client(timeout=15.0)
        close_after = self._http_client is None

        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = client.get(url, params={"heading": "GHS Classification"})

            if resp.status_code == 404:
                return None
            resp.raise_for_status()

            data = resp.json()
            return self._parse_ghs_response(data)

        except Exception as e:
            self.log.debug("ghs_fetch_error", cid=cid, error=str(e))
            return None
        finally:
            if close_after:
                client.close()

    def _parse_ghs_response(self, data: dict) -> dict:
        """Extract GHS codes, signal word, and pictograms from PUG VIEW JSON."""
        ghs_codes: list[str] = []
        signal_word: str | None = None
        pictograms: list[str] = []

        try:
            record = data.get("Record", {})
            sections = record.get("Section", [])

            for section in sections:
                for subsection in section.get("Section", []):
                    heading = subsection.get("TOCHeading", "")

                    if "GHS" not in heading:
                        continue

                    for info_section in subsection.get("Section", []):
                        info_heading = info_section.get("TOCHeading", "")
                        information = info_section.get("Information", [])

                        for info in information:
                            value = info.get("Value", {})
                            string_list = value.get("StringWithMarkup", [])

                            for s in string_list:
                                text_val = s.get("String", "")

                                if "Hazard Statements" in info_heading:
                                    codes = re.findall(r"H\d{3}", text_val)
                                    ghs_codes.extend(codes)

                                elif "Signal" in info_heading:
                                    if text_val in ("Danger", "Warning"):
                                        signal_word = text_val

                                elif "Pictogram" in info_heading:
                                    codes = re.findall(r"GHS\d{2}", text_val)
                                    pictograms.extend(codes)

        except Exception:
            pass

        return {
            "ghs_codes": sorted(set(ghs_codes)),
            "signal_word": signal_word,
            "pictograms": sorted(set(pictograms)),
        }
