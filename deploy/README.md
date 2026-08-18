# Deploy the bot on AWS EC2 (Docker Compose)

The bot uses Telegram **long polling** — it only makes outbound HTTPS calls
(Telegram, rxresu.me, OpenAI/OpenRouter). No inbound ports, no load balancer.
A single small instance (`t3.micro`) is enough.

## 0. Prerequisites (on your machine)

- An AWS account + the AWS CLI configured (`aws configure`).
- An SSH key pair in the target region.
- Your secrets ready: `TELEGRAM_BOT_TOKEN`, `RXRESUME_API_KEY`, `OPENAI_API_KEY`.

Pick a region, e.g. `export AWS_REGION=eu-central-1`.

## 1. Security group (egress only)

```bash
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 create-security-group \
  --group-name portfolio-bot-sg \
  --description "Egress-only SG for the telegram bot" \
  --vpc-id "$VPC_ID" --query GroupId --output text)

# Allow SSH from your IP only (for setup). Replace 1.2.3.4/32.
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr 1.2.3.4/32
```

Default egress (all outbound) is already allowed — that is all the bot needs.

## 2. Launch the instance

```bash
# Amazon Linux 2023 AMI id for your region:
AMI_ID=$(aws ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameter.Value' --output text)

aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.micro \
  --key-name YOUR_KEY_NAME \
  --security-group-ids "$SG_ID" \
  --user-data file://deploy/ec2-user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=portfolio-bot}]'
```

The user-data script installs Docker + Compose and registers the
`portfolio-bot` systemd service. Give it a couple of minutes to finish.

Grab the public IP:

```bash
aws ec2 describe-instances \
  --filters Name=tag:Name,Values=portfolio-bot Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text
```

## 3. Copy the code to the instance

Two options — pick one.

**A. Git clone (private repo → use a GitHub PAT or deploy key):**

```bash
ssh ec2-user@<PUBLIC_IP>
git clone https://<GITHUB_PAT>@github.com/astormspirit/ai-portfolio.git /opt/portfolio-bot
```

**B. Copy from your machine (no git on the server):**

```bash
rsync -az --exclude '.git' --exclude '.venv' --exclude '.env' \
  ./ ec2-user@<PUBLIC_IP>:/opt/portfolio-bot/
```

## 4. Create the `.env` on the instance

```bash
ssh ec2-user@<PUBLIC_IP>
cat >/opt/portfolio-bot/.env <<'ENV'
TELEGRAM_BOT_TOKEN=...
RXRESUME_API_KEY=...
RXRESUME_BASE_URL=https://rxresu.me/api/openapi
RXRESUME_AI_PROVIDER_ID=
OPENAI_API_KEY=...
OPENAI_BASE_URL=
LLM_MODEL=gpt-4o-mini
MAX_PDF_SIZE_MB=15
ENV
chmod 600 /opt/portfolio-bot/.env
```

Never commit `.env` — it is already git-ignored.

## 5. Start the bot

```bash
sudo systemctl start portfolio-bot
sudo systemctl status portfolio-bot --no-pager
# Follow logs:
journalctl -u portfolio-bot -f
```

The first start builds the image (a few minutes). After that the service
auto-restarts on crash and on reboot.

## Updating later

### Automatic (GitHub Actions → EC2)

On every push to `main`, [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
SSHs into the instance, runs [`deploy/update.sh`](update.sh) (`git pull` +
`systemctl restart portfolio-bot`), and keeps the server `.env` untouched.

**One-time setup**

1. On the EC2 box the app must already live at `/opt/portfolio-bot` as a **git
   clone** of this repo (see step 3), with a working `.env` and
   `portfolio-bot` systemd unit enabled.
2. Give the instance read access to the repo for `git pull`:
   - add a **read-only deploy key** to the GitHub repo, or
   - keep a fine-grained PAT in the remote URL (less ideal).
3. In the GitHub repo → **Settings → Secrets and variables → Actions** create:

| Secret | Example | Required |
|---|---|---|
| `EC2_HOST` | `18.184.x.x` or DNS | yes |
| `EC2_SSH_PRIVATE_KEY` | full PEM of the key that can SSH as `ec2-user` | yes |
| `EC2_USER` | `ec2-user` | no (default `ec2-user`) |
| `EC2_PORT` | `22` | no (default `22`) |

4. Allow SSH from GitHub Actions to the instance. Easiest for a small bot:
   temporarily allow `0.0.0.0/22` only from your IP is not enough for Actions —
   either open port 22 to `0.0.0.0/0` (lock down with key-only auth), use an
   SSM/bastion setup, or restrict to [GitHub Actions IP ranges](https://api.github.com/meta).
5. Push to `main` or run the workflow manually (**Actions → Deploy to EC2 → Run workflow**).

Watch the run in the Actions tab; on the server:

```bash
journalctl -u portfolio-bot -f
```

### Manual

```bash
ssh ec2-user@<PUBLIC_IP>
cd /opt/portfolio-bot && git pull   # or rsync again
sudo systemctl restart portfolio-bot
```

## Costs / notes

- `t3.micro` is eligible for the free tier in most regions; otherwise a few
  USD/month. Stop or terminate the instance to stop billing.
- Rotate any token that was ever shared in plain text.
- For stronger secret hygiene, store the values in AWS SSM Parameter Store and
  fetch them at start instead of a plain `.env` (ask and I'll wire it up).
```
