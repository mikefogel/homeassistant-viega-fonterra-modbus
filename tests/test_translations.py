"""Guard against translation files drifting apart or falling out of sync
with the error keys the config/options flow actually sets.

spec.md 6a requires every config/options flow error message to be
translated in every supported language: a raw error key like
"invalid_host" shown to the user instead of a translated sentence is
exactly the kind of gap this file is meant to catch.

Home Assistant's translation loader (`homeassistant/helpers/translation.py`)
keys its cache by top-level category, and a `ConfigFlow` and an
`OptionsFlow` are two different categories ("config" and "options" -
confirmed against every bundled core integration that ships both, e.g.
`homeassistant/components/airq/strings.json`): an options flow's strings
under `config.step.init` are never found by Home Assistant's own options-
flow translation lookup, which asks for the "options" category. This
previously went unnoticed because nothing here checked the options flow's
strings against the schema Home Assistant's translation loader actually
reads for it - it checked `config.step.init` (the wrong place) instead of
`options.step.init` (see git history for the same mistake this file made).
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

        assert user_errors == EXPECTED_USER_ERRORS, (
            f"{language}.json config.step.user.errors: expected "
            f"{EXPECTED_USER_ERRORS}, got {user_errors}"
        )


def test_every_options_flow_error_key_is_translated_in_both_languages():
    """The options flow (`ViegaFonterraOptionsFlow.async_step_init`) is a
    different translation category from the config flow - its strings must
    live under the top-level "options" key, not nested inside "config"
    (see this module's docstring)."""
    for language in ("de", "en"):
        data = _load(language)
        assert "config" not in data.get("options", {}), (
            f"{language}.json: options.config should not exist - the "
            "options flow's own strings belong directly under options.step"
        )
        init_errors = set(data["options"]["step"]["init"].get("errors", {}))

        assert init_errors == EXPECTED_INIT_ERRORS, (
            f"{language}.json options.step.init.errors: expected "
            f"{EXPECTED_INIT_ERRORS}, got {init_errors}"
        )


def test_config_step_init_is_not_used_for_the_options_flow():
    """Regression guard: the options flow's strings must not be placed
    under config.step.init, where Home Assistant's translation loader for
    an OptionsFlow (category "options") will never look."""
    for language in ("de", "en"):
        data = _load(language)
        assert "init" not in data["config"]["step"], (
            f"{language}.json: config.step.init should not exist - move "
            "its content to options.step.init"
        )


def test_every_exception_translation_key_used_in_code_is_translated():
    """spec.md 10a: every translation key passed to `invalid_request()` or
    `action_failed()` must have a message in every language, and no
    message may be left over without a user in the code."""
    import re

    source_dir = TRANSLATIONS_DIR.parent
    used: set[str] = set()
    for path in source_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        used |= set(
            re.findall(r'(?:invalid_request|action_failed)\(\s*"([a-z_]+)"', text)
        )
    assert used, "expected at least one translated exception in the code"

    for language in ("de", "en"):
        exceptions = _load(language).get("exceptions", {})
        assert set(exceptions) == used, (
            f"{language}.json exceptions: missing {sorted(used - set(exceptions))}, "
            f"unused {sorted(set(exceptions) - used)}"
        )
        for key, value in exceptions.items():
            assert value.get("message"), f"{language}.json exceptions.{key} has no message"


def test_exception_messages_use_the_same_placeholders_in_every_language():
    import re

    de = _load("de").get("exceptions", {})
    en = _load("en").get("exceptions", {})
    for key in de:
        de_placeholders = set(re.findall(r"\{(\w+)\}", de[key]["message"]))
        en_placeholders = set(re.findall(r"\{(\w+)\}", en[key]["message"]))
        assert de_placeholders == en_placeholders, key
