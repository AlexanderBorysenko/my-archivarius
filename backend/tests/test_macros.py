"""Tests for the content-macro foundation, validators, and processor."""

import base64
import json

import app.services.macros  # ensures gallery/figure specs are registered regardless of import order
from app.services.macros.gallery import _validate_gallery
from app.services.macros.figure import _validate_figure
from app.services.macros.process import process_macros, _decode_payload, _encode


CTX = {"att_a": "photo", "att_b": "photo", "att_v": "video"}


class TestGalleryValidate:
    def test_keeps_present_photos_dedup(self):
        out = _validate_gallery({"images": ["att_a", "att_b", "att_a", "att_v", "att_x"], "caption": " hi "}, CTX)
        assert out == {"images": ["att_a", "att_b"], "caption": "hi"}

    def test_none_when_no_valid_images(self):
        assert _validate_gallery({"images": ["att_v", "att_x"]}, CTX) is None

    def test_caption_optional_and_capped(self):
        out = _validate_gallery({"images": ["att_a"], "caption": "x" * 500}, CTX)
        assert len(out["caption"]) == 300
        out2 = _validate_gallery({"images": ["att_a"]}, CTX)
        assert out2["caption"] == ""


class TestFigureValidate:
    def test_basic(self):
        out = _validate_figure({"image": "att_a", "width": 33, "align": "left", "caption": "c"}, CTX)
        assert out == {"image": "att_a", "width": 33, "align": "left", "caption": "c"}

    def test_rejects_non_photo_or_missing(self):
        assert _validate_figure({"image": "att_v"}, CTX) is None
        assert _validate_figure({"image": "att_x"}, CTX) is None
        assert _validate_figure({}, CTX) is None

    def test_snaps_width_and_align_defaults(self):
        out = _validate_figure({"image": "att_a", "width": 40, "align": "weird"}, CTX)
        assert out["width"] == 33  # 40 snaps to nearest of {25,33,50,100}
        assert out["align"] == "left"

    def test_width_100_forces_full(self):
        out = _validate_figure({"image": "att_a", "width": 100, "align": "left"}, CTX)
        assert out["align"] == "full"


class TestProcess:
    def test_raw_json_normalized_to_base64_and_used_collected(self):
        raw = '<!-- macro:gallery {"images":["att_a","att_b"],"caption":"hi"} -->'
        content, used = process_macros(f"before\n{raw}\nafter", CTX)
        assert used == {"att_a", "att_b"}
        assert "before" in content and "after" in content
        # block rewritten to base64 form
        import re
        m = re.search(r"<!-- macro:gallery (\S+) -->", content)
        assert m and _decode_payload(m.group(1)) == {"images": ["att_a", "att_b"], "caption": "hi"}

    def test_drops_unknown_and_invalid(self):
        content, used = process_macros(
            '<!-- macro:bogus {"x":1} --> <!-- macro:gallery {"images":["att_v"]} -->', CTX
        )
        assert used == set()
        assert "macro:bogus" not in content
        assert "macro:gallery" not in content

    def test_figure_used_shortcode(self):
        content, used = process_macros('<!-- macro:figure {"image":"att_a"} -->', CTX)
        assert used == {"att_a"}
