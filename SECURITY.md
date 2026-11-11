# Security policy

VideoMind is an in-development application. Its private development demo is not
a production-hardened public service. There is no stable-release security
maintenance schedule or independent security-audit claim.

## Report privately

Email **msaad.official6@gmail.com** with the repository name, affected commit,
reproduction steps, and impact. Use synthetic media and dummy credentials where
possible. Do not put exploit details, private videos, transcripts, signed URLs,
API keys, or personal data into public issues. No response-time guarantee or
bug-bounty program is offered.

## Deployment boundaries

- Keep Codespaces ports private. Review authentication and the frontend proxy
  before exposing a multi-user service. An optional API key is not a full tenant
  isolation or authorization system.
- Replace development passwords/signing secrets; review TLS, storage access,
  presigned-URL expiry, network controls, and upload limits.
- Treat uploaded media, transcripts, OCR, captions, and generated answers as
  untrusted. FFmpeg parsing and model processing should run with restricted
  permissions and bounded resources.
- Use only videos you have permission to process. Avoid sending private content
  to caption/answer providers without the necessary authorization.
- Store secrets outside Git, set provider-side spending limits, and redact logs.
- Revoke/rotate exposed credentials immediately. Deleting a line from a file is
  not sufficient to remove a secret from Git history.

[docs/security.md](docs/security.md) distinguishes implemented controls from open
deployment items. The current feature set is not a guarantee of production safety.
