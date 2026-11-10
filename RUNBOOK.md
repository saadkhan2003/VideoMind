# Runbook — what you do yourself

The code in this repo was built and tested without paid accounts. Nothing below has been executed against a real cloud project. Prices change; check them before you create a VM.

Do these in order. Skip a step only if you have decided not to use that service.

## 1. Accounts

Create these yourself. Do not paste the secrets into git.

| Account | Why | What to copy into `.env` or GitHub secrets |
|---|---|---|
| GitHub | The repo already exists once you publish it. Actions needs permission to push to GHCR. | `GITHUB_TOKEN` is provided by Actions. Add `KUBECONFIG_B64` later. |
| Cloudflare | R2 bucket (no egress fee on the current public pricing — confirm it) and DNS. | `S3_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`. API token with R2 and DNS edit for Terraform: `TF_VAR_cloudflare_api_token`, `TF_VAR_cloudflare_account_id`, `TF_VAR_cloudflare_zone_id`. |
| Hetzner Cloud (or skip and use any Ubuntu VM) | One cheap CPU VM for k3s. | `TF_VAR_hcloud_token` |
| OpenRouter (optional) | VLM captions and the answer LLM without hosting a GPU. | `OPENROUTER_API_KEY`. Check the current model slug before you trust `OPENROUTER_VLM_MODEL`. |
| Langfuse Cloud (optional) | Traces for caption and answer calls. | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` |
| A domain you control | TLS and the Ingress host. | Point it at the VM in step 4. |

A GPU is optional. Dev ASR uses `WHISPER_MODEL=tiny` on CPU. `large-v3` wants a GPU (`WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`). Rent one only for a batch, or call a serverless GPU from the worker and shut it off after.

## 2. Local demo, no cloud

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y ffmpeg espeak-ng tesseract-ocr
make ingest-sample
make api
```

In another terminal:

```bash
make web
```

Open http://127.0.0.1:43123 and search `backpropagation`.

## 3. SSH key and Terraform

```bash
ssh-keygen -t ed25519 -f ~/.ssh/videomind -N ""
cd deploy/terraform
export TF_VAR_hcloud_token="paste-from-hetzner"
export TF_VAR_ssh_public_key="$(cat ~/.ssh/videomind.pub)"
export TF_VAR_create_servers=true
export TF_VAR_server_count=1
export TF_VAR_server_type=cpx21
export TF_VAR_location=fsn1
# optional R2 + DNS, after the Cloudflare token exists
# export TF_VAR_cloudflare_api_token="..."
# export TF_VAR_cloudflare_account_id="..."
# export TF_VAR_create_r2_bucket=true
# export TF_VAR_manage_dns=true
# export TF_VAR_cloudflare_zone_id="..."
# export TF_VAR_dns_name="videomind"
terraform init
terraform plan
terraform apply
terraform output node_ipv4
```

`create_servers` defaults to false so a casual apply does not bill you. Destroy the VM when you are not demoing:

```bash
terraform destroy
```

When you want remote state, create the state bucket first, then uncomment the `backend "s3"` block in `versions.tf` and set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` to the R2 token. Run `terraform init -migrate-state`.

## 4. k3s on that VM

```bash
export IP="$(terraform output -raw node_ipv4 | tr -d '[]" ' )"
ssh -i ~/.ssh/videomind root@"$IP"
# on the server
curl -sfL https://get.k3s.io | sh -s - server --write-kubeconfig-mode 644
# or: bash install-k3s.sh server   (copy deploy/k8s/install-k3s.sh up first)
kubectl get nodes
```

Install ingress-nginx and cert-manager on the server:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager
```

You still need a `ClusterIssuer` named `letsencrypt` before the chart's Ingress can get a certificate. Use your email:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: you@example.com
    privateKeySecretRef:
      name: letsencrypt-account
    solvers:
      - http01:
          ingress:
            class: nginx
EOF
```

The install script disables Traefik and the chart's default ingress class is `nginx`, which matches the ingress-nginx install above. If you leave Traefik on instead, set `ingress.className=traefik`.

Copy kubeconfig to your laptop and store it for Actions:

```bash
# on your laptop
scp -i ~/.ssh/videomind root@"$IP":/etc/rancher/k3s/k3s.yaml "$HOME/videomind.kubeconfig"
# edit the server: line so it is https://$IP:6443 rather than 127.0.0.1
base64 -w0 "$HOME/videomind.kubeconfig"
```

Put that base64 string in the GitHub secret `KUBECONFIG_B64`. Do not commit the kubeconfig.

## 5. Helm

On a machine with the kubeconfig:

```bash
kubectl create namespace videomind
helm upgrade --install videomind deploy/helm/videomind \
  --namespace videomind \
  --set ingress.host=videomind.yourdomain \
  --set ingress.className=nginx \
  --set postgres.password="$(openssl rand -hex 16)" \
  --set config.signingSecret="$(openssl rand -hex 16)" \
  --set config.s3Endpoint="https://<accountid>.r2.cloudflarestorage.com" \
  --set config.s3AccessKey="..." \
  --set config.s3SecretKey="..." \
  --set config.s3Bucket="videomind-videos"
kubectl -n videomind get pods
```

The shared PVC is ReadWriteOnce. Keep the API and the worker on the same node, or switch object storage to R2 and treat `/data` as scratch.

Rollback:

```bash
helm -n videomind history videomind
helm -n videomind rollback videomind <revision>
```

Prometheus and Grafana are not inside this chart. Install `kube-prometheus-stack` yourself when you want cluster metrics, and turn on `serviceMonitor.enabled`. The dashboard JSON in `monitoring/grafana` imports as-is.

Ray: install the KubeRay operator, then `--set ray.enabled=true`. Until then the worker is the poll loop (`python -m pipeline`). Celery is the other fallback (`WORKER_BACKEND=celery`, a Redis broker, and `pip install celery redis` in the image).

## 6. Models that cost a download or a bill

```bash
# bigger ASR, still local
export WHISPER_MODEL=small          # or large-v3 on a GPU

# real dense embeddings — this downloads BAAI/bge-m3, about a gigabyte-plus
export EMBEDDING_BACKEND=sentence_transformers
export EMBEDDING_MODEL=BAAI/bge-m3
export EMBEDDING_DIM=1024
# delete the old Qdrant collection first; the vector size changed

# real reranker — downloads BAAI/bge-reranker-v2-m3
export RERANKER_BACKEND=cross_encoder
export RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# paid captions
export CAPTION_BACKEND=openrouter
export OPENROUTER_API_KEY="..."
```

Reindex after you change the embedder. The caption cache keys include the model name, so a new model does not reuse old captions.

## 7. The labeled set

Target 150–200 queries on videos you have the right to use. About half spoken, about 30 percent visual, about 20 percent keyword. Mark 20 percent `dev` and the rest `test`. Use `eval/label_tool.py`. Then:

```bash
python -m eval.run_eval --queries eval/queries.jsonl --split test --ablation all --out eval/results/final
```

Copy the numbers into the README table yourself. If you cannot explain a metric on a toy ranking, leave it off your CV. The prompts are at the bottom of `NOTES.md`.

## 8. CI

Pushing to `main` runs `.github/workflows/ci.yml` (lint, unit tests, the 32-second end-to-end clip, UI build, `helm lint`, `terraform validate`) and `.github/workflows/deploy.yml` (GHCR images, then `helm upgrade` if `KUBECONFIG_B64` is present). The deploy job prints a skip line and exits 0 when that secret is absent, so the first push does not fail before the cluster exists. After you add the secret, re-run the workflow.
