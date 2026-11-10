# Security checklist

Items marked done were exercised by the unit tests or by reading the code in this repo. Items marked open need a real cluster, a domain, or a review Saad does himself.

| Item | Status | How it was checked |
|---|---|---|
| Secrets come from environment variables, with `.env.example` and no committed keys | Done | `.env.example` lists every key. Tests pass an explicit `Settings` object. |
| Upload size limit, including a 10 GB rejection | Done | `assert_upload_allowed` rejects 10 GiB in `test_validate_and_retry.py`. The HTTP layer stops reading once `MAX_UPLOAD_BYTES` is crossed (`test_api.py`). |
| File type allow-list (mp4, mov, mkv, webm) plus ffprobe | Done | A `.txt` upload returns 400. Random bytes named `.mp4` fail ffprobe. |
| Maximum video length | Done | A 3 s file is rejected when `MAX_VIDEO_SECONDS=1`. |
| Maximum concurrent jobs and a failed-job list | Done | A second upload returns 429 while one job is processing. `GET /jobs?status=failed` lists failures. `POST /jobs/{id}/retry` requeues a failed job. |
| Optional API key | Done | When `API_KEY` is set, requests without `X-API-Key` get 401. Empty key means open, which is the local demo. |
| Rate limit on search and answer | Done | Three searches with a limit of 2 return 429 on the third. |
| Presigned local URLs expire | Done | HMAC signature includes the expiry. `verify_signature` rejects an expired stamp. S3/R2 uses boto3 presign with `PRESIGN_TTL_S`. |
| MinIO bucket is not anonymous | Defined | `deploy/docker-compose.yml` runs `mc anonymous set none`. Not executed here (no Docker in the build environment). |
| Containers run as non-root | Done in the Dockerfiles | API and worker use uid 10001. The web image uses the `node` user. |
| Kubernetes Secrets instead of inline production passwords | Partial | The Helm chart reads keys from a Secret. The default `postgres.password` is the literal `change-me`. Replace it at install time. SOPS is not wired up. |
| Network policy / private buckets in the cloud account | Open | Terraform creates the firewall and an R2 bucket only when you set the flags. You still have to confirm the bucket is private in the Cloudflare dashboard. |
| TLS on the public host | Open | The Ingress asks cert-manager for a certificate. That requires a cluster, a domain, and a ClusterIssuer you install. |

Do not tick the open rows until you have run the command on your own machine.
