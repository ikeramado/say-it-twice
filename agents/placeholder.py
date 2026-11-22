"""Fixed-answer agent at a zero price: runs the runner end to end with no model."""

MODEL = "placeholder"
CALLS_PER_CASE = 1


def prompt(case):
    return f"Decide the refund for flight {case['carrier']}{case['flight_number']}: {case['message']['text']}"


def run(case, gate):
    p = prompt(case)
    answer = gate.call(p)
    return {
        "decision": answer,
        "explanation": "placeholder: fixed answer",
        "trace": [{"prompt": p, "answer": answer}],
    }
