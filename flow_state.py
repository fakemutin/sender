"""Persistent add-account flow stored in bot_state.json (survives restarts)."""

from storage import load_state, save_state


def get_flow(user_id: int) -> dict | None:
    flows = load_state().get("flows", {})
    item = flows.get(str(user_id))
    if not item:
        return None
    return item


def set_flow(user_id: int, step: str, data: dict | None = None) -> None:
    state = load_state()
    flows = state.setdefault("flows", {})
    current = flows.get(str(user_id), {})
    if data is not None:
        current["data"] = {**current.get("data", {}), **data}
    else:
        current.setdefault("data", {})
    current["step"] = step
    flows[str(user_id)] = current
    state["flows"] = flows
    save_state(state)


def flow_data(user_id: int) -> dict:
    flow = get_flow(user_id)
    return flow.get("data", {}) if flow else {}


def clear_flow(user_id: int) -> None:
    state = load_state()
    flows = state.get("flows", {})
    flows.pop(str(user_id), None)
    state["flows"] = flows
    save_state(state)


def flow_step(user_id: int) -> str | None:
    flow = get_flow(user_id)
    return flow.get("step") if flow else None
