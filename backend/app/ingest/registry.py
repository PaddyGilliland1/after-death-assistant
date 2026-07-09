"""Seed source registry loader (build contract section 10).

The registry is a JSON list of public guidance sources, each carrying
form_code_or_topic, title, url, licence and jurisdiction. Entries whose
URL is still "TO-RESOLVE" are skipped with a logged note so the pipeline
only ever fetches resolved addresses.
"""

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = _BACKEND_DIR / "seed_templates" / "source_registry.json"

UNRESOLVED_URL = "TO-RESOLVE"

# Form codes look like IHT400, IHT30, IOV2: upper-case letters then digits,
# optionally more letters. Topics use lower_snake_case and never match.
_FORM_CODE_RE = re.compile(r"^[A-Z]{2,8}\d{1,4}[A-Z]{0,2}$")


class RegistrySource(BaseModel):
    """One entry of the seed source registry."""

    model_config = ConfigDict(frozen=True)

    form_code_or_topic: str
    title: str
    url: str
    licence: str
    jurisdiction: str

    @property
    def key(self) -> str:
        """The stable identifier used to select sources for ingestion."""
        return self.form_code_or_topic

    @property
    def form_code(self) -> str | None:
        """The HMRC form code, when the entry is a form rather than a topic."""
        if _FORM_CODE_RE.match(self.form_code_or_topic):
            return self.form_code_or_topic
        return None

    @property
    def topic(self) -> str | None:
        """The topic slug, when the entry is guidance rather than a form."""
        if self.form_code is None:
            return self.form_code_or_topic
        return None


def load_registry(path: Path | str | None = None) -> list[RegistrySource]:
    """Load the source registry, skipping unresolved entries with a note."""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    raw_entries = json.loads(registry_path.read_text(encoding="utf-8"))

    sources: list[RegistrySource] = []
    for raw in raw_entries:
        source = RegistrySource.model_validate(raw)
        if source.url.strip() == UNRESOLVED_URL:
            logger.info(
                "Skipping registry entry %s (%s): URL not yet resolved (TO-RESOLVE)",
                source.key,
                source.title,
            )
            continue
        sources.append(source)
    return sources
