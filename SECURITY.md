# Security policy

Security fixes target the latest `main` branch. No older release has a separate maintenance policy.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting if available:
[Report a vulnerability](https://github.com/AndreCirri/assistente-stampa-3d/security/advisories/new).
If private reporting is unavailable, open an issue requesting a private contact channel without
including exploit details, credentials, private models or personal data. Share the details only
after a private channel has been established.

Include the affected commit, platform, reproducible steps using synthetic data, expected and
actual behaviour, and the impact. Never send live credentials. Response times are not guaranteed.

## Intended deployment

STRATO is a local desktop workflow served on localhost. It has no multi-user authentication or
tenant isolation. An Internet-facing or shared deployment requires a separate security design.
Uploaded models are parsed locally; optional Claude requests transmit the context selected by
the application. Review that context before requesting advice.
