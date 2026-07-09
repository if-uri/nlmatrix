import re
from pathlib import Path

# This test enforces a project policy: tasks / connectors / flows must use
# URI-based execution (urirun routes) instead of embedding shell scripts or
# calling subprocess/os.system directly. The test scans Python files under
# the `urirun-connector-` packages and `.urirun/flows` for banned patterns.


ROOT = Path(__file__).resolve().parents[1]

BANNED_PATTERNS = [
    r"\bsubprocess\.run\(",
    r"\bsubprocess\.Popen\(",
    r"\bos\.system\(",
    r"\bsubprocess\.call\(",
    r"shell=True",
]


def scan_files():
    matches = []
    # targets: only flows and user-facing scripts/examples (not connector internals)
    globs = []
    globs += list(ROOT.glob('.urirun/**'))
    globs += list(ROOT.glob('examples/**/*.py'))
    globs += list(ROOT.glob('app/scripts/**/*.py'))
    # filter out vendored/venv/site-packages or build artifacts
    files = []
    for p in globs:
        try:
            s = str(p)
        except Exception:
            continue
        if any(ex in s for ex in ('/venv/', '/.venv/', 'site-packages', '/examples/_site/', '/.tox/')):
            continue
        if p.is_file() and s.endswith('.py'):
            files.append(p)

    for f in files:
        text = f.read_text(encoding='utf-8', errors='ignore')
        for pat in BANNED_PATTERNS:
            if re.search(pat, text):
                matches.append((f.relative_to(ROOT), pat))
    return matches


def test_no_direct_subprocess_in_connectors_and_flows():
    matches = scan_files()
    if matches:
        msg_lines = [
            "Direct script/subprocess usage detected in connector/flow code.",
            "Policy: use URI routes (kvm://, shell:// manage://, app://, etc.) via urirun, not subprocess/os.system.",
            "Violations:",
        ]
        for f, pat in matches:
            msg_lines.append(f" - {f}: pattern {pat}")
        pytest_msg = "\n".join(msg_lines)
        raise AssertionError(pytest_msg)
