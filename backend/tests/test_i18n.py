from app.core.i18n import t, map_telegram_lang, TRANSLATIONS, SUPPORTED_LANGS, DEFAULT_LANG


class TestMapTelegramLang:
    def test_known_codes(self):
        assert map_telegram_lang("uk") == "uk"
        assert map_telegram_lang("ru") == "ru"
        assert map_telegram_lang("en") == "en"

    def test_region_suffix_stripped(self):
        assert map_telegram_lang("en-US") == "en"
        assert map_telegram_lang("ru-RU") == "ru"

    def test_unknown_and_none_default_en(self):
        assert map_telegram_lang("de") == "en"
        assert map_telegram_lang(None) == "en"
        assert map_telegram_lang("") == "en"


class TestTranslate:
    def test_returns_language_string(self):
        assert t("text_saved", "en") == "✅ Saved!"
        assert t("text_saved", "uk") == "✅ Записано!"

    def test_interpolates(self):
        assert "5" in t("bake_start", "en", count=5)

    def test_falls_back_to_default_for_unknown_language(self):
        assert t("text_saved", "xx") == TRANSLATIONS[DEFAULT_LANG]["text_saved"]

    def test_falls_back_to_key_for_unknown_key(self):
        assert t("no_such_key", "en") == "no_such_key"

    def test_all_languages_have_same_keys(self):
        base = set(TRANSLATIONS[DEFAULT_LANG].keys())
        for lang in SUPPORTED_LANGS:
            assert set(TRANSLATIONS[lang].keys()) == base, f"{lang} key mismatch"
