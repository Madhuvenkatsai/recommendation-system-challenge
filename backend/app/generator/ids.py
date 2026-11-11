from hashlib import blake2b

ID_PREFIXES = {
    "customers": "CUS",
    "products": "PRO",
    "categories": "CAT",
    "sessions": "SES",
    "page_views": "PVW",
    "carts": "CRT",
    "cart_lines": "CLN",
    "orders": "ORD",
    "order_lines": "OLN",
    "product_relations": "REL",
    "recommendations": "REC",
    "ground_truth_labels": "GTL",
    "dataset_splits": "SPL",
    "generation_runs": "RUN",
    "lifecycle_events": "LCE",
}


def make_id(collection: str, index: int, total: int) -> str:
    """Create a stable, zero-based sequential ID with a minimum 8-digit suffix."""
    if collection not in ID_PREFIXES:
        raise ValueError(f"No generated ID format is defined for {collection!r}.")
    if index < 0 or total < 0 or index >= max(total, 1):
        raise ValueError("index must refer to a record within the collection.")
    width = max(8, len(str(max(total, 1))))
    return f"{ID_PREFIXES[collection]}{index + 1:0{width}d}"


def dataset_fingerprint(config: dict[str, object]) -> str:
    digest = blake2b(digest_size=8)
    digest.update(repr(sorted(config.items())).encode("utf-8"))
    return digest.hexdigest().upper()


def dataset_version(config: dict[str, object]) -> str:
    return f"DS{dataset_fingerprint(config)}"


def dataset_id(collection: str, fingerprint: str, suffix: str) -> str:
    prefix = ID_PREFIXES[collection]
    return f"{prefix}{fingerprint}{suffix.upper()}"
