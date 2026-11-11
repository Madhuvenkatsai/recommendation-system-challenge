from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
from typing import Any

from bson.decimal128 import Decimal128
from bson.int64 import Int64

from backend.app.generator.config import GenerationConfig
from backend.app.generator.ids import dataset_id, dataset_version, make_id

SEASONS = ("spring", "summer", "autumn", "winter")
ROOT_CATEGORY_COUNT = 8
CHILDREN_PER_ROOT = 4
POPULAR_PRODUCT_SHARE = 0.8
COLD_START_PRODUCT_SHARE = 0.1
UNAVAILABLE_PRODUCT_SHARE = 0.05
SPARSE_CUSTOMER_SHARE = 0.7
SPARSE_CUSTOMER_SESSION_SHARE = 0.1


def _mix64(seed: int, namespace: int, index: int) -> int:
    value = (seed ^ namespace ^ (index * 0x9E3779B97F4A7C15)) & 0xFFFFFFFFFFFFFFFF
    value = (value + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9 & 0xFFFFFFFFFFFFFFFF
    value = (value ^ (value >> 27)) * 0x94D049BB133111EB & 0xFFFFFFFFFFFFFFFF
    return value ^ (value >> 31)


def _money(cents: int) -> Decimal128:
    return Decimal128(Decimal(cents) / Decimal(100))


def _product_price_cents(product_index: int) -> int:
    return 500 + (product_index * 7919) % 50_000


def _popular_product_count(config: GenerationConfig) -> int:
    return max(config.categories, int(config.products * POPULAR_PRODUCT_SHARE))


def _cold_start_end(config: GenerationConfig) -> int:
    return max(
        _popular_product_count(config),
        int(config.products * (POPULAR_PRODUCT_SHARE + COLD_START_PRODUCT_SHARE)),
    )


def _unavailable_start(config: GenerationConfig) -> int:
    return max(
        _cold_start_end(config),
        int(
            config.products
            * (
                POPULAR_PRODUCT_SHARE
                + COLD_START_PRODUCT_SHARE
                + UNAVAILABLE_PRODUCT_SHARE
            )
        ),
    )


def _customer_id_for_session(config: GenerationConfig, session_index: int) -> str:
    sparse_start = max(1, int(config.customers * (1 - SPARSE_CUSTOMER_SHARE)))
    draw = _mix64(config.seed, 0x435553544F4D4552, session_index)
    pool_size = (
        sparse_start
        if draw % 100 < int((1 - SPARSE_CUSTOMER_SESSION_SHARE) * 100)
        else config.customers
    )
    customer_index = (draw >> 8) % pool_size
    return make_id("customers", customer_index, config.customers)


def _session_start(config: GenerationConfig, session_index: int) -> datetime:
    usable_seconds = config.timeline_seconds - 86_400
    offset = session_index * usable_seconds // config.sessions
    return config.start_at.astimezone(timezone.utc) + timedelta(seconds=offset)


def _session_duration_minutes(config: GenerationConfig, session_index: int) -> int:
    return 20 + _mix64(config.seed, 0x53455353494F4E, session_index) % 161


def page_view_count_for_session(
    config: GenerationConfig, session_index: int
) -> int:
    max_count = config.page_views_per_session * 2 - 1
    return 1 + _mix64(config.seed, 0x5041474556494557, session_index) % max_count


def _session_view_products(
    config: GenerationConfig, session_index: int
) -> list[int]:
    popular_count = _popular_product_count(config)
    view_count = page_view_count_for_session(config, session_index)
    rng = random.Random(
        config.seed ^ (session_index * 0x9E3779B97F4A7C15) ^ 0x5041474556494557
    )
    products: list[int] = []
    selected: set[int] = set()
    while len(products) < view_count:
        product_index = min(
            popular_count - 1,
            int(rng.random() ** 2 * popular_count),
        )
        if product_index not in selected:
            products.append(product_index)
            selected.add(product_index)
    return products


def _view_time(
    config: GenerationConfig, session_index: int, sequence: int
) -> datetime:
    return _session_start(config, session_index) + timedelta(minutes=sequence * 2)


def _cart_line_count(config: GenerationConfig, cart_index: int) -> int:
    session_index = _cart_session_index(config, cart_index)
    max_lines = min(3, page_view_count_for_session(config, session_index))
    return 1 + _mix64(config.seed, 0x434152544C494E45, cart_index) % max_lines


def _cart_session_index(config: GenerationConfig, cart_index: int) -> int:
    return cart_index * config.sessions // config.cart_count


def _cart_products(
    config: GenerationConfig, cart_index: int
) -> list[tuple[int, int, datetime]]:
    session_index = _cart_session_index(config, cart_index)
    view_products = _session_view_products(config, session_index)
    line_count = _cart_line_count(config, cart_index)
    selected_views = range(
        len(view_products) - line_count,
        len(view_products),
    )
    return [
        (
            view_products[sequence],
            1 + _mix64(config.seed, 0x5155414E54495459 + cart_index, sequence) % 3,
            _view_time(config, session_index, sequence + 1) + timedelta(minutes=1),
        )
        for sequence in selected_views
    ]


def _cart_id_for_order(config: GenerationConfig, order_index: int) -> int:
    return order_index * config.cart_count // config.orders


def _order_index_for_cart(config: GenerationConfig, cart_index: int) -> int | None:
    candidate = (
        cart_index * config.orders + config.cart_count - 1
    ) // config.cart_count
    if (
        candidate < config.orders
        and _cart_id_for_order(config, candidate) == cart_index
    ):
        return candidate
    return None


def _order_time(config: GenerationConfig, order_index: int) -> datetime:
    cart_index = _cart_id_for_order(config, order_index)
    cart_products = _cart_products(config, cart_index)
    return cart_products[-1][2] + timedelta(minutes=5)


def _split_boundaries(config: GenerationConfig) -> tuple[datetime, datetime]:
    start = config.start_at.astimezone(timezone.utc)
    end = config.end_at.astimezone(timezone.utc)
    duration = config.timeline_seconds
    train_end = start + timedelta(seconds=duration * 70 // 100)
    validation_end = start + timedelta(seconds=duration * 85 // 100)
    return train_end, validation_end


def split_name_for(config: GenerationConfig, occurred_at: datetime) -> str:
    train_end, validation_end = _split_boundaries(config)
    if occurred_at < train_end:
        return "train"
    if occurred_at < validation_end:
        return "validation"
    return "test"


def _category_record(config: GenerationConfig, category_index: int) -> dict[str, Any]:
    is_root = category_index < ROOT_CATEGORY_COUNT
    if is_root:
        parent_id = None
        season = SEASONS[category_index % len(SEASONS)]
        name = f"{season.title()} Collection {category_index + 1:02d}"
    else:
        parent_index = (category_index - ROOT_CATEGORY_COUNT) // CHILDREN_PER_ROOT
        parent_id = make_id("categories", parent_index, config.categories)
        season = SEASONS[parent_index % len(SEASONS)]
        name = f"{season.title()} Category {category_index + 1:02d}"
    slug = name.lower().replace(" ", "-")
    return {
        "_id": make_id("categories", category_index, config.categories),
        "name": name,
        "slug": slug,
        "parent_category_id": parent_id,
        "seasonal_tags": [season],
        "active_from": None,
        "active_to": None,
        "created_at": config.start_at,
        "updated_at": config.start_at,
    }


def _customer_record(config: GenerationConfig, customer_index: int) -> dict[str, Any]:
    sparse_start = max(1, int(config.customers * (1 - SPARSE_CUSTOMER_SHARE)))
    is_sparse = customer_index >= sparse_start
    return {
        "_id": make_id("customers", customer_index, config.customers),
        "created_at": config.start_at,
        "updated_at": config.start_at,
        "segment": "sparse" if is_sparse else "regular",
        "region": f"region-{customer_index % 8 + 1}",
        "attributes": {"activity_tier": "sparse" if is_sparse else "regular"},
        "is_active": True,
    }


def _product_record(config: GenerationConfig, product_index: int) -> dict[str, Any]:
    cold_start_end = _cold_start_end(config)
    unavailable_start = _unavailable_start(config)
    if product_index < _popular_product_count(config):
        status = "active"
        is_cold_start = False
        available_to = None
    elif product_index < cold_start_end:
        status = "active"
        is_cold_start = True
        available_to = None
    elif product_index < unavailable_start:
        status = "unavailable"
        is_cold_start = False
        available_to = None
    else:
        status = "discontinued"
        is_cold_start = False
        available_to = config.start_at + timedelta(
            seconds=config.timeline_seconds * 3 // 4
        )
    if is_cold_start:
        catalog_group = "cold_start"
    elif status != "active":
        catalog_group = status
    else:
        catalog_group = "popular"
    category_index = product_index % config.categories
    return {
        "_id": make_id("products", product_index, config.products),
        "category_id": make_id("categories", category_index, config.categories),
        "name": f"Product {product_index + 1:06d}",
        "description": (
            f"{SEASONS[category_index % len(SEASONS)]} "
            f"category {category_index + 1} item"
        ),
        "brand": f"Brand {product_index % 25 + 1:02d}",
        "attributes": {
            "catalog_group": catalog_group,
            "category_index": category_index,
        },
        "price": _money(_product_price_cents(product_index)),
        "currency": "USD",
        "status": status,
        "available_from": config.start_at,
        "available_to": available_to,
        "is_cold_start": is_cold_start,
        "created_at": config.start_at,
        "updated_at": config.end_at,
    }


def _session_record(config: GenerationConfig, session_index: int) -> dict[str, Any]:
    draw = _mix64(config.seed, 0x54524146464943, session_index)
    is_bot = draw % 100 < 2
    is_noisy = (draw >> 8) % 100 < 5
    started_at = _session_start(config, session_index)
    return {
        "_id": make_id("sessions", session_index, config.sessions),
        "customer_id": _customer_id_for_session(config, session_index),
        "started_at": started_at,
        "ended_at": started_at
        + timedelta(minutes=_session_duration_minutes(config, session_index)),
        "source": ("bot" if is_bot else ("search", "direct", "email", "social")[(draw >> 16) % 4]),
        "device": ("desktop", "mobile", "tablet")[(draw >> 24) % 3],
        "is_bot": is_bot,
        "is_noisy": is_noisy,
    }


def _page_view_records(
    config: GenerationConfig, session_index: int
) -> Iterator[dict[str, Any]]:
    customer_id = _customer_id_for_session(config, session_index)
    products = _session_view_products(config, session_index)
    for sequence, product_index in enumerate(products, start=1):
        max_views = config.page_views_per_session * 2 - 1
        view_index = session_index * max_views + sequence - 1
        yield {
            "_id": make_id(
                "page_views",
                view_index,
                config.sessions * max_views,
            ),
            "session_id": make_id("sessions", session_index, config.sessions),
            "customer_id": customer_id,
            "product_id": make_id("products", product_index, config.products),
            "occurred_at": _view_time(config, session_index, sequence),
            "sequence": sequence,
            "referrer": ("search", "category", "recommendation")[sequence % 3],
        }


def _cart_record(config: GenerationConfig, cart_index: int) -> dict[str, Any]:
    session_index = _cart_session_index(config, cart_index)
    products = _cart_products(config, cart_index)
    created_at = products[0][2]
    order_index = _order_index_for_cart(config, cart_index)
    is_converted = order_index is not None
    converted_at = _order_time(config, order_index) if order_index is not None else None
    if is_converted:
        status = "converted"
        updated_at = converted_at
    else:
        draw = _mix64(config.seed, 0x4341525453544154, cart_index)
        status = "abandoned" if draw % 10 < 7 else "active"
        updated_at = created_at + timedelta(hours=1)
    return {
        "_id": make_id("carts", cart_index, config.cart_count),
        "customer_id": _customer_id_for_session(config, session_index),
        "session_id": make_id("sessions", session_index, config.sessions),
        "created_at": created_at,
        "updated_at": updated_at,
        "converted_at": converted_at,
        "status": status,
    }


def _cart_line_records(
    config: GenerationConfig, cart_index: int
) -> Iterator[dict[str, Any]]:
    for line_index, (product_index, quantity, added_at) in enumerate(
        _cart_products(config, cart_index)
    ):
        global_line_index = cart_index * 3 + line_index
        cents = _product_price_cents(product_index)
        yield {
            "_id": make_id(
                "cart_lines",
                global_line_index,
                config.cart_count * 3,
            ),
            "cart_id": make_id("carts", cart_index, config.cart_count),
            "product_id": make_id("products", product_index, config.products),
            "quantity": quantity,
            "unit_price": _money(cents),
            "line_total": _money(cents * quantity),
            "added_at": added_at,
        }


def _order_record(config: GenerationConfig, order_index: int) -> dict[str, Any]:
    cart_index = _cart_id_for_order(config, order_index)
    session_index = _cart_session_index(config, cart_index)
    line_data = _cart_products(config, cart_index)
    subtotal_cents = sum(
        _product_price_cents(product_index) * quantity
        for product_index, quantity, _ in line_data
    )
    tax_cents = (subtotal_cents + 5) // 10
    shipping_cents = 0 if subtotal_cents >= 10_000 else 500
    status_draw = _mix64(config.seed, 0x4F52444552535441, order_index) % 100
    status = (
        "completed"
        if status_draw < 94
        else "cancelled" if status_draw < 98 else "refunded"
    )
    return {
        "_id": make_id("orders", order_index, config.orders),
        "customer_id": _customer_id_for_session(config, session_index),
        "session_id": make_id("sessions", session_index, config.sessions),
        "cart_id": make_id("carts", cart_index, config.cart_count),
        "placed_at": _order_time(config, order_index),
        "status": status,
        "currency": "USD",
        "subtotal": _money(subtotal_cents),
        "discount_total": _money(0),
        "tax_total": _money(tax_cents),
        "shipping_total": _money(shipping_cents),
        "total": _money(subtotal_cents + tax_cents + shipping_cents),
    }


def _order_line_records(
    config: GenerationConfig, order_index: int
) -> Iterator[dict[str, Any]]:
    cart_index = _cart_id_for_order(config, order_index)
    cart_lines = _cart_products(config, cart_index)
    for line_index, (product_index, quantity, _) in enumerate(cart_lines):
        unit_cents = _product_price_cents(product_index)
        yield {
            "_id": make_id(
                "order_lines",
                order_index * 3 + line_index,
                config.cart_count * 3,
            ),
            "order_id": make_id("orders", order_index, config.orders),
            "product_id": make_id("products", product_index, config.products),
            "quantity": quantity,
            "unit_price": _money(unit_cents),
            "discount": _money(0),
            "line_total": _money(unit_cents * quantity),
        }


def _category_partner(category_index: int, category_count: int) -> int:
    if category_index < ROOT_CATEGORY_COUNT:
        first_child = ROOT_CATEGORY_COUNT + category_index * CHILDREN_PER_ROOT
        return first_child if first_child < category_count else (category_index + 1) % ROOT_CATEGORY_COUNT
    parent_index = (category_index - ROOT_CATEGORY_COUNT) // CHILDREN_PER_ROOT
    group_start = ROOT_CATEGORY_COUNT + parent_index * CHILDREN_PER_ROOT
    group_end = min(group_start + CHILDREN_PER_ROOT, category_count)
    if group_end - group_start > 1:
        return group_start + (category_index - group_start + 1) % (group_end - group_start)
    return parent_index


def _product_relation_records(
    config: GenerationConfig, product_index: int
) -> Iterator[dict[str, Any]]:
    active_count = _cold_start_end(config)
    category_index = product_index % config.categories
    same_category = list(range(category_index, active_count, config.categories))
    source_position = same_category.index(product_index)
    similar_index = same_category[(source_position + 1) % len(same_category)]
    partner_category = _category_partner(category_index, config.categories)
    complementary_index = partner_category
    source_id = make_id("products", product_index, config.products)
    created_at = config.start_at
    yield {
        "_id": make_id(
            "product_relations", product_index * 2, active_count * 2
        ),
        "source_product_id": source_id,
        "target_product_id": make_id("products", similar_index, config.products),
        "relation_type": "similar",
        "weight": 1.0,
        "created_at": created_at,
    }
    yield {
        "_id": make_id(
            "product_relations", product_index * 2 + 1, active_count * 2
        ),
        "source_product_id": source_id,
        "target_product_id": make_id(
            "products", complementary_index, config.products
        ),
        "relation_type": "complementary",
        "weight": 0.5,
        "created_at": created_at,
    }


def _split_records(
    config: GenerationConfig, event_counts: dict[str, int]
) -> Iterator[dict[str, Any]]:
    start = config.start_at.astimezone(timezone.utc)
    end = config.end_at.astimezone(timezone.utc)
    train_end, validation_end = _split_boundaries(config)
    fingerprint = dataset_version(config.as_dict())[2:]
    windows = (
        ("train", start, train_end),
        ("validation", train_end, validation_end),
        ("test", validation_end, end),
    )
    for split_name, start_at, end_at in windows:
        yield {
            "_id": dataset_id("dataset_splits", fingerprint, split_name),
            "dataset_version": dataset_version(config.as_dict()),
            "split_name": split_name,
            "start_at": start_at,
            "end_at": end_at,
            "created_at": start,
            "event_count": event_counts[split_name],
        }


def _ground_truth_records(config: GenerationConfig) -> Iterator[dict[str, Any]]:
    fingerprint = dataset_version(config.as_dict())[2:]
    split_ids = {
        name: dataset_id("dataset_splits", fingerprint, name)
        for name in ("validation", "test")
    }
    label_index = 0
    for order_index in range(config.orders):
        occurred_at = _order_time(config, order_index)
        split_name = split_name_for(config, occurred_at)
        if split_name == "train":
            continue
        order = _order_record(config, order_index)
        if order["status"] not in {"paid", "completed"}:
            continue
        for order_line in _order_line_records(config, order_index):
            yield {
                "_id": make_id("ground_truth_labels", label_index, config.orders * 3),
                "customer_id": order["customer_id"],
                "product_id": order_line["product_id"],
                "source_event_id": order_line["_id"],
                "dataset_split_id": split_ids[split_name],
                "event_type": "purchase",
                "occurred_at": occurred_at,
                "relevance": 1,
            }
            label_index += 1


def iter_collection(
    collection_name: str,
    config: GenerationConfig,
    *,
    event_counts: dict[str, int] | None = None,
) -> Iterator[dict[str, Any]]:
    if collection_name == "categories":
        for index in range(config.categories):
            yield _category_record(config, index)
    elif collection_name == "customers":
        for index in range(config.customers):
            yield _customer_record(config, index)
    elif collection_name == "products":
        for index in range(config.products):
            yield _product_record(config, index)
    elif collection_name == "sessions":
        for index in range(config.sessions):
            yield _session_record(config, index)
    elif collection_name == "page_views":
        for session_index in range(config.sessions):
            yield from _page_view_records(config, session_index)
    elif collection_name == "carts":
        for index in range(config.cart_count):
            yield _cart_record(config, index)
    elif collection_name == "cart_lines":
        for cart_index in range(config.cart_count):
            yield from _cart_line_records(config, cart_index)
    elif collection_name == "orders":
        for index in range(config.orders):
            yield _order_record(config, index)
    elif collection_name == "order_lines":
        for order_index in range(config.orders):
            for record in _order_line_records(config, order_index):
                yield record
    elif collection_name == "product_relations":
        for product_index in range(_cold_start_end(config)):
            yield from _product_relation_records(config, product_index)
    elif collection_name == "dataset_splits":
        if event_counts is None:
            raise ValueError("event_counts is required to generate dataset_splits.")
        yield from _split_records(config, event_counts)
    elif collection_name == "ground_truth_labels":
        yield from _ground_truth_records(config)
    else:
        raise ValueError(f"Collection {collection_name!r} is not generated here.")


def event_timestamp(collection_name: str, record: dict[str, Any]) -> datetime | None:
    if collection_name == "page_views":
        return record["occurred_at"]
    if collection_name == "carts":
        return record["created_at"]
    if collection_name == "orders":
        return record["placed_at"]
    return None


def event_split_for(config: GenerationConfig, occurred_at: datetime) -> str:
    return split_name_for(config, occurred_at)


def generation_run_record(
    config: GenerationConfig,
    counts: dict[str, int],
    checksums: dict[str, str],
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    version = dataset_version(config.as_dict())
    return {
        "_id": dataset_id("generation_runs", version[2:], ""),
        "seed": Int64(config.seed),
        "configuration": config.as_dict(),
        "status": "completed",
        "started_at": started_at,
        "completed_at": completed_at,
        "collection_counts": counts,
        "checksums": checksums,
        "error": None,
    }
