"""Gen 11 must have teeth: three flawed robot architectures are caught by
the same invariants that the honest engine passes.
"""
import gen11_capability_acquisition as g


def _case(case_id):
    return next(c for c in g.expand() if c["id"] == case_id)


def test_oracle_passes_all_episodes():
    for case in g.expand():
        result = g.run_case(case, engine=g.run_episode)
        assert g.check(case, result) == [], f"{case['id']}: {g.check(case, result)}"


def test_runtime_acquisition_then_resume_completes():
    result = g.run_case(_case("gap-recoverable"), engine=g.run_episode)
    assert result["status"] == "ok" and result["verified"]
    assert [a["uri"] for a in result["acquired"]] == ["img://host/svg/command/rasterize"]
    assert result["acquired"][0]["admitted"] is True


def test_unrecoverable_gap_yields_typed_need_not_success():
    result = g.run_case(_case("gap-unrecoverable-app"), engine=g.run_episode)
    assert result["status"] == "blocked-need"
    assert result["block"]["app"] == "inkscape"
    assert result["block"]["recoverable"] is False
    assert result["verified"] is False


def test_lying_generated_contract_blocked_at_admission():
    result = g.run_case(_case("gap-lying-contract"), engine=g.run_episode)
    assert result["status"] == "blocked-gate"
    assert "reversible-without-inverse" in result["block"]["violations"]
    assert result["executed"] == ["read_src"]


def test_resume_does_not_reexecute_completed_steps():
    result = g.run_case(_case("resume-after-fill"), engine=g.run_episode)
    assert result["status"] == "ok" and result["verified"]
    assert result["executed"] == ["write_png"]
    assert result["re_executed"] == []


def test_skip_missing_capability_is_caught():
    case = _case("gap-recoverable")
    result = g.run_case(case, engine=g.buggy_skip_missing)
    violations = g.check(case, result)
    assert any("verify-honesty" in x for x in violations), (
        "silent skip of a missing capability yields false success; checker must catch it"
    )


def test_ungated_acquisition_is_caught():
    case = _case("gap-lying-contract")
    result = g.run_case(case, engine=g.buggy_ungated_acquire)
    violations = g.check(case, result)
    assert any("ungated-acquisition" in x for x in violations), (
        "generated connector used without admission must be caught"
    )


def test_restart_instead_of_resume_is_caught():
    case = _case("idempotent-rerun")
    result = g.run_case(case, engine=g.buggy_restart)
    violations = g.check(case, result)
    assert any("restart" in x for x in violations), (
        "re-executing completed steps, including mutations, must be caught"
    )
