from splendor.utils.text_integrity import sanitize_generated_text


def test_sanitize_generated_text_repairs_latin1_decoded_utf8_when_controls_present() -> None:
    text = sanitize_generated_text("Evidence â\x80\x94 says â\x80\x9cnaturalnessâ\x80\x9d.")

    assert text == "Evidence — says “naturalness”."


def test_sanitize_generated_text_does_not_rewrite_literal_mojibake_examples() -> None:
    text = sanitize_generated_text("The literal sequence â€” is documented here.")

    assert text == "The literal sequence â€” is documented here."


def test_sanitize_generated_text_removes_controls_that_are_not_repairable_mojibake() -> None:
    text = sanitize_generated_text("alpha\x07 beta\x1a\x7f gamma")

    assert text == "alpha beta gamma"
