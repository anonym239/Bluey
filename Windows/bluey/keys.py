"""Der OpenAI-Schlüssel (optional) liegt in der Windows-Anmeldeinformationsverwaltung, nie im Projektordner.

Ohne keyring (z. B. bei Tests) landet er in einer privaten Datei im Benutzerprofil.
"""
import json
import os

from .config import data_dir

_SERVICE = "Bluey"
_cache = {}


def _file():
    return os.path.join(data_dir(), "keys.json")


def get(name="openai"):
    if name in _cache:
        return _cache[name] or None
    value = None
    try:
        import keyring
        value = keyring.get_password(_SERVICE, name)
    except Exception:
        try:
            with open(_file(), encoding="utf-8") as f:
                value = json.load(f).get(name)
        except (OSError, ValueError):
            value = None
    _cache[name] = value or ""
    return value or None


def set(name, value):
    value = (value or "").strip()
    _cache[name] = value
    try:
        import keyring
        if value:
            keyring.set_password(_SERVICE, name, value)
        else:
            try:
                keyring.delete_password(_SERVICE, name)
            except Exception:
                pass
        return
    except Exception:
        pass
    try:
        with open(_file(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    with open(_file(), "w", encoding="utf-8") as f:
        json.dump(data, f)
