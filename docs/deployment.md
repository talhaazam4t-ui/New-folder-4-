# Production Deployment Guide — Google Cloud Free-Tier VPS

This guide details deploying **Talox Tech Stream** on Google Cloud Platform's Always-Free Compute Engine tier (`e2-micro`: 1GB RAM, 0.25-2 vCPU, 30GB disk).

---

## 1. Prerequisites

1. Google Cloud Account (Free Tier).
2. GCP Compute Engine VM:
   - **Machine type:** `e2-micro` (2 vCPUs, 1 GB memory)
   - **Region:** `us-central1`, `us-west1`, or `us-east1` (Free-tier eligible)
   - **Boot disk:** Ubuntu 24.04 LTS (30 GB Standard Persistent Disk)
   - **Firewall:** Allow HTTP (port 80) and HTTPS (port 443)
3. Domain name with DNS A-record pointing to VM external IP.
4. Supabase Project (Free Tier) for PostgreSQL & Auth.

---

## 2. Server Provisioning & Swap Setup (Crucial for 1GB RAM)

Connect via SSH to your GCP VM and execute:

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Configure 2GB Swap Space to prevent Out-Of-Memory (OOM) crashes
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Install Docker & Docker Compose Plugin
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out and back in for group membership to take effect.

---

## 3. Clone Repository & Configure Environment

```bash
git clone https://github.com/your-org/talox-tech-stream.git
cd talox-tech-stream

# Create production environment file
cp .env.example .env
nano .env
```

Ensure production values are set:
- `APP_ENV=production`
- `DEBUG=false`
- `APP_SECRET_KEY=<generate-32-byte-secret>`
- `SUPABASE_URL=https://<your-project>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY=<your-secret-key>`
- `SUPABASE_DATABASE_URL=postgresql+asyncpg://postgres:<password>@db.<your-project>.supabase.co:5432/postgres`
- `AI_API_KEY=<your-openrouter-key>`

---

## 4. Configure Domain in Caddyfile

Edit `Caddyfile`:

```caddy
api.yourdomain.com {
    reverse_proxy backend:8000
}
```

Caddy automatically provisions and renews trusted Let's Encrypt SSL certificates.

---

## 5. Build and Launch Containers

```bash
# Build and run containers in detached mode with memory limits
docker compose -f docker-compose.prod.yml up -d --build

# Verify container health
docker compose -f docker-compose.prod.yml ps
docker logs -f talox_backend_prod
```

---

## 6. Zero-Downtime Updates

```bash
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build --no-deps backend
```
