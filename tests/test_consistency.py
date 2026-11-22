from eval.consistency import consistency_share


def cases():
    out = []
    for i, carrier in enumerate(["AA", "AA", "DL", "DL", "UA", "UA"]):
        out.append(
            {
                "case_id": f"c{i}",
                "carrier": carrier,
                "flight_date": "2024-07-0" + str(i + 1),
            }
        )
    return out


def decisions(bad="c3"):
    d = {c["case_id"]: ["no_refund"] * 10 for c in cases()}
    d[bad] = ["no_refund"] * 9 + ["refund"]
    return d


def test_share_five_sixths_with_interval():
    # @criterion C1
    s = consistency_share(cases(), decisions())
    assert s["share"] == 5 / 6
    assert 0 <= s["low"] <= s["high"] <= 1
    assert (s["low"], s["high"]) == (0.5, 1.0)  # seed 20261118, 10,000 resamples
    assert s["clusters"] == 3 and s["cases"] == 6


def test_same_on_every_run_with_the_seed():
    # @criterion C1
    a = consistency_share(cases(), decisions())
    b = consistency_share(cases(), decisions())
    assert a == b


def test_all_consistent_is_one():
    # @criterion C1
    d = {c["case_id"]: ["escalate"] * 10 for c in cases()}
    s = consistency_share(cases(), d)
    assert (s["share"], s["low"], s["high"]) == (1, 1, 1)


def test_paired_draw_serves_every_agent():
    # @criterion C1
    from eval.consistency import cluster_draws, paired_difference

    keys = ["AA-2024-07", "DL-2024-07", "DL-2024-08"]
    draws = cluster_draws(keys, resamples=1000, seed=7)
    assert draws == cluster_draws(keys, resamples=1000, seed=7)
    assert all(len(d) == 3 and set(d) <= set(keys) for d in draws)
    # two agents with different values per cluster but the same value everywhere in their
    # difference: a paired draw gives that difference in every resample; two independent
    # draws would not
    a = {"AA-2024-07": (2, 2), "DL-2024-07": (1, 2), "DL-2024-08": (0, 2)}
    b = {"AA-2024-07": (1, 2), "DL-2024-07": (0, 2), "DL-2024-08": (-1, 2)}
    d = paired_difference(a, b, draws)
    assert (d["difference"], d["low"], d["high"]) == (0.5, 0.5, 0.5)
    assert d["resamples"] == 1000
    # the same agent against itself: zero in every resample
    same = paired_difference(a, a, draws)
    assert (same["low"], same["high"]) == (0, 0)


def test_paired_draw_matches_the_one_agent_bootstrap():
    # @criterion C1
    from eval.consistency import cluster_draws, consistency_share, percentile_interval

    # the paired draw is consistency_share's draw: same seed, same clusters, same interval
    s = consistency_share(cases(), decisions())
    groups = {"AA-2024-07": (2, 2), "DL-2024-07": (1, 2), "UA-2024-07": (2, 2)}
    shares = [
        sum(groups[k][0] for k in d) / sum(groups[k][1] for k in d)
        for d in cluster_draws(list(groups))
    ]
    assert percentile_interval(shares) == (s["low"], s["high"])
