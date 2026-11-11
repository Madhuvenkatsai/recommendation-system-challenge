from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

from backend.app.db.schema import COLLECTION_NAMES
from backend.app.generator.anomalies import AnomalyConfig, iter_anomaly_fixtures
from backend.app.generator.config import GenerationConfig
from backend.app.generator.ids import dataset_version
from backend.app.generator.records import (
    event_split_for,
    event_timestamp,
    generation_run_record,
    iter_collection,
)
from backend.app.generator.targets import GenerationTarget, canonical_json, empty_checksum

GENERATION_ORDER = (
    "categories",
    "customers",
    "products",
    "sessions",
    "page_views",
    "carts",
    "cart_lines",
    "orders",
    "order_lines",
    "product_relations",
    "dataset_splits",
    "ground_truth_labels",
)


@dataclass(frozen=True)
class GenerationManifest:
    dataset_version: str
    seed: int
    configuration: dict[str, Any]
    collection_counts: dict[str, int]
    checksums: dict[str, str]
    started_at: datetime
    completed_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "seed": self.seed,
            "configuration": self.configuration,
            "collection_counts": self.collection_counts,
            "checksums": self.checksums,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "checksum_scope": (
                "Dataset collection rows only; generation_runs is excluded "
                "because its audit timestamps record wall-clock execution."
            ),
        }


class GenerationEngine:
    def __init__(
        self,
        config: GenerationConfig,
        *,
        batch_size: int = 1_000,
        anomaly_config: AnomalyConfig | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero.")
        self.config = config
        self.batch_size = batch_size
        self.anomaly_config = anomaly_config or AnomalyConfig()

    def run(self, target: GenerationTarget) -> GenerationManifest:
        started_at = datetime.now(timezone.utc)
        counts = {name: 0 for name in COLLECTION_NAMES}
        checksums = {
            name: empty_checksum()
            for name in COLLECTION_NAMES
            if name != "generation_runs"
        }
        digesters = {
            name: hashlib.sha256()
            for name in COLLECTION_NAMES
            if name != "generation_runs"
        }
        split_event_counts = {"train": 0, "validation": 0, "test": 0}
        try:
            for collection_name in GENERATION_ORDER:
                self._write_collection(
                    collection_name,
                    iter_collection(
                        collection_name,
                        self.config,
                        event_counts=split_event_counts,
                    ),
                    target,
                    counts,
                    digesters,
                    split_event_counts,
                )

            self._write_collection(
                "anomaly_fixtures",
                iter_anomaly_fixtures(self.config, self.anomaly_config),
                target,
                counts,
                digesters,
                split_event_counts,
            )
            completed_at = datetime.now(timezone.utc)
            counts["generation_runs"] = 1
            checksums = {
                name: digester.hexdigest() for name, digester in digesters.items()
            }
            manifest = GenerationManifest(
                dataset_version=dataset_version(self.config.as_dict()),
                seed=self.config.seed,
                configuration={
                    **self.config.as_dict(),
                    "anomaly_injection": {
                        "enabled": self.anomaly_config.enabled,
                        "issue_types": list(self.anomaly_config.issue_types),
                    },
                },
                collection_counts=counts,
                checksums=checksums,
                started_at=started_at,
                completed_at=completed_at,
            )
            run_record = generation_run_record(
                self.config, counts, checksums, started_at, completed_at
            )
            run_record["configuration"]["anomaly_injection"] = {
                "enabled": self.anomaly_config.enabled,
                "issue_types": list(self.anomaly_config.issue_types),
            }
            target.write_batch("generation_runs", [run_record])
            target.finalize(manifest.as_dict())
            return manifest
        finally:
            target.close()

    def _write_collection(
        self,
        collection_name: str,
        records,
        target: GenerationTarget,
        counts: dict[str, int],
        digesters: dict[str, Any],
        split_event_counts: dict[str, int],
    ) -> None:
        batch: list[dict[str, Any]] = []
        digester = digesters[collection_name]
        for record in records:
            canonical = canonical_json(record).encode("utf-8")
            digester.update(canonical)
            digester.update(b"\n")
            counts[collection_name] += 1
            timestamp = event_timestamp(collection_name, record)
            if timestamp is not None:
                split_event_counts[event_split_for(self.config, timestamp)] += 1
            batch.append(record)
            if len(batch) == self.batch_size:
                target.write_batch(collection_name, batch)
                batch = []
        if batch:
            target.write_batch(collection_name, batch)
