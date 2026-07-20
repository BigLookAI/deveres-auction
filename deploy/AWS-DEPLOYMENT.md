# deVeres Reconciliation — AWS Deployment Runbook & Cost Estimate

_Prepared 20-Jul-2026. Moves the client system off the two office laptops onto a
single locked-down AWS host. Everything here is validated locally; the only
blocked step is provisioning itself, which needs AWS credentials (none on the
build machine yet — see §0)._

## 0. Status / prerequisites

| Item | State |
|---|---|
| Reconciliation image (`Dockerfile.recon`) | ✅ builds + runs healthy locally (ARM64 + x86_64 base) |
| Production stack (`deploy/docker-compose.prod.yml`) | ✅ `docker compose config` valid |
| Nightly backup (`deploy/backup.sh`) | ✅ pattern proven on the DGX (TOC-verified dumps) |
| Odoo prod config (`deploy/odoo.prod.conf`) | ✅ single-DB, no db-selector, workers=2 |
| **AWS CLI + credentials on build machine** | ❌ **not installed / not configured** — blocks actual provisioning |
| AWS account + billing (client to attach payment) | ⛔ client action |

Install the CLI when ready: `brew install awscli` then `aws configure` (or SSO).

## 1. Target architecture

Single EC2 instance, one VPC, everything private except a tightly-scoped app edge.

```
Client office (≤10 devices)
        │  HTTPS (443)
        ▼
[ Security Group: inbound 443 + 22 from client office CIDRs ONLY ]
        │
   EC2 t3.medium (Ubuntu 24.04, Docker)
   ├─ nginx (TLS termination, Let's Encrypt)  ── 443 → 127.0.0.1:8003
   ├─ deveres-recon   (app, loopback-bound)
   ├─ deveres-odoo    (private docker net only)
   └─ deveres-db      (private docker net only, EBS gp3)
        │
   Nightly: pg_dump → /opt/deveres/backups → S3 (versioned, lifecycle 30d)
   Daily:   EBS snapshot of the data volume (filestore + DB)
```

Why single-host: the client is <15 concurrent back-office sessions, not
public-facing. A managed RDS + ECS setup triples the cost for no benefit at this
scale. If load ever grows, the compose stack lifts onto ECS unchanged.

## 2. Network lockdown (the "client IPs only" requirement)

- One VPC, one public subnet, an internet gateway.
- **Security group** is the enforcement point:
  - `443/tcp` and `22/tcp` inbound **only** from the client's office egress
    CIDR(s) — get these from De Veres IT (static office IP, likely a /32 each).
  - All other inbound denied. No `0.0.0.0/0` anywhere.
  - Outbound: 443 (Let's Encrypt, S3, apt/docker pulls) — can be narrowed later.
- No public IP on the DB/Odoo containers at all — they have `no ports:` in the
  compose file, reachable only on the internal docker network.
- Odoo admin UI, when needed, is reached over an SSH tunnel
  (`ssh -L 8069:localhost:8069`), never published.

Terraform skeleton is in `deploy/aws/` (§8) — SG ingress is a variable list of
CIDRs so adding a laptop is a one-line change + `terraform apply`.

## 3. Provisioning steps (run once credentials exist)

```bash
# 3.1 infra
cd deploy/aws && terraform init && terraform apply \
  -var 'client_cidrs=["203.0.113.10/32","203.0.113.11/32"]' \
  -var 'key_name=deveres-ops'

# 3.2 on the instance (user-data does most of this)
ssh ubuntu@<eip>
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
git clone git@github-biglook:BigLookAI/deveres-auction.git /opt/deveres
cd /opt/deveres

# 3.3 addons for the Odoo container (exact assembly module set)
./odoo-test/sync_addons.sh odoo-test/assemblies/deveres_april.yaml \
  ~/BL-Odoo-System-of-Record   # or a bundled addons tarball

# 3.4 secrets
cp deploy/.env.prod.example deploy/.env.prod && edit it   # strong passwords/keys
# 3.5 bring up the stack
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
```

## 4. Load the real auction data (Postgres populated)

```bash
# restore the latest verified dump from the DGX backup set into the new DB
scp dgx:~/Cimelium/backups/odoo/deveres_april_*.dump ./
docker exec -i deveres-db pg_restore -U odoo -d odoo_deveres --clean --if-exists < deveres_april_*.dump
# upgrade module code to the assembly set, then verify
docker exec deveres-odoo odoo -c /etc/odoo/odoo.conf -d odoo_deveres \
  -u sor_technical_menu,sor_contact_roles,sor_business_model,sor_events,sor_lotting,sor_auction_documents,sor_accounting,sor_buyer_invoice --stop-after-init --no-http
ODOO_URL=http://localhost:8069 ODOO_DB=odoo_deveres python3 scripts/verify_environment.py   # expect 38/38
```

## 5. TLS + edge

`certbot --nginx -d deveres.<clientdomain>` (or a Cimelium subdomain). nginx
proxies `443 → 127.0.0.1:8003`. HSTS on. Basic-auth stays as the app's second
factor.

## 6. Readiness check (after env wired)

```bash
curl -su "$RECON_USER:$RECON_PASS" https://<host>/reconcile/health   # master_source=odoo, master_records ~13.7k
```
This is the readiness probe the container HEALTHCHECK deliberately does *not*
run (it would false-fail before Odoo is connected).

## 7. Backups & DR

- **DB**: `deploy/backup.sh` nightly (cron `30 2 * * *`) → local + S3
  (`S3_BUCKET=s3://deveres-backups`), 14-day local / 30-day S3 lifecycle,
  every dump TOC-verified.
- **Filestore**: Odoo attachments live in the `odoo-data` volume, *not* in the
  DB dump — a daily EBS snapshot of the data volume covers them. (Set a Data
  Lifecycle Manager policy, 7 daily.)
- **Restore drill**: documented one-liner in §4; test quarterly.

## 8. Cost estimate (eu-west-1, on-demand, ~monthly)

| Component | Spec | ~USD/mo |
|---|---|---|
| EC2 | t3.medium (2 vCPU / 4 GB), on-demand | 30 |
| EBS | 40 GB gp3 root+data | 3.5 |
| EBS snapshots | ~40 GB churn, 7 daily | 2 |
| S3 backups | <5 GB, versioned + lifecycle | 0.5 |
| Elastic IP | 1, attached | 0 (3.6 if idle) |
| Data transfer | low, internal office use | 1–3 |
| **Total (on-demand)** | | **≈ $38–42 / month** |
| **Total (1-yr Savings Plan / reserved t3.medium)** | | **≈ $25–28 / month** |

Notes: assumes the existing on-prem **Gemma LLM stays on the DGX** — the
reconciliation path uses **no LLM**, so no GPU instance is required (this is the
big cost saver; a GPU box would be $400–1000+/mo). If bidder-eval is later
hosted and wants cloud rationale generation, that is a separate line item.
A t3.small (2 GB) would run ~$15/mo but Odoo 19 + Postgres wants 4 GB headroom;
t3.medium is the safe floor. Right-size down after observing real load.

## 9. What the client needs to provide

1. AWS account (or authorise Cimelium to run one and re-bill) + a payment method.
2. Office egress IP(s) for the security-group allow-list.
3. Domain (or accept a Cimelium subdomain) for TLS.
4. Green light to restore real data (currently only on the DGX + laptops).

## 10. Pre-prod mirror (deferred, §later)

Same compose file, a second smaller instance (`t3.small`), its own DB restored
from the nightly dump, its own git branch (`pre-prod`). Deploy flow: push to
`pre-prod` → client UAT → tag → deploy to prod. Not day-one; noted so the
architecture already supports it (nothing here is single-environment-specific).
