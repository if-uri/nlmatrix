import re
from pathlib import Path

# This test enforces a project policy: flow implementations must use URI-based
# execution instead of embedding shell scripts or calling subprocess directly.
# Test harnesses, build scripts and executable adapter implementations may
# legitimately spawn processes, so they are deliberately outside this gate.


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
    # Only declarative/user flow implementation directories are governed here.
    # Connector internals and example test runners have their own contract gates.
    globs = list(ROOT.glob('.urirun/flows/**/*.py'))
    globs += list(ROOT.glob('flows/**/*.py'))
    globs += list(ROOT.glob('urirun-connector-*/flows/**/*.py'))
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
