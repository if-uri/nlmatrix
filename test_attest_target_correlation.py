"""L11↔L3 target-correlation attestation has teeth: it flags the observed buggy
trace (results.target=host while routing/timeline=lenovo) that every checklist
passes because all steps are ok:true. The bug lies only in cross-layer agreement.

This is the RED test on the mismatch the user found: `test_observed_trace_is_consistent`
documents the OPEN bug (xfail) — it flips to pass when the executor stamps the same
target into results that routing/timeline carry.
"""
import pytest

import attest_target_correlation as a


def test_consistent_trace_has_no_violation():
    assert a.violations(a.CONSISTENT_TRACE) == []


def test_attestation_catches_the_target_mismatch():
    viol = a.violations(a.BUGGY_TRACE)
    assert viol, "results/routing/timeline disagree on the target; attestation must flag it"
    assert "results=host" in viol[0]["detail"] and "routing=lenovo" in viol[0]["detail"]


def test_checklist_blindspot_every_step_is_ok_true():
    # the whole point: a checklist sees only ok:true and passes; correlation is what fails
    results = a.BUGGY_TRACE["results"]
    assert all(sr["result"]["ok"] for sr in results.values())
    assert a.violations(a.BUGGY_TRACE)  # yet the cross-layer attestation fails


@pytest.mark.xfail(reason="OPEN BUG: executor stamps results.target=host while routing/timeline=lenovo "
                          "(recall on host+lenovo). Flips to pass once the same runsOn is recorded in results.",
                   strict=True)
def test_observed_trace_is_consistent():
    # the RED test: the observed trace SHOULD be target-consistent. It is not (yet).
    assert a.violations(a.BUGGY_TRACE) == []
