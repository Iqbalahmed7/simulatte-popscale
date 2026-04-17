"""response_cache — deduplication cache for PopScale simulation runs.

Prevents redundant LLM calls when the same (persona, scenario) pair is
re-run. The cache key is a SHA-256 hash of persona_id + scenario question
+ domain, so different scenarios against the same persona are cached
independently.

Two backends:
  - In-memory (default): fast, process-lifetime only
  - Disk (optional): persists across runs as a JSON file

Usage::

    cache = ResponseCache()                     # in-memory only
    cache = ResponseCache(path="cache.json")    # with disk persistence

    key = cache.make_key(persona_id, scenario)
    if (hit := cache.get(key)) is not None:
        return hit

    response = await run_scenario(...)
    cache.put(key, response)
    cache.save()   # flush to disk if path set
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..scenario.model import Scenario
from ..schema.population_response import DomainSignals, PopulationResponse

logger = logging.getLogger(__name__)


class ResponseCache:
    """In-memory deduplication cache with optional disk persistence.

    Thread-safe for async use within a single event loop (no cross-process
    safety — for that, use a proper KV store in Week 10).

    Attributes:
        path:    Optional path to the JSON cache file.
        _store:  In-memory dict: cache_key → serialised PopulationResponse.
    """

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else None
        self._store: dict[str, dict] = {}
        self._hits = 0
        self._misses = 0
        if self.path and self.path.exists():
            self._load()

    # ── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def make_key(persona_id: str, scenario: Scenario) -> str:
        """Deterministic cache key for a (persona, scenario) pair.

        Key includes: persona_id, scenario question (normalised), context
        (normalised), and domain. Context is included because different
        research contexts (e.g. fuel price protests vs. no protests) should
        produce distinct responses for the same question.
        """
        context_fragment = scenario.context.strip().lower() if scenario.context else ""
        raw = (
            f"{persona_id}|"
            f"{scenario.question.strip().lower()}|"
            f"{context_fragment}|"
            f"{scenario.domain.value}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get(self, key: str) -> Optional[PopulationResponse]:
        """Return cached response, or None on miss."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        try:
            return _deserialise(entry)
        except Exception as e:
            logger.warning("Cache deserialisation failed for key %s: %s", key, e)
            self._misses += 1
            return None

    def put(self, key: str, response: PopulationResponse) -> None:
        """Store a response in the cache."""
        self._store[key] = _serialise(response)

    def invalidate(self, key: str) -> bool:
        """Remove a single entry. Returns True if the key existed."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Clear all entries and reset hit/miss counters."""
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def save(self) -> None:
        """Flush in-memory store to disk. No-op if no path configured."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._store, indent=2))
        logger.debug("Cache saved: %d entries → %s", len(self._store), self.path)

    # ── Stats ─────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def stats(self) -> dict:
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
            "path": str(self.path) if self.path else None,
        }

    # ── Private ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._store = json.loads(self.path.read_text())  # type: ignore[arg-type]
            logger.info("Cache loaded: %d entries from %s", len(self._store), self.path)
        except Exception as e:
            logger.warning("Failed to load cache from %s: %s", self.path, e)
            self._store = {}


# ── Serialisation helpers ─────────────────────────────────────────────────────
# PopulationResponse is a dataclass — convert to/from plain dict for JSON.

def _serialise(r: PopulationResponse) -> dict:
    d = dataclasses.asdict(r)
    # DomainSignals is nested dataclass — asdict handles it recursively
    return d


def _deserialise(d: dict) -> PopulationResponse:
    # Reconstruct DomainSignals from nested dict
    ds_raw = d.get("domain_signals", {})
    domain_signals = DomainSignals(**ds_raw) if ds_raw else DomainSignals()
    kwargs = {k: v for k, v in d.items() if k != "domain_signals"}
    return PopulationResponse(domain_signals=domain_signals, **kwargs)
