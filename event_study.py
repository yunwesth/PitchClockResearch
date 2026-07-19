"""
event_study.py — STUB (robustness, not implemented yet).

Pitch Clock x Reliever Fatigue analysis. See CLAUDE.md section 5.

⚠️ DECISION NEEDED / not started:
    - Parallel-trends check across pre-clock seasons (2021-2022): verify the
      treatment/control trends are parallel before 2023.
    - Likely form: an event-study (leads/lags interacted with consec_day) so the
      pre-period coefficients can be inspected for pre-trends.
    - The full robustness specification list (alt filters, cutter inclusion,
      min-AB, (b) intensity coding of ConsecutiveDay, 2025 data) is also undecided.

# TODO: implement once Daniel confirms the robustness spec. Left as a stub so the
main pipeline (reliever_list -> build_panel -> run_did) stands on its own.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "event_study.py is a stub — robustness spec not yet confirmed (see CLAUDE.md sec. 5)"
    )


if __name__ == "__main__":
    main()
