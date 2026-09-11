from veritas.self_improve import is_allowed


def test_can_edit_normal_modules():
    assert is_allowed("veritas/reasoner.py")


def test_cannot_edit_guardrails_or_tests():
    assert not is_allowed("veritas/self_improve.py")
    assert not is_allowed("tests/test_memory.py")


def test_cannot_escape_project():
    assert not is_allowed("veritas/../../etc/passwd")
    assert not is_allowed("/etc/passwd")
    assert not is_allowed("setup.sh")
