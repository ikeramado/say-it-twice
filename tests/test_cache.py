from llm import Gate

PRICES = {"m": {"input": 1.0, "cached_input": 0.1, "output": 1.0}}


def test_repeat_reads_cache(tmp_path):
    # @criterion C9
    calls = []

    def p(model, prompt, n):
        calls.append(prompt)
        return "ans", 5, 5

    g = Gate(tmp_path / "r", "m", PRICES, 10.0, tmp_path / "cache", p)
    assert g.call("q", 0) == "ans"
    assert g.call("q", 0) == "ans"
    assert len(calls) == 1
    g.call("q", 1)  # another sample index is another key
    assert len(calls) == 2
    g2 = Gate(tmp_path / "r2", "m", PRICES, 10.0, tmp_path / "cache", p)
    assert g2.call("q", 0) == "ans" and len(calls) == 2
