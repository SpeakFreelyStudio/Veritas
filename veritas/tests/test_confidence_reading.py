import pytest

from veritas.reasoner import ANSWER_SYSTEM, VERIFY_SYSTEM, _clamp


@pytest.mark.parametrize("given, expected", [
    (0.85, 0.85), ("0.85", 0.85), (85, 0.85), ("85%", 0.85), ("85 percent", 0.85),
    (1, 1.0), (0, 0.0), (150, 1.0), (-2, 0.0), ("unsure", 0.0), (None, 0.0), (True, 0.0),
])
def test_confidence_read_correctly_however_written(given, expected):
    assert _clamp(given) == pytest.approx(expected)


def test_instructions_contain_no_example_score_to_copy():
    for prompt in (ANSWER_SYSTEM, VERIFY_SYSTEM):
        assert '"confidence":0.0' not in prompt and '"adjusted_confidence":0.0' not in prompt
