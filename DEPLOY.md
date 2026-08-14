# Deploy unusual_options_bot on an OVH VPS

Paper desk only. Virtual **$1,000**. No broker login, no live order.

This is a **separate** desk from `prediction_bot` and `market_bot`. Same machine is fine: this one uses ports **3003** and **8003**.

## Ports

| Service | Host port |
|---|---|
| UI | https://vps-43564666.vps.ovh.net/options/ (basic auth) |
| API | loopback 127.0.0.1:8003, proxied at /options/api/ |

On this OVH box, start with the lean file so `next dev` does not eat RAM:

```bash
docker compose -f docker-compose.vps.yml up -d --build
```

## 1. Server once

If Docker is not installed yet (skip if you already did this for the other bots):

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# log out and back in so docker works without sudo
```

## 2. Clone on the VPS

The Mac deploy keys do **not** live on the VPS. Create a read-only key on the server:

```bash
ssh-keygen -t ed25519 -C "unusual_options_bot-vps" -f ~/.ssh/unusual_options_bot_vps -N ""
cat ~/.ssh/unusual_options_bot_vps.pub
```

On GitHub: repo **Settings → Deploy keys → Add deploy key**. Title `unusual_options_bot vps`. Paste the public key. Leave **Allow write access** unchecked.

Then:

```bash
mkdir -p ~/.ssh
cat >> ~/.ssh/config <<'EOF'
Host github.com-option
  HostName github.com
  User git
  IdentityFile ~/.ssh/unusual_options_bot_vps
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

cd ~
git clone git@github.com-option:dbo-Crypto/unusual_options_bot.git
cd unusual_options_bot
```

## 3. Env file (never commit)

```bash
cp .env.example .env
chmod 600 .env
```

Set the public URLs (ProtectYourDoc nginx fronts this desk at `/options/`):

```bash
# in .env
DATA_MODE=live
CORS_ORIGINS=https://vps-43564666.vps.ovh.net
NEXT_PUBLIC_API_URL=https://vps-43564666.vps.ovh.net/options
NEXT_PUBLIC_WS_URL=wss://vps-43564666.vps.ovh.net/options/ws
NEXT_PUBLIC_BASE_PATH=/options
DESK_TOKEN=long-random-token
NEXT_PUBLIC_DESK_TOKEN=long-random-token
```

`POSTGRES_*` / `REDIS_URL` stay as in `.env.example` (they talk to the other containers). Compose overrides host to `postgres`.

## 4. Start

```bash
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml ps
curl -sS http://127.0.0.1:8003/health
```

Open `https://vps-43564666.vps.ovh.net/options/` (same basic-auth as the other desks).

Paper ledger lives in the Docker volume `pgdata`. `docker compose down` keeps it. `docker compose down -v` wipes the bankroll.

## 5. Update later

```bash
cd ~/unusual_options_bot
git pull
docker compose -f docker-compose.vps.yml up -d --build
```

## SSH tunnel (no public UI ports)

From your Mac, with the OVH key:

```bash
ssh -i ~/.ssh/ovh/pyd -L 3003:127.0.0.1:3003 -L 8003:127.0.0.1:8003 ubuntu@vps-43564666.vps.ovh.net
```

Keep `.env` on `localhost` URLs. Open http://localhost:3003 on the Mac.
