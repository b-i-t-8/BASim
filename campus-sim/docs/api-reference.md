# Talking to BASim (API Reference)

Want to hook up your own software to BASim? Here's everything you need to know about the REST API.

---

## First: Authentication

Every API call needs you to be logged in. The web UI uses cookies, so if you're automating things, you'll need to grab a session cookie first.

```bash
# Log in and save the cookie
curl -c cookies.txt -X POST https://your-domain.com/login \
  -d "username=admin&password=admin"

# Now use that cookie for API calls
curl -b cookies.txt https://your-domain.com/api/status
```

---

## The Endpoints

### Getting Data

| What you want | How to get it |
|---------------|---------------|
| Overall status (time, weather) | `GET /api/status` |
| Central plant (chillers, boilers) | `GET /api/plant` |
| Electrical (meters, solar, UPS) | `GET /api/electrical` |
| List of buildings | `GET /api/buildings` |
| One specific building | `GET /api/building/<id>` |
| Wastewater plant | `GET /api/wastewater` |
| Data center | `GET /api/datacenter` |
| Who am I? | `GET /api/user` |

### Overrides

| What you want to do | How to do it |
|---------------------|--------------|
| See all active overrides | `GET /api/overrides` |
| Force a value | `POST /api/override/set` |
| Release an override | `POST /api/override/release` |

### Admin Stuff

| What you want to do | How to do it |
|---------------------|--------------|
| Get sim parameters | `GET /api/admin/parameters` |
| Change sim parameters | `POST /api/admin/parameters` |
| Trigger weather scenario | `POST /api/admin/scenario` |
| Switch units (US/Metric) | `POST /api/admin/unit-system` |

---

## Some Examples

### What's the current status?

```bash
curl -b cookies.txt https://your-domain.com/api/status
```

You'll get back something like:

```json
{
  "simulation_time": "2025-12-28T14:30:00",
  "season": "Winter",
  "oat": 42.5,
  "humidity": 65,
  "wet_bulb": 38.2,
  "dew_point": 32.1,
  "enthalpy": 15.8,
  "simulation_speed": 1.0,
  "num_buildings": 5,
  "total_vavs": 50,
  "temp_unit": "°F"
}
```

### What's happening at the plant?

```bash
curl -b cookies.txt https://your-domain.com/api/plant
```

```json
{
  "name": "Central Plant",
  "chw_supply_temp": 44.2,
  "chw_return_temp": 54.8,
  "hw_supply_temp": 180.5,
  "hw_return_temp": 160.2,
  "total_cooling_tons": 250.5,
  "total_heating_mbh": 1200.0,
  "total_plant_kw": 185.2,
  "chillers": [...],
  "boilers": [...],
  "cooling_towers": [...],
  "pumps": [...]
}
```

### Force a chiller off

```bash
curl -b cookies.txt -X POST https://your-domain.com/api/override/set \
  -H "Content-Type: application/json" \
  -d '{
    "point_path": "CentralPlant.Chiller_1.status",
    "value": 0,
    "priority": 8,
    "duration_seconds": 300
  }'
```

**What those fields mean:**
- `point_path` — Which point to override (see below for naming)
- `value` — What to set it to
- `priority` — BACnet-style priority, 1-16 (lower wins)
- `duration_seconds` — Optional: auto-release after this many seconds

### Release that override

```bash
curl -b cookies.txt -X POST https://your-domain.com/api/override/release \
  -H "Content-Type: application/json" \
  -d '{"point_path": "CentralPlant.Chiller_1.status"}'
```

### Make it snow

```bash
curl -b cookies.txt -X POST https://your-domain.com/api/admin/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "Snow"}'
```

Options: `Normal`, `Snow`, `Rainstorm`, `Windstorm`, `Thunderstorm`

---

## Point Naming

Points follow a `System.Equipment.Point` pattern. Some examples:

```
CentralPlant.Chiller_1.status
CentralPlant.Chiller_1.chw_supply_temp
CentralPlant.Pump_CHW_1.speed
Building_1.AHU_1.supply_fan_speed
Building_1.AHU_1.VAV_101.damper_position
Building_1.AHU_1.VAV_101.zone_temp
```

Hit `/api/overrides` to see real examples from your running system.

---

## When Things Go Wrong

Standard HTTP codes:

| Code | What happened |
|------|---------------|
| `200` | All good |
| `400` | You sent bad data |
| `401` | Not logged in |
| `403` | You don't have permission |
| `404` | That doesn't exist |
| `500` | Something broke on our end |

Errors come back as JSON:

```json
{
  "error": "Invalid point path: CentralPlant.Chiller_99.status"
}
```

---

## What's Next?

- **[User Guide](user-guide.md)** — Learn the web interface
- **[Troubleshooting](troubleshooting.md)** — Fix common problems
