import argparse
from pathlib import Path

from backend.app.db.initialize import initialize_database
from backend.app.db.mongo import get_database
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
        default=Path("generated-data"),
        help="Directory for CSV, JSON Lines, and manifest exports.",
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
    database = get_database()
    initialize_database(database)
    target = CompositeGenerationTarget(
        MongoGenerationTarget(database),
        ExportGenerationTarget(args.output_dir),
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
    print(f"CSV/JSONL exports and manifest: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
