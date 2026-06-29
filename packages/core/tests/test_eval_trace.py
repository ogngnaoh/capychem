from capychem.eval.trace import GenerationTrace, trace_to_dict


def test_generation_trace_serializes_to_json_safe_dict() -> None:
    t = GenerationTrace(
        generation=3,
        summary_top=[("c1ccccc1", 0.9)],
        summary_bottom=[("CCC", 0.1)],
        recent_top10_means=[0.5, 0.7, 0.8],
        prior_structured={"focus": "logP", "avoid": ["amide"]},
        analyzer_raw="Focus on logP. {\"focus\": \"logP\", \"avoid\": [\"amide\"]}",
        analyzer_structured={"focus": "logP", "avoid": ["amide"]},
        prompt_used="...conditioned...",
        prompt_unconditioned="...plain...",
    )
    d = trace_to_dict(t)
    import json
    json.dumps(d)  # must not raise
    assert d["generation"] == 3
    assert d["analyzer_structured"] == {"focus": "logP", "avoid": ["amide"]}
    assert d["summary_top"] == [["c1ccccc1", 0.9]]  # tuples -> lists through JSON-safe dict
