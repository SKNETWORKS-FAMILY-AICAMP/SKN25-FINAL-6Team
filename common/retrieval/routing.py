from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


StateLike = Mapping[str, Any] | Any


def state_value(state: StateLike, field_name: str, default: Any = None) -> Any:
    """Read a state field from either a mapping or an object-like state model."""
    if isinstance(state, Mapping):
        return state.get(field_name, default)
    return getattr(state, field_name, default)


def route_by_mapping(
    state: StateLike,
    *,
    field_name: str,
    route_map: Mapping[str, str],
    default_route: str,
) -> str:
    """Map one state field to a concrete node name with a default fallback."""
    return route_map.get(str(state_value(state, field_name, "")), default_route)


def require_state_route(
    state: StateLike,
    *,
    field_names: Sequence[str],
    allowed_values: Sequence[str],
    route_name: str,
) -> str:
    """Return the first allowed state value across one or more fallback fields."""
    allowed = set(allowed_values)
    for field_name in field_names:
        resolved = state_value(state, field_name)
        if resolved is None:
            continue
        if resolved not in allowed:
            raise ValueError(f"{route_name} has unexpected value: {resolved!r}")
        return str(resolved)
    raise ValueError(f"{route_name} is required for routing")


def route_after_retry_limit(
    state: StateLike,
    *,
    retry_count_field: str = "retry_count",
    max_retries_field: str = "max_retries",
    urgent_flag_field: str | None = None,
    urgent_flag_value: str = "urgent_alert",
    default_max_retries: int = 3,
    retry_route: str,
    exhausted_route: str,
) -> str:
    """Return the retry route until retries are exhausted or an urgent flag is set."""
    retry_count = int(state_value(state, retry_count_field, 0) or 0)
    max_retries_raw = state_value(state, max_retries_field, default_max_retries)
    max_retries = default_max_retries if max_retries_raw is None else int(max_retries_raw)

    if urgent_flag_field and state_value(state, urgent_flag_field) == urgent_flag_value:
        return exhausted_route
    if retry_count >= max_retries:
        return exhausted_route
    return retry_route


def route_after_safety(
    state: StateLike,
    *,
    category_router: Callable[[StateLike], str],
    max_masking_retry: int,
    max_safety_retry: int,
    retry_node: str,
    final_node: str,
    safety_action_field: str = "safety_action",
    retry_count_field: str = "retry_count",
    safety_passed_field: str = "safety_passed",
    masking_action: str = "MASKING",
    terminal_actions: Sequence[str] = ("BLOCK_RESPONSE", "SAFE_FALLBACK", "REVIEW_QUEUE"),
) -> str:
    """Apply the shared safety retry policy used by graph routing layers."""
    safety_action = state_value(state, safety_action_field)
    retry_count = int(state_value(state, retry_count_field, 0) or 0)

    if safety_action == masking_action:
        if retry_count <= max_masking_retry:
            return retry_node
        return final_node
    if safety_action in set(terminal_actions):
        return final_node
    if bool(state_value(state, safety_passed_field, False)):
        return final_node
    if retry_count >= max_safety_retry:
        return final_node
    return category_router(state)
