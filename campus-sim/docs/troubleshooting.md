# Troubleshooting

Something not working? Let's figure it out.

---

## It Won't Start

### Check the logs first

```bash
docker compose logs campus-sim
```

This usually tells you exactly what's wrong.

### Common culprits:

- **Port conflict** — Something else is using 80, 443, or 5020
- **Python error** — If you modified code, check for syntax errors
- **Missing files** — Make sure all the files are there

### The fix:

```bash
# Stop anything that might be in the way
sudo systemctl stop apache2   # or nginx
sudo systemctl stop caddy

# Rebuild from scratch
docker compose down
docker compose up -d --build
```

### Container keeps crashing?

```bash
docker compose logs -f campus-sim
```

Look for Python tracebacks. Usually something obvious.

---

## SSL Problems

### "Connection refused" or certificate errors

This usually means Caddy can't get a cert from Let's Encrypt.

**Check the basics:**

1. Are ports 80 and 443 actually open?
   ```bash
   sudo ufw status
   # Should show 80/tcp ALLOW and 443/tcp ALLOW
   ```

2. Is your DNS actually pointing here?
   ```bash
   dig your-domain.com +short
   # Should show your server's IP
   ```

3. What's Caddy saying?
   ```bash
   docker compose logs | grep -i "certificate\|acme\|tls"
   ```

**Rate limited?** Let's Encrypt has limits. If you've been testing a lot, Caddy will fall back to a self-signed cert. Wait an hour and restart.

### Self-signed certificate warning

If you're running locally with `localhost`, this is totally normal. Just click through the warning in your browser.

For production, make sure you have a real domain set up in the Caddyfile.

---

## Can't Connect via Modbus or BACnet

### Modbus won't connect

First, is the port even there?

```bash
docker compose ps
# Look for 5020->5020/tcp
```

Can you reach it?

```bash
nc -zv your-server 5020
# Should say "Connection succeeded"
```

Firewall?

```bash
sudo ufw allow 5020/tcp
```

Quick test with Python:

```python
from pymodbus.client import ModbusTcpClient
client = ModbusTcpClient('your-server', port=5020)
client.connect()
result = client.read_holding_registers(0, 10)
print(result.registers)
```

### BACnet/IP won't connect

Remember: BACnet/IP uses **UDP**, not TCP. That trips people up.

```bash
# Check it's exposed
docker compose ps
# Look for 47808->47808/udp

# Open the firewall
sudo ufw allow 47808/udp
```

**Other things to check:**
- Is something else using device ID 389999?
- Some firewalls block UDP by default
- Make sure your BACnet client is set to UDP port 47808

### BACnet/SC issues

BACnet/SC goes through WebSocket at `/bacnet-sc`.

Test it:

```bash
# Install wscat: npm install -g wscat
wscat -c wss://your-domain.com/bacnet-sc
```

Check Caddy's proxying it:

```bash
docker compose logs | grep bacnet
```

---

## It's Slow

### High CPU

Usually one of these:

- Campus too big
- Sim speed too high
- Too many browser tabs open

**Try:**

```bash
# In your .env
CAMPUS_SIZE=Small
SIMULATION_SPEED=1.0
```

See what's actually using CPU:

```bash
docker stats campus-sim
```

### Web interface is laggy

- Chrome and Firefox work best (Safari can be sluggish)
- Smaller campus = fewer things to render
- Check your network latency

---

## Weird Data

### Temperatures look wrong

**Are you looking at the right units?** Go to Admin and check if you're in °F or °C. It's easy to mix them up.

**Is something overridden?** Look for yellow highlighting on values. Click the Overrides button to see what's being forced.

**Did you change the physics?** Admin > Parameters > Reset to Defaults.

### Equipment isn't responding

Check for:
- Yellow highlight (it's being overridden)
- Fault indicators
- Whether the enable is actually on

---

## Can't Log In

**Default creds:** `admin` / `admin`

**Still not working?**
- Clear your cookies
- Try incognito/private mode
- If the container restarted, sessions get wiped

**Session keeps expiring?** Sessions live in memory. Container restarts = everyone gets logged out. That's just how it works for now.

---

## Still Stuck?

1. **Check the logs** (seriously, always start here):
   ```bash
   docker compose logs -f
   ```

2. **Search for similar issues** in the repo

3. **Open an issue** with:
   - What OS you're on
   - Docker version
   - What you did
   - What happened (with logs)
   - What you expected
