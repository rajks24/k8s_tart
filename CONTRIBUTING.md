# Contributing

Thank you for improving k8s-tart automation. Changes should preserve the
project's safety guarantees: no implicit kubeadm reset, no silent CNI
replacement, no credential output, and exact confirmation for destructive
operations.

## Development setup

Python 3.11 or newer is required. Runtime code uses only the standard library.
Install Ruff for development using the version pinned in the CI workflow.

Run the local validation suite before opening a pull request:

```bash
ruff check k8sctl.py scripts/check_markdown.py tests
python3 -m unittest discover -s tests -v
python3 -m py_compile k8sctl.py scripts/check_markdown.py
python3 scripts/check_markdown.py
bash -n scripts/guest/prepare-node.sh scripts/host/*.sh
shellcheck scripts/guest/prepare-node.sh scripts/host/*.sh
git diff --check
```

Tests must not require Tart, root access, or a live Kubernetes cluster. Clearly
identify changes that still require macOS/Tart integration testing.

Wrap normal Markdown prose at 80 characters. Tables, fenced code blocks, raw
URLs, and reference-link definitions are exempt because forced wrapping makes
those structures harder to maintain. Run `make docs-check` to verify the
project convention. The top-level `README.md` is intentionally not
hard-wrapped because it is the primary presentation document & GitHub wraps its
rendered text responsively. The same check also validates local Markdown file
targets and heading anchors.

## Pull requests

1. Keep changes focused and update user-facing documentation.
2. Add regression tests for behavior and safety checks.
3. Never commit `.state`, kubeconfigs, keys, logs, reports, real MAC addresses,
   DHCP reservations, bootstrap tokens, or unreviewed diagnostic output.
4. Pin new downloads and GitHub Actions by immutable digest or full commit SHA.
5. Explain destructive, privilege, networking, or compatibility implications.

By submitting a contribution, you agree that it is licensed under Apache-2.0.
For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening an
issue.
