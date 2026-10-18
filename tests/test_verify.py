from lore_lite.verify import verify_quote


def test_quote_verification_normalizes_case_and_whitespace():
    assert verify_quote("Use   parameterized\nqueries.", "The policy says USE parameterized queries.")


def test_quote_verification_rejects_invented_quote():
    assert not verify_quote("Always encrypt every record.", "Use parameterized queries.")
