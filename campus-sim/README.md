# Campus Simulator (BASim)

![Version](https://img.shields.io/badge/version-0.0.6-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)

BASim is a building automation simulator. It creates a fake (but realistic) university campus with chillers, boilers, AHUs, VAVs, electrical systems — the whole deal. Everything talks real protocols (Modbus, BACnet), so you can point actual BAS software at it for testing, training, or demos.

---

## Docs

| | |
|---|---|
| **[Getting Started](docs/installation.md)** | Install and run BASim |
| **[User Guide](docs/user-guide.md)** | How to use the dashboard |
| **[API Reference](docs/api-reference.md)** | REST API for integrations |
| **[Troubleshooting](docs/troubleshooting.md)** | When stuff breaks |

---

## What's Inside

**Equipment:**
- Central plant (chillers, boilers, cooling towers, pumps)
- Building HVAC (AHUs and VAV boxes)
- Electrical (meters, generators, UPS, solar)
- Wastewater (lift stations, blowers, clarifiers)

**Protocols:**
| Protocol | Port |
|----------|------|
| Modbus TCP | `5020` |
| BACnet/IP | `47808/udp` |
| BACnet/SC | `8443` (via `/bacnet-sc`) |

**Web UI:**
- Live dashboard
- Works on mobile
- Override any point
- Trigger weather scenarios

---

## Quick Start

**Option 1: GitHub Codespaces** (no install needed)
1. Click **Code** → **Codespaces** → **Create codespace**
2. Run `python main.py` (quick) or `docker compose up -d --build` (full)
3. Open port 8080 or 443 from the Ports tab

**Option 2: Local with Docker**
```bash
git clone https://github.com/your-repo/campus-sim.git
cd campus-sim
docker compose up -d --build
```

**Option 3: Local without Docker**
```bash
git clone https://github.com/your-repo/campus-sim.git
cd campus-sim
pip install -r requirements.txt
python main.py
```

Open https://localhost (Docker) or http://localhost:8080 (Python). Login: `admin` / `admin`

See the **[Installation Guide](docs/installation.md)** for production deployments.

---

## Configuration

Set these in your `.env` or `docker-compose.yml`:

| Variable | Default | What it does |
|----------|---------|--------------|
| `CAMPUS_SIZE` | `Small` | How many buildings/points |
| `SIMULATION_SPEED` | `1.0` | Time multiplier |
| `GEO_LAT` | `36.16` | Location for weather |

---

## The Code

| File | What it does |
|------|--------------|
| `model.py` | Physics engine, equipment models |
| `servers.py` | Modbus and BACnet servers |
| `web/` | Flask app, dashboard, API |
| `main.py` | Ties it all together |
| `Caddyfile` | Reverse proxy, SSL |

---

## Todo

**Protocol Testing**
- [ ] Automated BACnet/SC tests
- [ ] Automated Modbus tests
- [ ] Conformance validation
- [ ] Test with Niagara, Ignition

**Multi-Campus**
- [ ] Multiple campus instances
- [ ] Cross-campus networking
- [ ] BACnet routing between sites

**Better Simulation**
- [ ] Real equipment curves
- [ ] Sensor drift/noise
- [ ] Startup/shutdown sequences
- [ ] Fault injection

**Features**
- [ ] BACnet alarms
- [ ] Schedule objects
- [ ] Trending/charts
- [ ] Energy reporting

---

## Contributing

PRs welcome. For big changes, open an issue first so we can talk about it.
