# Getting BASim Running

So you want to spin up your own building automation simulator? Cool. This guide will walk you through getting BASim up and running, whether you're just playing around locally or deploying to a real server.

---

## Easiest: GitHub Codespaces

Don't want to install anything? Use Codespaces:

1. Go to the repo on GitHub
2. Click the green **Code** button → **Codespaces** → **Create codespace**
3. Wait for it to build (~2 minutes)

Then pick how you want to run it:

### Option A: Quick and simple (Python direct)

```bash
python main.py
```

When port 8080 shows up in the Ports tab, click "Open in Browser". Login: `admin` / `admin`

This runs the simulator without Caddy/SSL. Good for testing.

### Option B: Full stack (Docker)

```bash
docker compose up -d --build
```

When port 443 shows up, click "Open in Browser". You'll get the full setup with Caddy reverse proxy.

---

## What You'll Need (Local/Server)

If you're running this on your own machine:

- **Docker** (20.10 or newer) - this is what runs everything
- **Docker Compose** (v2+) - comes with Docker Desktop, or install the plugin
- A machine with these ports free: **80**, **443**, **5020**, and **47808/udp**
- A domain name (optional, but nice for real SSL certificates)

Don't have Docker? Grab it from [docker.com](https://docs.docker.com/get-docker/).

---

## Quick Start (5 Minutes)

Just want to see it work? Here's the fast path:

```bash
git clone https://github.com/your-repo/campus-sim.git
cd campus-sim
docker compose up -d --build
```

That's it. Open [https://localhost](https://localhost) in your browser.

You'll get a certificate warning (it's self-signed locally) — just click through it. Log in with **admin** / **admin**.

---

## Running It for Real

Want to put this on an actual server with a real domain? Here's how.

### Step 1: Edit the Caddyfile

Open `Caddyfile` and swap out `sim.hill.coffee` with your domain:

```caddyfile
your-domain.com {
    tls {
        issuer acme
    }
    
    @bacnetsc {
        path /bacnet-sc
        header Connection *upgrade*
        header Upgrade websocket
    }
    reverse_proxy @bacnetsc https://127.0.0.1:8443 {
        transport http {
            tls_insecure_skip_verify
        }
    }
    
    reverse_proxy http://127.0.0.1:8080
}
```

### Step 2: Point Your Domain

Add an A record in your DNS pointing to your server's IP. This usually takes a few minutes to propagate.

### Step 3: Open the Firewall

```bash
# Ubuntu/Debian with UFW
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5020/tcp      # Modbus
sudo ufw allow 47808/udp     # BACnet/IP
```

### Step 4: Fire It Up

```bash
docker compose up -d --build
```

Caddy handles SSL automatically via Let's Encrypt. Give it a minute, then hit your domain. Should just work.

### Step 5: Make Sure It's Alive

```bash
docker compose logs -f
```

Watch for any errors. Hit Ctrl+C when you're satisfied.

---

## Tweaking the Config

You can customize things with environment variables. Either edit `docker-compose.yml` directly, or create a `.env` file:

```bash
# .env
CAMPUS_SIZE=Medium
SIMULATION_SPEED=5.0
GEO_LAT=40.7128
```

Here's what they do:

| Variable | Default | What it does |
|----------|---------|--------------|
| `CAMPUS_SIZE` | `Small` | How big the campus is. `Small` = 1 building (~10 points), `Medium` = 5 buildings (~100 points), `Large` = 20 buildings (~500 points) |
| `SIMULATION_SPEED` | `1.0` | Time multiplier. `1.0` = real-time, `60.0` = one simulated minute per real second |
| `GEO_LAT` | `36.16` | Latitude for weather and solar calculations (default is Las Vegas) |

---

## Ports at a Glance

| Port | What's there |
|------|--------------|
| `80` | HTTP (just redirects to HTTPS) |
| `443` | The web UI |
| `5020` | Modbus TCP |
| `47808/udp` | BACnet/IP |
| `8443` | BACnet/SC (WebSocket, accessed via `/bacnet-sc`) |

---

## Home Server? No Problem (DuckDNS)

Running this at home without a static IP? [DuckDNS](https://www.duckdns.org/) gives you a free subdomain.

1. Sign up at DuckDNS and grab a subdomain
2. Set up their update script (or a cron job) to keep your IP current
3. Put your DuckDNS domain in the Caddyfile
4. Forward ports 80 and 443 on your router
5. Restart the container

Caddy will get you a real SSL cert automatically.

---

## What's Next?

- **[User Guide](user-guide.md)** — Learn how to actually use this thing
- **[API Reference](api-reference.md)** — Hook up your own software
- **[Troubleshooting](troubleshooting.md)** — When things go sideways
