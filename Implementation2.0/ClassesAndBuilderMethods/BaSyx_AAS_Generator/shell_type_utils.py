import re
import yaml
from pathlib import Path

TYPE_SHELLS_DIR = Path(__file__).parent / "shell_templates"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _build_token_context(merged: dict) -> dict:
    ctx = {}
    mat_props = merged.get("submodels", {}).get("Properties", {}).get("MaterialProperties", {})
    ctx.update(mat_props)
    return ctx


def _resolve_pattern(pattern: str, ctx: dict) -> str:
    def replace(m):
        return str(ctx.get(m.group(1), ""))
    result = re.sub(r"\{(\w+)\}", replace, pattern)
    result = re.sub(r"[-_\s]{2,}", lambda m: m.group(0)[0], result)
    return result.strip("-_ ")


def _is_lang_map(val: dict) -> bool:
    return bool(val) and all(
        isinstance(k, str) and len(k) == 2 and isinstance(v, str)
        for k, v in val.items()
    )


def _apply_derived(target: dict, derived: dict, ctx: dict) -> None:
    for key, val in derived.items():
        if isinstance(val, dict):
            if _is_lang_map(val):
                target[key] = [
                    {"language": lang, "text": _resolve_pattern(pattern, ctx)}
                    for lang, pattern in val.items()
                ]
            else:
                _apply_derived(target.setdefault(key, {}), val, ctx)
        elif isinstance(val, str):
            target[key] = _resolve_pattern(val, ctx)


def resolve_type(preset: dict) -> dict:
    """
    If preset has 'type', load the type shell, merge preset delta on top,
    then resolve any 'derived' patterns using MaterialProperties as token context.
    Presets without 'type' (using 'shell' directly) are returned unchanged.
    """
    type_name = preset.get("type")
    if not type_name:
        return preset
    path = TYPE_SHELLS_DIR / f"{type_name}.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            type_shell = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Type shell '{type_name}' not found at {path}. "
            f"Check the 'type:' field in your preset."
        )
    merged = _deep_merge(type_shell, {k: v for k, v in preset.items() if k != "type"})
    merged["shell"] = type_shell["shell"]
    derived = type_shell.get("derived", {})
    if derived:
        ctx = _build_token_context(merged)
        _apply_derived(merged.setdefault("submodels", {}), derived, ctx)
    merged.pop("derived", None)
    return merged
