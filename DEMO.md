# The Sentinel — demo runbook

Six minutes. Rehearse it five times. The script below is the one that was
timed against the real build, not an aspiration.

---

## Before you walk on

```bash
make stop          # clear stray servers
make api           # terminal 1
make web           # terminal 2
make check         # 18 endpoint smoke test — do NOT skip this
make demo          # known-good starting state
```

`make check` takes about ten seconds and has already caught two things that
would have shown on stage. Run it after every code change and once more
immediately before presenting.

Open **two browser tabs**, both already loaded:

1. `http://localhost:3000` — citizen view
2. `http://localhost:3000/authority` — authority dashboard

Then **click "Pre-download this area"** in the offline panel and wait for
"map ready offline". Beat 7 does not work without it.

Get a judge's phone number during setup if you are using real Twilio. If not,
the simulated handset carries the beat on its own.

---

## The script

| Time | Do | Say |
|---|---|---|
| **0:00** | Citizen view, calm | "This is Visakhapatnam right now. Quiet." |
| **0:45** | Click **Cloudburst** | "Now let's make it rain — 140 mm/hr." |
| **1:30** | Point at the escalating count, switch map to **+60 min** | "Water hasn't arrived yet. 70-odd zones are already warned — amber outlines are calm now, flooded in an hour." |
| **2:15** | Scroll to the handset, switch to **తెలుగు** | "Telugu first — this is Andhra Pradesh. One CAP document, three languages. Press ▶ for the people who can't read it." |
| **2:45** | Click **Why?** on the forecast panel | "Exact Shapley values. Forecast rain next hour, +55 cm, 38% of the decision." |
| **3:00** | **Report flooding** → click the map three times | "Three independent citizens. One report is ignored; three corroborate and move the risk map." |
| **3:30** | Click the map (report mode off) | "Route out. Amber dashed means it crosses a flooded road — we say so rather than refusing to route." |
| **4:00** | Switch to the **authority tab** | "146,000 people in the flooded area, 14,600 elderly. 16,500 shelter places. That gap is the decision. Team 1 goes where the most people are and there's no shelter within 2 km." |
| **4:45** | **Turn off wifi** | "The map is still here. Labelled last known, not pretending to be live. A report filed now queues and sends when the network returns." |
| **5:15** | Wifi back on, one slide | "Same pipeline, different forcing. Cyclone reuses the HAND surface for surge. `GET /hazards` lists what's built and what isn't." |

---

## Say these before a judge asks

Pre-empting a weakness reads as rigour; getting caught reads as overclaiming.

- **Terrain and population are real** — AWS Terrain Tiles and GHS-POP (JRC),
  both free and keyless, because OpenTopography and WorldPop were unreachable.
  Attribution to both is required if you publish.
- **Shelter capacity is not surveyed.** It is an OSM per-type default, so the
  shortfall figure is indicative of scale, not an operational number.
- **The vision model is a heuristic**, not a trained network. `"trained": false`
  in every response.
- **Skill is 17% overall, ~30% on storm days.** Operator step changes are
  unpredictable by construction; real rainfall ramps.
- **Translations are unreviewed** by a native speaker.
- **Trained on US gauges plus a synthetic generator**, because sub-hourly Indian
  gauge data is not public. Architecture transfers; weights need calibration.

Closing line: *"The model isn't the bottleneck. Data access is. Here's the
CAP-compliant interface NDMA could plug into tomorrow."*

---

## If something breaks

| Symptom | Do this |
|---|---|
| Forecast says "warming up" | `make demo` — warm-starts the history |
| Map grey, no zones | API is down. `make api`, then reload |
| Alerts not firing | `POST /alerts/evaluate` twice — debounce needs two passes |
| Slider does nothing | You are in Live mode. Click **Scenario** |
| Everything is flooded already | `make demo` and start again from Calm |
| Tiles missing offline | You skipped Pre-download. Reconnect and do it |
| Total failure | Play the backup recording. Keep talking |

**Record the backup before demo day.** Run the script once, screen-record the
whole six minutes with audio, and keep the file open in a tab. A recording you
never play costs nothing; not having one costs the demo.

---

## Reset between runs

```bash
make demo
```

Clears alerts, clears reports, returns to calm scenario at 10×, world clock to
zero. One command, because hunting for three reset buttons while a room waits
is its own kind of failure.
