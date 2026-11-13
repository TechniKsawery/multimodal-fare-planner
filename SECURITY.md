English | Polski: [wersja polska](SECURITY.pl.md)

# Security policy

This is a portfolio/prototype project, not a production service. If you find a security issue
(for example an exposed secret), please report it privately through GitHub:
**Security tab -> "Report a vulnerability"** (private vulnerability reporting), not in a public issue.

- Secrets (`.env`, tokens) are never committed; `.env.example` contains only empty placeholders.
- The unofficial DB price service was removed from this repository; the optional `UNOFFICIAL_PRICES` client code stays off by default.
- Do not expose the Streamlit app or the API to the internet without your own authentication and rate limiting.
