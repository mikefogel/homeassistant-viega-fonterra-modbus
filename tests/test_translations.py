"""Guard against translation files drifting apart or falling out of sync
with the error keys the config/options flow actually sets.

spec.md 6a requires every config/options flow error message to be
translated in every supported language: a raw error key like
"invalid_host" shown to the user instead of a translated sentence is
exactly the kind of gap this file is meant to catch.
"""

import json
from pathlib import Path

TRANSLATIONS_DIR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "viega_fonterra_modbus"
    / "translations"
)

# Every error key `config_flow.py` can put into `errors[...]` for each step.
EXPECTED_USER_ERRORS = {"invalid_host", "required", "invalid_port", "invalid_timeout", "cannot_connect"}
EXPECTED_INIT_ERRORS = EXPECTED_USER_ERRORS | {"invalid_polling_interval"}


def _load(language: str) -> dict:
    return json.loads((TRANSLATIONS_DIR / f"{language}.json").read_text(encoding="utf-8"))


def _flatten(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _flatten(value, full_key)
        else:
            keys.add(full_key)
    return keys


def test_translation_files_are_valid_json():
    for language in ("de", "en"):
        _load(language)  # raises if malformed


def test_de_and_en_expose_exactly_the_same_translation_keys():
    de_keys = _flatten(_load("de"))
    en_keys = _flatten(_load("en"))

    assert de_keys == en_keys, (
        f"only in de: {sorted(de_keys - en_keys)}, "
        f"only in en: {sorted(en_keys - de_keys)}"
    )


def test_every_config_flow_error_key_is_translated_in_both_languages():
    for language in ("de", "en"):
        data = _load(language)
        user_errors = set(data["config"]["step"]["user"].get("errors", {}))
        init_errors = set(data["config"]["step"]["init"].get("errors", {}))

        assert user_errors == EXPECTED_USER_ERRORS, (
            f"{language}.json config.step.user.errors: expected "
            f"{EXPECTED_USER_ERRORS}, got {user_errors}"
        )
        assert init_errors == EXPECTED_INIT_ERRORS, (
            f"{language}.json config.step.init.errors: expected "
            f"{EXPECTED_INIT_ERRORS}, got {init_errors}"
        )
