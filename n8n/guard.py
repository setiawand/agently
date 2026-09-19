"""Gate keamanan untuk perubahan workflow yang diusulkan agent -- deterministik, tanpa LLM.

Update hanya boleh auto-apply jika TIDAK: menghapus node, mengubah credential,
menambah/mengubah/menghapus node trigger. Selain itu -> escalate (manusia yang apply).
"""

_TRIGGER_HINTS = ("trigger", "webhook", "cron", "schedule")


def _is_trigger(node: dict) -> bool:
    node_type = str(node.get("type", "")).lower()
    return any(h in node_type for h in _TRIGGER_HINTS)


def check_update(old_nodes: list[dict], new_nodes: list[dict]) -> tuple[bool, str]:
    """Return (aman_untuk_auto_apply, alasan)."""
    old = {n.get("name"): n for n in old_nodes}
    new = {n.get("name"): n for n in new_nodes}

    removed = sorted(str(k) for k in old.keys() - new.keys())
    if removed:
        return False, f"menghapus/mengganti nama node: {', '.join(removed)}"

    for name, n in new.items():
        o = old.get(name)
        if o is None:
            if _is_trigger(n):
                return False, f"menambah node trigger baru: {name}"
            continue
        if o.get("credentials") != n.get("credentials"):
            return False, f"mengubah credential pada node: {name}"
        if _is_trigger(o) and o != n:
            return False, f"mengubah node trigger: {name}"
        if o.get("type") != n.get("type"):
            return False, f"mengubah tipe node: {name}"
    return True, "perubahan minimal, tidak menyentuh credential/trigger/penghapusan node"


