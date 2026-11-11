from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Any

from backend.app.db.schema import CORE_COLLECTIONS, REQUIRED_FIELDS, SCHEMAS

Record = Mapping[str, Any]
Rows = Callable[[], Iterable[Record]] | Iterable[Record]
Emitter = Callable[..., None]


def iter_rows(source: Rows) -> Iterable[Record]:
    return source() if callable(source) else source


def _money(value: Any) -> Decimal:
    if hasattr(value, "to_decimal"):
        return value.to_decimal()
    return Decimal(str(value))


@dataclass
class ValidationContext:
    sources: Mapping[str, Rows]
    generation_run_id: str
    detected_at: datetime
    emit: Emitter
    ids: dict[str, set[str]] = field(default_factory=dict)
    categories: dict[str, str | None] = field(default_factory=dict)
    products: dict[str, tuple[Any, Any, Any, Any]] = field(default_factory=dict)
    sessions: dict[str, tuple[Any, Any, Any]] = field(default_factory=dict)
    carts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    orders: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    order_line_orders: dict[str, str] = field(default_factory=dict)
    splits: dict[str, tuple[str, Any, Any]] = field(default_factory=dict)
    split_names: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    view_times: dict[tuple[str, str], datetime] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def rows(self, collection: str) -> Iterable[Record]:
        return iter_rows(self.sources.get(collection, ()))

    def id_exists(self, collection: str, value: Any) -> bool:
        return isinstance(value, str) and value in self.ids.get(collection, set())


def prepare_context(context: ValidationContext) -> None:
    referenced_collections = {
        "customers",
        "categories",
        "products",
        "sessions",
        "carts",
        "orders",
        "dataset_splits",
        "ground_truth_labels",
        "model_runs",
        "order_lines",
    }
    context.ids = {name: set() for name in referenced_collections}
    for collection in context.sources:
        seen: set[str] = set()
        required = REQUIRED_FIELDS.get(collection, ())
        count = 0
        for record in context.rows(collection):
            count += 1
            entity_id = record.get("_id")
            if not isinstance(entity_id, str) or not entity_id:
                context.emit(
                    "primary_key_missing",
                    "error",
                    collection,
                    None,
                    [],
                    "Record is missing a non-empty string _id.",
                    "primary_key_missing",
                )
            elif entity_id in seen:
                context.emit(
                    "primary_key_duplicate",
                    "critical",
                    collection,
                    entity_id,
                    [entity_id],
                    "Duplicate primary key in the input collection.",
                    "primary_key_duplicate",
                )
            else:
                seen.add(entity_id)
                if collection in context.ids:
                    context.ids[collection].add(entity_id)
            for field_name in required:
                bson_type = SCHEMAS[collection][field_name].get("bsonType")
                nullable = isinstance(bson_type, list) and "null" in bson_type
                if field_name not in record or (
                    record[field_name] is None and not nullable
                ):
                    context.emit(
                        "required_field_missing",
                        "error",
                        collection,
                        entity_id,
                        [entity_id] if entity_id else [],
                        f"Required field {field_name!r} is missing or null.",
                        "required_field_missing",
                    )
        context.counts[collection] = count

    for record in context.rows("categories"):
        category_id = record.get("_id")
        if isinstance(category_id, str):
            context.categories[category_id] = record.get("parent_category_id")
    for record in context.rows("products"):
        product_id = record.get("_id")
        if isinstance(product_id, str):
            context.products[product_id] = (
                record.get("status"),
                record.get("available_from"),
                record.get("available_to"),
                record.get("category_id"),
            )
    for record in context.rows("sessions"):
        session_id = record.get("_id")
        if isinstance(session_id, str):
            context.sessions[session_id] = (
                record.get("customer_id"),
                record.get("started_at"),
                record.get("ended_at"),
            )
    for record in context.rows("carts"):
        cart_id = record.get("_id")
        if isinstance(cart_id, str):
            context.carts[cart_id] = (
                record.get("customer_id"),
                record.get("session_id"),
                record.get("created_at"),
                record.get("updated_at"),
                record.get("converted_at"),
                record.get("status"),
            )
    for record in context.rows("orders"):
        order_id = record.get("_id")
        if isinstance(order_id, str):
            context.orders[order_id] = (
                record.get("customer_id"),
                record.get("session_id"),
                record.get("cart_id"),
                record.get("placed_at"),
                record.get("status"),
                record.get("subtotal"),
                record.get("discount_total"),
                record.get("tax_total"),
                record.get("shipping_total"),
                record.get("total"),
            )
    for record in context.rows("dataset_splits"):
        split_id = record.get("_id")
        split_name = record.get("split_name")
        if isinstance(split_id, str) and isinstance(split_name, str):
            context.splits[split_id] = (
                split_name,
                record.get("start_at"),
                record.get("end_at"),
            )
            context.split_names[split_name] = (
                record.get("start_at"),
                record.get("end_at"),
            )
    for record in context.rows("order_lines"):
        line_id = record.get("_id")
        order_id = record.get("order_id")
        if isinstance(line_id, str) and isinstance(order_id, str):
            context.order_line_orders[line_id] = order_id


def validate_references(context: ValidationContext) -> None:
    direct_references = (
        ("products", "category_id", "categories"),
        ("sessions", "customer_id", "customers"),
        ("page_views", "session_id", "sessions"),
        ("page_views", "customer_id", "customers"),
        ("page_views", "product_id", "products"),
        ("carts", "customer_id", "customers"),
        ("carts", "session_id", "sessions"),
        ("cart_lines", "cart_id", "carts"),
        ("cart_lines", "product_id", "products"),
        ("orders", "customer_id", "customers"),
        ("orders", "session_id", "sessions"),
        ("orders", "cart_id", "carts"),
        ("order_lines", "order_id", "orders"),
        ("order_lines", "product_id", "products"),
        ("product_relations", "source_product_id", "products"),
        ("product_relations", "target_product_id", "products"),
        ("recommendations", "customer_id", "customers"),
        ("ground_truth_labels", "customer_id", "customers"),
        ("ground_truth_labels", "product_id", "products"),
        ("ground_truth_labels", "dataset_split_id", "dataset_splits"),
        ("ground_truth_labels", "source_event_id", "order_lines"),
        ("model_runs", "training_split_id", "dataset_splits"),
        ("evaluation_results", "model_run_id", "model_runs"),
        ("evaluation_results", "dataset_split_id", "dataset_splits"),
        ("recommendations", "model_run_id", "model_runs"),
    )
    for collection, field_name, referenced in direct_references:
        for record in context.rows(collection):
            value = record.get(field_name)
            if value is None and collection in {"carts", "orders", "recommendations"}:
                continue
            if not context.id_exists(referenced, value):
                entity_id = record.get("_id")
                context.emit(
                    "foreign_reference_missing",
                    "error",
                    collection,
                    entity_id,
                    [entity_id, value] if isinstance(value, str) else [entity_id],
                    f"{field_name} does not reference an existing {referenced} record.",
                    "foreign_reference_missing",
                )
    for record in context.rows("categories"):
        category_id = record.get("_id")
        parent_id = record.get("parent_category_id")
        if parent_id is not None and not context.id_exists("categories", parent_id):
            context.emit(
                "category_parent_missing",
                "error",
                "categories",
                category_id,
                [category_id, parent_id] if isinstance(parent_id, str) else [category_id],
                "Category parent reference does not exist.",
                "category_parent_missing",
            )
    for relation in context.rows("product_relations"):
        if relation.get("source_product_id") == relation.get("target_product_id"):
            context.emit(
                "product_relation_self_reference",
                "error",
                "product_relations",
                relation.get("_id"),
                [
                    relation.get("_id"),
                    relation.get("source_product_id"),
                    relation.get("target_product_id"),
                ],
                "A product relation cannot reference the same product as source and target.",
                "product_relation_self_reference",
            )
    for record in context.rows("recommendations"):
        recommendation_id = record.get("_id")
        for item in record.get("items", ()):
            product_id = item.get("product_id")
            if not context.id_exists("products", product_id):
                context.emit(
                    "foreign_reference_missing",
                    "error",
                    "recommendations",
                    recommendation_id,
                    [recommendation_id, product_id]
                    if isinstance(product_id, str)
                    else [recommendation_id],
                    "Recommendation item does not reference an existing product.",
                    "foreign_reference_missing",
                )


def validate_lifecycle_history(context: ValidationContext) -> None:
    allowed_transitions = {
        "cart": {
            "active": {"converted", "abandoned", "cancelled"},
        },
        "order": {
            "pending": {"paid", "cancelled"},
            "paid": {"completed", "refunded"},
            "completed": {"refunded"},
        },
    }
    histories: dict[tuple[str, str], tuple[int, str, datetime]] = {}
    seen_sequences: set[tuple[str, str, int]] = set()
    seen_event_ids: set[str] = set()

    events = context.rows("lifecycle_events")
    if hasattr(events, "batch_size") and hasattr(events, "sort"):
        events = events.sort(
            [("entity_type", 1), ("entity_id", 1), ("sequence", 1)]
        )
    for event in events:
        event_id = event.get("_id")
        entity_type = event.get("entity_type")
        entity_id = event.get("entity_id")
        sequence = event.get("sequence")
        previous_state = event.get("previous_state")
        new_state = event.get("new_state")
        occurred_at = event.get("occurred_at")
        key = (entity_type, entity_id)
        reference_collection = {
            "cart": "carts",
            "order": "orders",
        }.get(entity_type)
        if (
            reference_collection is None
            or not context.id_exists(reference_collection, entity_id)
        ):
            context.emit(
                "lifecycle_entity_missing",
                "error",
                "lifecycle_events",
                event_id,
                [event_id, entity_id],
                "Lifecycle event must reference an existing cart or order.",
                "lifecycle_entity_missing",
            )
            continue
        if not isinstance(sequence, int) or sequence < 1:
            context.emit(
                "lifecycle_sequence_invalid",
                "error",
                "lifecycle_events",
                event_id,
                [event_id, entity_id],
                "Lifecycle event sequence must be a positive integer.",
                "lifecycle_sequence_invalid",
            )
            continue
        sequence_key = (entity_type, entity_id, sequence)
        if sequence_key in seen_sequences or (
            isinstance(event_id, str) and event_id in seen_event_ids
        ):
            context.emit(
                "lifecycle_event_duplicate",
                "error",
                "lifecycle_events",
                event_id,
                [event_id, entity_id],
                "Lifecycle event ID or entity sequence is duplicated.",
                "lifecycle_event_duplicate",
            )
            continue
        seen_sequences.add(sequence_key)
        if isinstance(event_id, str):
            seen_event_ids.add(event_id)

        prior = histories.get(key)
        valid = isinstance(occurred_at, datetime)
        if prior is None:
            valid = (
                valid
                and sequence == 1
                and previous_state is None
                and event.get("event_type") == "created"
                and new_state
                in ({"active"} if entity_type == "cart" else {"pending"})
            )
            entity = (
                context.carts[entity_id]
                if entity_type == "cart"
                else context.orders[entity_id]
            )
            expected_start = entity[2] if entity_type == "cart" else entity[3]
            valid = valid and occurred_at == expected_start
        else:
            prior_sequence, prior_state, prior_time = prior
            valid = (
                valid
                and sequence == prior_sequence + 1
                and occurred_at >= prior_time
                and previous_state == prior_state
                and event.get("event_type") == "status_changed"
                and new_state
                in allowed_transitions.get(entity_type, {}).get(prior_state, set())
            )
        reference_id = event.get("reference_id")
        if reference_id is not None:
            if entity_type == "cart":
                related_order = context.orders.get(reference_id)
                valid = valid and related_order is not None and related_order[2] == entity_id
            else:
                valid = valid and reference_id == context.orders[entity_id][2]
        if not valid:
            context.emit(
                "lifecycle_transition_invalid",
                "error",
                "lifecycle_events",
                event_id,
                [event_id, entity_id],
                "Lifecycle event has invalid ordering, timestamp, or state transition.",
                "lifecycle_transition_invalid",
            )
            continue
        histories[key] = (sequence, new_state, occurred_at)

    for (entity_type, entity_id), (_, final_state, _) in histories.items():
        if entity_type == "cart":
            expected_state = context.carts[entity_id][5]
        else:
            expected_state = context.orders[entity_id][4]
        if final_state != expected_state:
            context.emit(
                "lifecycle_final_state_mismatch",
                "error",
                "lifecycle_events",
                entity_id,
                [entity_id],
                "Latest lifecycle state does not match the entity's current state.",
                "lifecycle_final_state_mismatch",
            )


def validate_category_hierarchy(context: ValidationContext) -> None:
    for category_id, parent_id in context.categories.items():
        visited = {category_id}
        current = parent_id
        while isinstance(current, str) and current in context.categories:
            if current in visited:
                context.emit(
                    "category_hierarchy_cycle",
                    "error",
                    "categories",
                    category_id,
                    [category_id, current],
                    "Category parent links contain a cycle.",
                    "category_hierarchy_cycle",
                )
                break
            visited.add(current)
            current = context.categories[current]


def validate_session_and_event_chronology(context: ValidationContext) -> None:
    seen_events: set[bytes] = set()
    view_sequences: dict[str, dict[int, datetime]] = {}

    def check_duplicate_event(
        event_type: str, identity: list[Any], collection: str, entity_id: Any
    ) -> None:
        signature = hashlib.blake2b(
            json.dumps(
                [event_type, *identity],
                separators=(",", ":"),
                default=str,
            ).encode(),
            digest_size=16,
        ).digest()
        if signature in seen_events:
            context.emit(
                "duplicate_event",
                "error",
                collection,
                entity_id,
                [entity_id, *identity],
                f"Duplicate {event_type} event for the same entity and timestamp.",
                "duplicate_event",
            )
        else:
            seen_events.add(signature)

    for session_id, (customer_id, started_at, ended_at) in context.sessions.items():
        if started_at is not None and ended_at is not None and started_at >= ended_at:
            context.emit(
                "session_chronology_invalid",
                "error",
                "sessions",
                session_id,
                [session_id],
                "Session ended_at must be later than started_at.",
                "session_chronology_invalid",
            )
    for record in context.rows("page_views"):
        view_id = record.get("_id")
        session_id = record.get("session_id")
        product_id = record.get("product_id")
        occurred_at = record.get("occurred_at")
        session = context.sessions.get(session_id)
        if session and isinstance(occurred_at, datetime):
            _, started_at, ended_at = session
            if (started_at and occurred_at < started_at) or (
                ended_at and occurred_at > ended_at
            ):
                context.emit(
                    "page_view_outside_session",
                    "error",
                    "page_views",
                    view_id,
                    [view_id, session_id],
                    "Page view timestamp falls outside its session window.",
                    "page_view_outside_session",
                )
            if record.get("customer_id") != session[0]:
                context.emit(
                    "session_customer_mismatch",
                    "error",
                    "page_views",
                    view_id,
                    [view_id, session_id, record.get("customer_id")],
                    "Page-view customer does not match the session customer.",
                    "session_customer_mismatch",
                )
        if isinstance(session_id, str) and isinstance(product_id, str):
            sequence = record.get("sequence")
            if isinstance(sequence, int) and isinstance(occurred_at, datetime):
                by_sequence = view_sequences.setdefault(session_id, {})
                if sequence in by_sequence:
                    context.emit(
                        "duplicate_page_view_sequence",
                        "error",
                        "page_views",
                        view_id,
                        [view_id, session_id],
                        "Page-view sequence must be unique within its session.",
                        "duplicate_page_view_sequence",
                    )
                else:
                    by_sequence[sequence] = occurred_at
            key = (session_id, product_id)
            if isinstance(occurred_at, datetime):
                context.view_times[key] = min(
                    context.view_times.get(key, occurred_at), occurred_at
                )
            check_duplicate_event(
                "page_view", [session_id, product_id, occurred_at], "page_views", view_id
            )

    for session_id, sequence_times in view_sequences.items():
        ordered_times = [
            occurred_at
            for _, occurred_at in sorted(sequence_times.items())
        ]
        if any(
            current >= following
            for current, following in zip(ordered_times, ordered_times[1:])
        ):
            context.emit(
                "page_view_sequence_chronology_invalid",
                "error",
                "sessions",
                session_id,
                [session_id],
                "Page-view timestamps must strictly increase with sequence.",
                "page_view_sequence_chronology_invalid",
            )

    for collection, timestamp_field in (
        ("carts", "created_at"),
        ("orders", "placed_at"),
    ):
        for record in context.rows(collection):
            check_duplicate_event(
                collection[:-1],
                [record.get("session_id"), record.get(timestamp_field)],
                collection,
                record.get("_id"),
            )

    for order in context.rows("orders"):
        order_id = order.get("_id")
        session_id = order.get("session_id")
        placed_at = order.get("placed_at")
        session = context.sessions.get(session_id)
        if session and isinstance(placed_at, datetime):
            _, started_at, ended_at = session
            if (started_at and placed_at < started_at) or (
                ended_at and placed_at > ended_at
            ):
                context.emit(
                    "order_outside_session",
                    "error",
                    "orders",
                    order_id,
                    [order_id, session_id],
                    "Order timestamp falls outside its associated session.",
                    "order_outside_session",
                )

    for line in context.rows("order_lines"):
        order = context.orders.get(line.get("order_id"))
        if not order:
            continue
        _, session_id, _, placed_at, _, *_ = order
        view_at = context.view_times.get((session_id, line.get("product_id")))
        if not isinstance(view_at, datetime) or (
            isinstance(placed_at, datetime) and view_at >= placed_at
        ):
            context.emit(
                "purchase_before_session_view",
                "critical",
                "orders",
                line.get("order_id"),
                [line.get("order_id"), line.get("_id"), session_id, line.get("product_id")],
                "Purchase occurred without a valid preceding product view in its associated session.",
                "purchase_before_session_view",
            )


def validate_cart_and_order_arithmetic(context: ValidationContext) -> None:
    order_line_totals: dict[str, Decimal] = {}
    for line in context.rows("cart_lines"):
        line_id = line.get("_id")
        quantity = line.get("quantity")
        try:
            correct_total = _money(line["unit_price"]) * quantity == _money(
                line["line_total"]
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            correct_total = False
        if not correct_total:
            context.emit(
                "cart_line_arithmetic_invalid",
                "error",
                "cart_lines",
                line_id,
                [line_id, line.get("cart_id")],
                "Cart line total must equal quantity multiplied by unit price.",
                "cart_line_arithmetic_invalid",
            )
        cart = context.carts.get(line.get("cart_id"))
        added_at = line.get("added_at")
        if cart and isinstance(added_at, datetime):
            created_at, updated_at = cart[2], cart[3]
            if (created_at and added_at < created_at) or (
                updated_at and added_at > updated_at
            ):
                context.emit(
                    "cart_line_lifecycle_invalid",
                    "error",
                    "cart_lines",
                    line_id,
                    [line_id, line.get("cart_id")],
                    "Cart line timestamp falls outside its cart lifecycle.",
                    "cart_line_lifecycle_invalid",
                )
            view_at = context.view_times.get((cart[1], line.get("product_id")))
            if view_at is None or view_at >= added_at:
                context.emit(
                    "cart_before_session_view",
                    "error",
                    "cart_lines",
                    line_id,
                    [line_id, line.get("cart_id"), cart[1], line.get("product_id")],
                    "Cart line was added without an earlier product view in its session.",
                    "cart_before_session_view",
                )

    order_line_counts: dict[str, int] = {}
    for line in context.rows("order_lines"):
        line_id = line.get("_id")
        order_id = line.get("order_id")
        quantity = line.get("quantity")
        try:
            line_total = _money(line["line_total"])
            correct_total = (
                _money(line["unit_price"]) * quantity - _money(line["discount"])
                == line_total
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            line_total = Decimal(0)
            correct_total = False
        if not correct_total:
            context.emit(
                "order_line_arithmetic_invalid",
                "error",
                "order_lines",
                line_id,
                [line_id, order_id],
                "Order line total must equal quantity multiplied by unit price.",
                "order_line_arithmetic_invalid",
            )
        if isinstance(order_id, str):
            order_line_totals[order_id] = order_line_totals.get(order_id, Decimal(0)) + line_total
            order_line_counts[order_id] = order_line_counts.get(order_id, 0) + 1

    for order in context.rows("orders"):
        order_id = order.get("_id")
        if order_line_counts.get(order_id, 0) == 0:
            context.emit(
                "order_without_lines",
                "error",
                "orders",
                order_id,
                [order_id],
                "Order must contain at least one order line.",
                "order_without_lines",
            )
            continue
        try:
            subtotal = _money(order["subtotal"])
            discount = _money(order["discount_total"])
            tax = _money(order["tax_total"])
            shipping = _money(order["shipping_total"])
            total = _money(order["total"])
            valid = (
                subtotal == order_line_totals[order_id]
                and discount <= subtotal
                and total == subtotal - discount + tax + shipping
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            valid = False
        if not valid:
            context.emit(
                "order_arithmetic_invalid",
                "error",
                "orders",
                order_id,
                [order_id],
                "Order totals do not reconcile with its lines, discounts, tax and shipping.",
                "order_arithmetic_invalid",
            )


def validate_lifecycle_and_availability(context: ValidationContext) -> None:
    for product_id, product in context.products.items():
        status, available_from, available_to, _ = product
        if status not in {"active", "unavailable", "discontinued"} or (
            available_from is not None
            and available_to is not None
            and available_from > available_to
        ):
            context.emit(
                "product_lifecycle_invalid",
                "error",
                "products",
                product_id,
                [product_id],
                "Product status or availability window is invalid.",
                "product_lifecycle_invalid",
            )
    order_by_cart: dict[str, str] = {}
    for order_id, order in context.orders.items():
        _, session_id, cart_id, placed_at, status, *_ = order
        if status not in {"pending", "paid", "completed", "cancelled", "refunded"}:
            context.emit(
                "order_lifecycle_invalid",
                "error",
                "orders",
                order_id,
                [order_id],
                "Order has an invalid lifecycle status.",
                "order_lifecycle_invalid",
            )
        if isinstance(cart_id, str):
            if cart_id in order_by_cart:
                context.emit(
                    "cart_multiple_orders",
                    "error",
                    "orders",
                    order_id,
                    [order_id, order_by_cart[cart_id], cart_id],
                    "A cart is associated with more than one order.",
                    "cart_multiple_orders",
                )
            order_by_cart[cart_id] = order_id
        if session_id in context.sessions:
            session_customer = context.sessions[session_id][0]
            if order[0] != session_customer:
                context.emit(
                    "session_customer_mismatch",
                    "error",
                    "orders",
                    order_id,
                    [order_id, session_id],
                    "Order customer does not match its session customer.",
                    "session_customer_mismatch",
                )
        if status in {"completed", "cancelled", "refunded", "paid"} and cart_id is None:
            context.emit(
                "order_lifecycle_invalid",
                "error",
                "orders",
                order_id,
                [order_id],
                "Finalized order status requires an associated source cart.",
                "order_lifecycle_invalid",
            )
        if cart_id in context.carts:
            cart = context.carts[cart_id]
            if cart[5] != "converted" or cart[4] != placed_at:
                context.emit(
                    "order_cart_lifecycle_invalid",
                    "error",
                    "orders",
                    order_id,
                    [order_id, cart_id],
                    "Order and source cart do not have a consistent converted lifecycle.",
                    "order_cart_lifecycle_invalid",
                )
    for cart_id, cart in context.carts.items():
        customer_id, session_id, created_at, updated_at, converted_at, status = cart
        if created_at and updated_at and updated_at < created_at:
            context.emit(
                "cart_lifecycle_invalid",
                "error",
                "carts",
                cart_id,
                [cart_id],
                "Cart updated_at precedes created_at.",
                "cart_lifecycle_invalid",
            )
        if session_id in context.sessions:
            session_customer, session_start, session_end = context.sessions[session_id]
            if session_customer != customer_id:
                context.emit(
                    "session_customer_mismatch",
                    "error",
                    "carts",
                    cart_id,
                    [cart_id, session_id],
                    "Cart customer does not match its associated session.",
                    "session_customer_mismatch",
                )
            if created_at and (
                (session_start and created_at < session_start)
                or (session_end and created_at > session_end)
            ):
                context.emit(
                    "cart_outside_session",
                    "error",
                    "carts",
                    cart_id,
                    [cart_id, session_id],
                    "Cart creation falls outside its associated session.",
                    "cart_outside_session",
                )
        if status == "converted" and (converted_at is None or cart_id not in order_by_cart):
            context.emit(
                "cart_lifecycle_invalid",
                "error",
                "carts",
                cart_id,
                [cart_id],
                "Converted cart must have converted_at and exactly one related order.",
                "cart_lifecycle_invalid",
            )

    for record in context.rows("recommendations"):
        as_of = record.get("as_of_time")
        recommendation_id = record.get("_id")
        for item in record.get("items", ()):
            product_id = item.get("product_id")
            product = context.products.get(product_id)
            if not product:
                continue
            status, available_from, available_to, _ = product
            eligible = status == "active"
            if available_from is not None and as_of is not None:
                eligible = eligible and available_from <= as_of
            if available_to is not None and as_of is not None:
                eligible = eligible and as_of <= available_to
            if not eligible:
                context.emit(
                    "ineligible_product_recommendation",
                    "critical",
                    "recommendations",
                    recommendation_id,
                    [recommendation_id, product_id],
                    "Recommendation contains a product unavailable at as_of_time.",
                    "ineligible_product_recommendation",
                )


def validate_split_chronology(context: ValidationContext) -> None:
    windows = sorted(
        (
            (start, end, name, split_id)
            for split_id, (name, start, end) in context.splits.items()
            if isinstance(start, datetime) and isinstance(end, datetime)
        ),
        key=lambda item: item[0],
    )
    if [window[2] for window in windows] != ["train", "validation", "test"]:
        context.emit(
            "dataset_split_order_invalid",
            "critical",
            "dataset_splits",
            None,
            [window[3] for window in windows],
            "Dataset must define chronological train, validation and test windows.",
            "dataset_split_order_invalid",
        )
    for current, following in zip(windows, windows[1:]):
        if current[1] > following[0]:
            context.emit(
                "dataset_split_overlap",
                "critical",
                "dataset_splits",
                following[3],
                [current[3], following[3]],
                "Dataset split windows overlap or are not chronological.",
                "dataset_split_overlap",
            )
    event_counts = {name: 0 for name in context.split_names}
    for collection, timestamp_field in (
        ("page_views", "occurred_at"),
        ("carts", "created_at"),
        ("orders", "placed_at"),
    ):
        for record in context.rows(collection):
            occurred_at = record.get(timestamp_field)
            if not isinstance(occurred_at, datetime):
                continue
            expected = next(
                (
                    name
                    for start, end, name, _ in windows
                    if start <= occurred_at < end
                ),
                None,
            )
            if expected is None:
                context.emit(
                    "event_outside_dataset_splits",
                    "error",
                    collection,
                    record.get("_id"),
                    [record.get("_id")],
                    "Event timestamp is not covered by a dataset split.",
                    "event_outside_dataset_splits",
                )
            else:
                event_counts[expected] += 1
    for split_id, (name, _, _) in context.splits.items():
        matching = next(
            (
                record
                for record in context.rows("dataset_splits")
                if record.get("_id") == split_id
            ),
            None,
        )
        if matching and matching.get("event_count") != event_counts.get(name, 0):
            context.emit(
                "dataset_split_event_count_mismatch",
                "error",
                "dataset_splits",
                split_id,
                [split_id],
                "Stored event_count does not match the events in the split window.",
                "dataset_split_event_count_mismatch",
            )
    for record in context.rows("ground_truth_labels"):
        split_id = record.get("dataset_split_id")
        occurred_at = record.get("occurred_at")
        split = context.splits.get(split_id)
        if split and isinstance(occurred_at, datetime):
            name, start, end = split
            if name == "train" or not (start <= occurred_at < end):
                context.emit(
                    "ground_truth_split_invalid",
                    "critical",
                    "ground_truth_labels",
                    record.get("_id"),
                    [record.get("_id"), record.get("source_event_id"), split_id],
                    "Ground-truth event is assigned outside its held-out split window.",
                    "ground_truth_split_invalid",
                )
        source_id = record.get("source_event_id")
        source_order_id = (
            context.order_line_orders.get(source_id)
            if isinstance(source_id, str)
            else None
        )
        if source_order_id is not None:
            order = context.orders.get(source_order_id)
            if order and order[4] != "completed":
                context.emit(
                    "ground_truth_outcome_invalid",
                    "error",
                    "ground_truth_labels",
                    record.get("_id"),
                    [record.get("_id"), source_id, source_order_id],
                    "Purchase ground-truth label must come from a completed order.",
                    "ground_truth_outcome_invalid",
                )
    for model_run in context.rows("model_runs"):
        split_id = model_run.get("training_split_id")
        split = context.splits.get(split_id)
        cutoff = model_run.get("training_cutoff")
        if split and (
            split[0] != "train"
            or (
                isinstance(cutoff, datetime)
                and isinstance(split[2], datetime)
                and cutoff > split[2]
            )
        ):
            context.emit(
                "model_training_split_invalid",
                "critical",
                "model_runs",
                model_run.get("_id"),
                [model_run.get("_id"), split_id],
                "Model training must use only the train split and its time boundary.",
                "model_training_split_invalid",
            )
    for result in context.rows("evaluation_results"):
        split = context.splits.get(result.get("dataset_split_id"))
        if split and split[0] not in {"validation", "test"}:
            context.emit(
                "evaluation_split_invalid",
                "error",
                "evaluation_results",
                result.get("_id"),
                [result.get("_id"), result.get("dataset_split_id")],
                "Evaluation must use a held-out validation or test split.",
                "evaluation_split_invalid",
            )

    train_id = next(
        (split_id for split_id, (name, _, _) in context.splits.items() if name == "train"),
        None,
    )
    for fixture in context.rows("anomaly_fixtures"):
        for wrapped in fixture.get("fixture_records", ()):
            assigned_id = wrapped.get("assigned_split_id")
            document = wrapped.get("document", {})
            occurred_at = document.get("placed_at", document.get("occurred_at"))
            if assigned_id is None or not isinstance(occurred_at, datetime):
                continue
            expected_id = next(
                (
                    split_id
                    for split_id, (_, start, end) in context.splits.items()
                    if isinstance(start, datetime)
                    and isinstance(end, datetime)
                    and start <= occurred_at < end
                ),
                None,
            )
            if assigned_id == train_id and expected_id != train_id:
                context.emit(
                    "train_test_leakage",
                    "critical",
                    "dataset_splits",
                    fixture.get("anomaly_id"),
                    [fixture.get("anomaly_id"), document.get("_id"), assigned_id],
                    "Held-out test event is incorrectly assigned to the train split.",
                    "train_test_leakage",
                )


def validate_anomaly_fixtures(context: ValidationContext) -> None:
    for fixture in context.rows("anomaly_fixtures"):
        issue_type = fixture.get("issue_type")
        entity_type = fixture.get("entity_type", "unknown")
        entity_id = fixture.get("entity_id")
        if issue_type == "purchase_before_session_view":
            records = {
                wrapped.get("collection"): wrapped.get("document", {})
                for wrapped in fixture.get("fixture_records", ())
            }
            order = records.get("orders", {})
            line = records.get("order_lines", {})
            view_at = context.view_times.get(
                (order.get("session_id"), line.get("product_id"))
            )
            if view_at is None or order.get("placed_at") <= view_at:
                context.emit(
                    "purchase_before_session_view",
                    "critical",
                    "orders",
                    entity_id,
                    [
                        fixture.get("anomaly_id"),
                        order.get("_id"),
                        line.get("_id"),
                        order.get("session_id"),
                        line.get("product_id"),
                    ],
                    "Purchase fixture precedes a valid product view in its session.",
                    "purchase_before_session_view",
                )
            continue
        if issue_type == "missing_product_category":
            product = next(
                (
                    wrapped.get("document", {})
                    for wrapped in fixture.get("fixture_records", ())
                    if wrapped.get("collection") == "products"
                ),
                {},
            )
            category_id = product.get("category_id")
            if context.id_exists("categories", category_id):
                continue
            context.emit(
                "missing_product_category",
                "error",
                entity_type,
                entity_id,
                [fixture.get("anomaly_id"), entity_id, category_id],
                "Product category_id does not reference an existing category.",
                "missing_product_category",
            )
        elif issue_type == "ineligible_product_recommendation":
            for wrapped in fixture.get("fixture_records", ()):
                if wrapped.get("collection") != "recommendations":
                    continue
                recommendation = wrapped.get("document", {})
                for item in recommendation.get("items", ()):
                    product = context.products.get(item.get("product_id"))
                    if product and product[0] != "active":
                        context.emit(
                            "ineligible_product_recommendation",
                            "critical",
                            "recommendations",
                            recommendation.get("_id"),
                            [fixture.get("anomaly_id"), recommendation.get("_id"), item.get("product_id")],
                            "Recommendation fixture contains a discontinued or unavailable product.",
                            "ineligible_product_recommendation",
                        )
