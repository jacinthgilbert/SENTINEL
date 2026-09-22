# Data licences and attribution

The MIT licence in `LICENSE` covers the code. The files committed under
`data/` are **derived from third-party datasets carrying their own terms**,
some of which are share-alike. Read this before publishing, redistributing or
commercialising anything built from this repository.

| File | Derived from | Licence | Obligation |
|---|---|---|---|
| `roads.graphml`, `road_segments.geojson`, `facilities.geojson` | OpenStreetMap | **ODbL 1.0** | Attribute, and share derived databases alike |
| `dem.tif`, `hand.tif` | AWS Terrain Tiles (SRTM, NED, national DEMs) | Mostly public domain; per-source terms vary | Attribute the underlying sources |
| `population.tif`, population fields in `zones.geojson` | GHS-POP R2023A, European Commission JRC | **CC BY 4.0** | Attribute |
| `zones.geojson` (geometry) | H3 grid over the above | — | Inherits from its inputs |

`zones.geojson` mixes OSM-derived and GHS-POP-derived values, so treat it as
**ODbL + CC BY**, the stricter combination.

## Required attribution

Put this on any published map, dashboard or slide:

> Map data © OpenStreetMap contributors, ODbL.
> Population: GHS-POP R2023A, European Commission, Joint Research Centre (JRC), CC BY 4.0.
> Elevation: AWS Terrain Tiles (SRTM and national DEMs).

## Live services

| Service | Terms | Note |
|---|---|---|
| Open-Meteo | CC BY-NC 4.0 | **Non-commercial only.** Fine for a hackathon; needs a licence to commercialise |
| OpenStreetMap tiles | Tile Usage Policy | Bulk downloading is discouraged — the offline pre-cache here is a single AOI at z12–15. Use a commercial tile host in production |
| OpenTopography | Free with a key | 200 calls/24 h academic, 50 otherwise |
| Twilio | Commercial | Sandbox limits apply; see README |

## If you would rather not carry ODbL

Remove the OSM-derived files from git and regenerate them locally:

```bash
git rm --cached data/roads.graphml data/road_segments.geojson data/facilities.geojson
echo "data/roads.graphml"        >> .gitignore
echo "data/road_segments.geojson" >> .gitignore
echo "data/facilities.geojson"   >> .gitignore
make prep     # rebuilds them from OSM in a couple of minutes
```

The trade-off is that a fresh clone then needs network access before it runs,
which is why they are committed by default.
