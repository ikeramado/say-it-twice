"""What each airline policy version says about a delay, as the minimum arrival delay (minutes)
that earns a refund. Read from the saved clauses (rules/policies/*.yaml):

- Delta, up to DL-2024-10-28 and DL-2025-10-08: "delay of greater than 120 minutes" -> 121.
- Delta DL-2026-08-18: "arrive 180 minutes or more after" -> 180.
- American up to AA-2024-07-25: "delays your arrival more than 4 hours" -> 241.
- American from AA-2024-10-28: "delayed for 3 or more hours (domestic)" -> 180.

Cancelled flights are refunded under every version, so only delays can differ.
"""

REFUND_IF_DELAY_AT_LEAST = {
    "DL-2023-06-22": 121,
    "DL-2024-03-12": 121,
    "DL-2024-10-28": 121,
    "DL-2025-10-08": 121,
    "DL-2026-08-18": 180,
    "AA-2023-10-10": 241,
    "AA-2024-04-12": 241,
    "AA-2024-07-25": 241,
    "AA-2024-10-28": 180,
    "AA-2025-04-04": 180,
    "AA-2025-06-27": 180,
    "AA-2026-03-02": 180,
    "AA-2026-05-12": 180,
    "AA-2026-08-13": 180,
}


def policy_answer(policy_id: str, delay_min: int) -> str:
    return "refund" if delay_min >= REFUND_IF_DELAY_AT_LEAST[policy_id] else "no_refund"
