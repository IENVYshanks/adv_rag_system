from __future__ import annotations

import logfire

from app.evals.guardrails_eval import compute_guardrails_metrics
from app.guardrails import guard


def evaluate_guardrails(samples: list[dict]) -> dict:
    """Evaluate the production guard against caller-provided test cases."""
    results = []

    with logfire.span("In-process guardrails evaluation", total=len(samples)):
        for original_sample in samples:
            sample = dict(original_sample)
            blocked, response = guard(sample["input"])
            expected = sample["expected_blocked"]
            if expected and blocked:
                outcome = "TP"
            elif expected and not blocked:
                outcome = "FN"
            elif not expected and not blocked:
                outcome = "TN"
            else:
                outcome = "FP"

            sample.update(
                {
                    "actual_blocked": blocked,
                    "guardrail_response": response,
                    "result": outcome,
                }
            )
            results.append(sample)

    return {
        "metrics": compute_guardrails_metrics(results),
        "results": results,
    }
