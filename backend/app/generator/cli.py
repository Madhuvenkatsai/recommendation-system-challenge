import argparse
from pathlib import Path

from backend.app.db.initialize import initialize_database
from backend.app.db.mongo import get_database
from backend.app.db.schema import COLLECTION_NAMES
from backend.app.generator.anomalies import ANOMALY_TYPES, AnomalyConfig
from backend.app.generator.config import GenerationConfig
from backend.app.generator.engine import GenerationEngine
from backend.app.generator.targets import (
    CompositeGenerationTarget,
    ExportGenerationTarget,
    MongoGenerationTarget,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic e-commerce data."
    )
    parser.add_argument(
        "--scale",
        choices=("starter", "full"),
        default="starter",
        help="Dataset scale; full uses the challenge's required target volumes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for CSV, JSON, JSONL, SQL, and manifest exports.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000,
        help="Maximum documents buffered per MongoDB insert batch.",
    )
    parser.add_argument(
        "--inject-anomalies",
        action="store_true",
        help="Write controlled anomaly fixtures separately from clean records.",
    )
    parser.add_argument(
        "--anomaly-types",
        nargs="+",
        choices=ANOMALY_TYPES,
        default=list(ANOMALY_TYPES),
        help="Anomaly fixture types to generate when --inject-anomalies is set.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = (
        GenerationConfig.starter()
        if args.scale == "starter"
        else GenerationConfig.full()
    )
    collection_prefix = "full_" if args.scale == "full" else None
    database = get_database(collection_prefix=collection_prefix)
    for collection_name in COLLECTION_NAMES:
        if database[collection_name].find_one({}, {"_id": 1}):
            raise RuntimeError(
                f"Collection namespace for {args.scale!r} generation already "
                f"contains data ('{collection_name}'); refusing to overwrite it."
            )
    initialize_database(database)
    output_dir = args.output_dir or (
        Path("generated-data-full")
        if args.scale == "full"
        else Path("generated-data")
    )
    target = CompositeGenerationTarget(
        MongoGenerationTarget(database),
        ExportGenerationTarget(output_dir),
    )
    manifest = GenerationEngine(
        config,
        batch_size=args.batch_size,
        anomaly_config=AnomalyConfig(args.inject_anomalies, tuple(args.anomaly_types)),
    ).run(target)
    print(
        f"Generated {manifest.dataset_version}: "
        f"{manifest.collection_counts['customers']} customers, "
        f"{manifest.collection_counts['products']} products, "
        f"{manifest.collection_counts['sessions']} sessions, "
        f"{manifest.collection_counts['orders']} orders."
    )
    print(f"CSV/JSONL/JSON/SQL exports and manifest: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
