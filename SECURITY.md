# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately. Do not open a public issue for security-sensitive findings.

Use GitHub private vulnerability reporting or contact the repository owner through the maintainer profile. Include:

- A concise description of the issue
- Reproduction steps or proof of concept
- Affected versions, commits, services, or deployment modes
- Potential impact and suggested remediation, if known

We aim to acknowledge valid reports promptly and coordinate a fix before public disclosure.

## Supported Scope

Security support applies to the default branch and the latest released or documented deployment path for quantum-workbench. Experimental examples, local-only scripts, and archived demos are best-effort unless the README states otherwise.

## Handling Secrets

- Never commit API keys, tokens, certificates, private keys, cookies, or `.env` files.
- Prefer environment variables, platform secret stores, or CI secret managers.
- Rotate any secret that may have been exposed in logs, screenshots, commits, or artifacts.

## Upstream Audit Exception

Last reviewed: 2026-07-23

Amazon Braket currently requires `setuptools==81.0.0` through both
`amazon-braket-default-simulator` and `amazon-braket-schemas`. That conflicts with
the `setuptools>=83.0.0` fix for `PYSEC-2026-3447` / `CVE-2026-59890`.

The advisory affects source-distribution file exclusion on macOS when filenames
use conflicting Unicode normalization forms. This service does not build or
publish source distributions at runtime, and release artifacts must be produced
from a trusted source tree. Do not process untrusted files through an sdist build
in the application environment.

Audit runs may ignore `PYSEC-2026-3447` only while the Braket packages retain the
exact setuptools pin. Remove the exception and upgrade setuptools as soon as the
upstream constraint is relaxed.
