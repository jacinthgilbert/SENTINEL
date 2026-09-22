# The Sentinel

Flood early-warning and response platform — **Visakhapatnam**.

Predicts flooding 30–120 minutes ahead, shows zone-level risk on a live map,
routes people around flooded roads, and alerts them in their own language —
including by SMS and voice, for phones that cannot run an app.

## Run

```bash
make            # list every task
make setup      # once: create .venv, install python deps
make prep       # fetch data, build HAND / zones / road graph
make api        # :8000
make web        # :3000
```

No OpenTopography key yet? `make prep-synthetic` builds everything on stand-in
terrain so the whole stack runs; the map shows a banner until real terrain
replaces it. Then `make fresh-terrain && make prep`.

> **Do not run `./prep/setup.sh` directly.** macOS 15 tags files written by
> sandboxed processes with `com.apple.provenance`, so `exec()` on them fails
> with *Operation not permitted* even though the exec bit is set. `make` invokes
> `bash <file>`, which reads the script instead, and always works.

Docker (optional, for PostGIS):

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API | http://localhost:8000 |
| Health | http://localhost:8000/health |
| Postgres | `localhost:5432` · `sentinel` / `sentinel` |

## Architecture in one paragraph

Everything reads from a single `WorldState` (`api/world.py`) fed by one of two
interchangeable adapters: **live** (Open-Meteo + sensors) or **scenario**
(replay file + rainfall slider). Nowcast, inundation, risk, routing and alerts
are all *pure functions* of that state — no DB reads, no HTTP, no clock access.
That is why the digital-twin demo behaves identically to live mode: same code
path, different adapter.

Full plan: `../flood-mvp-plan.md`

## Build progress

- [x] **1 — Spine.** WorldState contract, tick loop, SSE, schema, compose.
- [x] **2 — Geo prep.** DEM → HAND, road graph, H3 zones, population.
- [x] **3 — Inundation.** HAND threshold → polygon, live Leaflet map.
- [ ] 4 — Sim console: slider, clock, speed. *(F5 digital twin)*
- [ ] 5 — Nowcast: XGBoost quantile + SHAP. *(F1)*
- [ ] 6 — Risk + zones + vulnerable population.
- [ ] 7 — Routing: NetworkX edge removal. *(F2)*
- [ ] 8 — Alerts: CAP + i18n + Twilio + voice. *(F4)*
- [ ] 9 — Citizen reports + CV + trust. *(F3)*
- [ ] 10 — Authority dashboard + dispatch. *(F6)*
- [ ] 11 — Offline PWA + colour-blind mode.
- [ ] 12 — Demo polish + backup recording.

## The contract

`WorldState` is frozen as of Step 1. Changing a field means coordinating every
track, so don't — extend downstream instead.

```python
t: datetime            # sim clock in scenario mode, wall clock in live
tick: int
rainfall_mm_hr: float
stages: Mapping[str, float]      # gauge_id -> cm
blocked_roads: frozenset[int]    # OSM way ids
reports: tuple[Report, ...]
mode: Literal["live", "scenario"]
```


## Step 2 — geo prep

One-off, idempotent, runs outside the API container:

```bash
cp .env.example .env          # add your OpenTopography key
export $(grep -v '^#' .env | xargs)
pip install -r prep/requirements.txt
python prep/run.py
```

Produces, in `data/`:

| File | Source | Feeds |
|---|---|---|
| `dem.tif` | OpenTopography COP30 (1 API call) | HAND |
| `hand.tif` | pysheds `compute_hand()` | inundation, zone risk |
| `population.tif` | WorldPop 100 m constrained 2020, windowed via HTTP range reads | affected population |
| `roads.graphml` | OSMnx drivable network + speeds | evacuation routing |
| `road_segments.geojson` | OSMnx edges | PostGIS blocked-road state |
| `facilities.geojson` | OSM hospitals / schools / shelters | critical infrastructure |
| `zones.geojson` | H3 res-9 + zonal min-HAND + population sum | the risk choropleth |

Every stage skips if its output already exists, so a failed run resumes where
it stopped. `--no-load` builds artifacts without touching PostGIS.

### Data caveats to state in the pitch

- **`elderly_frac` is a flat placeholder** (`prep/config.py`). WorldPop's
  age-structure rasters would replace it; until then, do not present
  per-zone elderly counts as real.
- **HAND assumes river/channel flooding.** It models water backing up from
  drainage lines, not pluvial ponding behind blocked storm drains — which is a
  large part of real Visakhapatnam urban flooding. Say so before a judge asks.
- **`ACC_THRESHOLD` is tuned by eye.** The run prints what fraction of the grid
  became channel; if the drainage network looks wrong for the terrain, change
  it and delete `hand.tif` to recompute.
- **OSM facility coverage is uneven.** Shelter capacity is a per-type default,
  not surveyed data.

## Step 3 — inundation

`GET /inundation?stage_m=` thresholds the cached HAND array and polygonises it.
31 levels (0–3 m at 10 cm) are pre-warmed at startup, so no slider position
ever pays the cold cost: served in **8–22 ms**, 4–5 ms on a cache hit.

| Endpoint | Returns |
|---|---|
| `/inundation?stage_m=` | flooded extent as GeoJSON |
| `/inundation?stage_m=&geometry=false` | area only, no polygonisation |
| `/inundation/current` | extent implied by the live gauge |
| `/zones` | the static H3 layer |
| `/zones/flooded?stage_m=` | per-zone flooded fraction + exposed population |
| `/facilities` | hospitals / schools / shelters |

Two design notes worth keeping:

- **Zones carry a HAND decile curve, not a minimum.** A res-9 hex spans ~117 DEM
  cells and almost every hex touches a drainage line, so a min-based rule floods
  60% of the city at 0.5 m. The decile curve is the zone's empirical CDF, so
  "what fraction of this zone is under water" is an interpolation — a graded
  choropleth, computed with no raster access.
- **The risk ramp is colour-blind-safe by construction** (`web/lib/palette.ts`),
  blue→yellow→magenta rather than green→red, monotonic in lightness so it also
  survives greyscale and projector washout. Water uses a separate colour so the
  two never read as one scale.

### Blocked in the authoring sandbox — run these on your own network

Two downloads could not complete where this repo was built. Both work fine on a
normal connection; the pipeline is idempotent, so just run it again.

```bash
make fresh-terrain && make prep
```

| Stage | Why it was blocked | Expected on your machine |
|---|---|---|
| DEM (COP30) | `portal.opentopography.org` stopped resolving mid-session. The key itself was verified working on an earlier call. | one request, a few MB, seconds |
| Population | WorldPop advertises `accept-ranges` but ignores `Range:` headers, so the whole 506 MB file must come down. Sandbox throughput was 35 KB/s. | minutes on a normal link — `fetch_population.py` falls back to a full download and caches it as `data/worldpop_ind.tif` |

Everything else — road graph, facilities, H3 zones, and the HAND algorithm
itself — is built and verified.

### Verifying the hydrology

`prep/hydrology.py` is covered by an analytical test: a synthetic V-shaped
valley whose HAND is known in closed form.

```bash
python prep/tests/test_hydrology.py
```

Checks depression filling, D8 routing completeness, flow concentration, and
HAND values at 3/5/8 cells up the valley wall against `slope x distance`.
