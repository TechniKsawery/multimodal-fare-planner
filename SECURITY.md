# Security policy

This is a portfolio/prototype project, not a production service. If you find a security issue
(for example an exposed secret), please report it privately through GitHub:
**Security tab -> "Report a vulnerability"** (private vulnerability reporting), not in a public issue.

- Secrets (`.env`, tokens) are never committed; `.env.example` contains only empty placeholders.
- The optional unofficial price service (`tools/db-vendo-service`) binds to 127.0.0.1 and is meant for local testing only.
- Do not expose the Streamlit app or the API to the internet without your own authentication and rate limiting.
