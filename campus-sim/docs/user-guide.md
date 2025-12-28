# Using BASim

Alright, you've got BASim running. Now what? Let's walk through how to actually use this thing.

---

## Finding Your Way Around

When you log in, you'll land on the **Dashboard**. This is your home base — it shows everything happening in the simulated campus.

### The Tabs

Click the tabs at the top to explore different parts of the system:

- **Plant** — The central plant: chillers, boilers, cooling towers, pumps
- **Electrical** — Power stuff: meters, generators, solar panels, UPS
- **Building 1, 2, 3...** — Individual buildings with their AHUs and VAVs
- **Wastewater** — Treatment facility (if your campus has one)
- **Data Center** — Cooling systems for data centers (if configured)

### The Status Bar

That bar at the top tells you what's going on globally:

- **Date/Time** — The simulated time (might be running faster than real-time)
- **Season** — Affects weather patterns and loads
- **OAT** — Outside Air Temperature (the big one)
- **Humidity** — Relative humidity
- **Wet Bulb / Dew Point** — Important for cooling tower calcs
- **Enthalpy** — Used for economizer decisions
- **Sim Speed** — How fast time is moving (1.0 = real-time)
- **Plant kW** — Total power the central plant is using
- **Cooling Load** — How many tons of cooling we're making

---

## Playing God (Overrides)

This is the fun part. You can override almost any value in the simulation to see what happens.

### How to Override Something

1. Click on any value — temperatures, pump statuses, setpoints, whatever
2. The override menu pops up
3. Enter the value you want to force
4. Pick a priority (1-16, lower wins — just like real BACnet)
5. Optionally set a duration (it'll auto-release after)
6. Hit Set

**Try this:** Click on a chiller's status and force it to `0` (Off). Watch the chilled water supply temperature start climbing. The other chillers will try to compensate.

### Overridden Values

Overridden points show up highlighted in yellow so you know something's being forced. Click on it again to see the current override or release it.

### See All Overrides

Click the **Overrides** button in the header. You'll get a list of everything currently being forced, and you can release them from there.

---

## Weather Scenarios

Want to stress-test the system? Use the scenario buttons to mess with the weather:

| Button | What Happens |
|--------|--------------|
| **Normal** | Back to regular weather based on date and location |
| **Snow** | Freezing temps (20-30°F), heating load spikes |
| **Rain** | Cooler, more humid |
| **Wind** | Temperature swings, harder to control |
| **Thunder** | Power flickers, possible outages |

It's kind of fun to hit "Heatwave" and watch all the chillers scramble.

---

## Admin Stuff

If you're logged in as an admin, you can tweak the simulation itself.

### Campus Settings

- **Campus Name** — Change what shows up in the header
- **Unit System** — Switch between US (°F, GPM, CFM) and Metric (°C, L/s)

### Physics Parameters

This is where you can tune how the simulation behaves:

- **Thermal Mass** — How sluggish zones are (higher = slower response)
- **Envelope UA** — Building insulation (higher = more heat loss)
- **Internal Gains** — Heat from people, lights, computers
- **Solar Gain** — How much the sun heats up zones
- **VAV Gains** — How aggressive the VAV control is
- **Equipment Efficiency** — Chiller and boiler performance

Play with these if the defaults don't feel right for what you're testing.

---

## Fun Things to Try

### Watch a Control Sequence React

1. Find a zone temperature
2. Override it to something high (like 85°F)
3. Watch the VAV damper slam open
4. See the airflow increase
5. Notice the AHU fan speed up
6. Watch the chiller load climb

Now release the override and watch everything settle back down.

### Simulate a Chiller Failure

1. Go to the Plant tab
2. Override Chiller 1's status to `0`
3. Watch the remaining chiller(s) pick up the load
4. If load exceeds capacity, watch the loop temps climb

### Fast-Forward Time

Want to see a whole day in a minute?

1. Go to Admin
2. Set simulation speed to `60` (that's 1 hour per minute)
3. Watch daily and seasonal patterns unfold
4. Set it back to `1.0` when you're done

---

## Next Up

- **[API Reference](api-reference.md)** — Want to integrate with your own software?
- **[Troubleshooting](troubleshooting.md)** — When things aren't working
