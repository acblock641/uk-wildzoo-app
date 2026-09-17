
import math
import requests
import pandas as pd
import streamlit as st
import folium
from pyproj import Transformer
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation


# ------------------------------------------------------------
# App configuration
# ------------------------------------------------------------

st.set_page_config(
    page_title="UK Wildlife Explorer",
    page_icon="🦊",
    layout="centered",
)

ATLAS_URL = "https://records-ws.nbnatlas.org/occurrences/search"
SPECIES_LOOKUP_URL = "https://species-ws.nbnatlas.org/species/lookup/bulk"
TIMEOUT = 30
LOOKUP_CHUNK_SIZE = 100

# Conservative public prototype:
# use only the three NBN open licences.
OPEN_LICENSES = ["CC0", "CC-BY", "OGL"]

TAXON_FILTERS = {
    "All animals": 'kingdom:"Animalia"',
    "Birds": 'classs:"Aves"',
    "Mammals": 'classs:"Mammalia"',
    "Amphibians": 'classs:"Amphibia"',
    "Reptiles": 'classs:"Reptilia"',
    "Insects": 'classs:"Insecta"',
}

# Approximate bounding box for the United Kingdom
# (England, Scotland, Wales, Northern Ireland), including
# outlying islands such as Shetland, the Outer Hebrides and
# the Isles of Scilly. Deliberately generous — this is only
# used to catch accidental searches far outside the UK, not
# to draw a precise national boundary.
UK_BOUNDS = {
    "lat_min": 49.80,
    "lat_max": 61.05,
    "lon_min": -8.70,
    "lon_max": 1.80,
}


# ------------------------------------------------------------
# Coordinate / map helpers
# ------------------------------------------------------------

to_grid = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:27700",
    always_xy=True,
)

from_grid = Transformer.from_crs(
    "EPSG:27700",
    "EPSG:4326",
    always_xy=True,
)


def make_square(lat, lon, size_km):
    """Create a square in metres, centred on the supplied WGS84 point."""
    if size_km not in (1, 10):
        raise ValueError("size_km must be 1 or 10")

    x, y = to_grid.transform(lon, lat)
    half = size_km * 1000 / 2

    from shapely.geometry import box

    return box(
        x - half,
        y - half,
        x + half,
        y + half,
    )


def square_corners_latlon(square):
    """Return square corners as [(lat, lon), ...]."""
    corners = []

    for x, y in list(square.exterior.coords):
        lon, lat = from_grid.transform(x, y)
        corners.append((lat, lon))

    return corners


def build_map(lat, lon, size_km):
    square = make_square(lat, lon, size_km)
    corners = square_corners_latlon(square)

    zoom = 13 if size_km == 1 else 11

    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        control_scale=True,
        tiles="OpenStreetMap",
    )

    folium.Marker(
        [lat, lon],
        tooltip="Search centre",
        popup=f"{lat:.5f}, {lon:.5f}",
    ).add_to(m)

    folium.Polygon(
        locations=corners,
        tooltip=f"Selected area: {size_km} km × {size_km} km",
        weight=2,
        fill=True,
        fill_opacity=0.08,
    ).add_to(m)

    return m


def inside_uk(lat, lon):
    return (
        UK_BOUNDS["lat_min"] <= lat <= UK_BOUNDS["lat_max"]
        and
        UK_BOUNDS["lon_min"] <= lon <= UK_BOUNDS["lon_max"]
    )


# ------------------------------------------------------------
# NBN response helpers
# ------------------------------------------------------------

def extract_facet_rows(data):
    """
    Extract rows from the species facet in the live NBN response.

    The Atlas currently returns facetResults as a list.
    """

    facet_results = data.get("facetResults", [])

    if isinstance(facet_results, dict):
        facet_results = [facet_results]

    # First try to identify the species facet directly.
    for facet in facet_results:

        if not isinstance(facet, dict):
            continue

        facet_name = (
            facet.get("fieldName")
            or facet.get("field")
            or facet.get("name")
        )

        if facet_name and facet_name != "species":
            continue

        field_result = facet.get("fieldResult", [])

        if isinstance(field_result, dict):
            field_result = [field_result]

        if isinstance(field_result, list):
            rows = [
                row for row in field_result
                if isinstance(row, dict)
            ]

            if rows:
                return rows

    # Fallback: recursively find label/count objects.
    results = []

    def walk(obj):
        if isinstance(obj, dict):

            if "label" in obj and "count" in obj:
                results.append(obj)

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):

            for item in obj:
                walk(item)

    walk(facet_results)

    return results


def atlas_species(lat, lon, size_km, taxon):
    """
    Query the NBN Atlas for species in the selected area.

    The current working prototype uses the documented Atlas
    radius search. The map shows the intended 1 km / 10 km square.

    Unlike the Isle of Man version, this queries the NBN Atlas
    UK-wide, so there is no stateProvince/country filter — the
    lat/lon/radius parameters alone determine the search area,
    and that area can fall anywhere in England, Scotland, Wales
    or Northern Ireland.
    """
    radius_km = size_km / 2
    taxon_filter = TAXON_FILTERS[taxon]

    combined = {}
    total_records = 0

    for licence in OPEN_LICENSES:

        fq = [
            '-occurrence_status:"absent"',
            f'license:"{licence}"',
            taxon_filter,
        ]

        params = {
            "q": "*:*",
            "fq": fq,
            "lat": lat,
            "lon": lon,
            "radius": radius_km,
            "facets": "species",
            "flimit": -1,
            "pageSize": 0,
        }

        response = requests.get(
            ATLAS_URL,
            params=params,
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()
        total_records += int(data.get("totalRecords") or 0)

        for row in extract_facet_rows(data):

            species = (
                row.get("label")
                or row.get("fieldValue")
                or "Unknown"
            )

            count = int(row.get("count") or 0)

            if species not in combined:
                combined[species] = 0

            combined[species] += count

    df = pd.DataFrame(
        [
            {
                "Species": species,
                "Records": records,
            }
            for species, records in combined.items()
        ]
    )

    if not df.empty:
        df = df.sort_values(
            "Species",
            key=lambda s: s.fillna("").str.lower(),
        ).reset_index(drop=True)

    return df, total_records


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def lookup_common_names(scientific_names):
    """
    Look up common (vernacular) names for a tuple of scientific names,
    using the NBN Atlas bulk species lookup service.

    Returns a dict mapping scientific name -> common name. Species with
    no matched common name, or any that fail to look up, are simply
    left out of the dict rather than raising, so a lookup problem never
    breaks the main species list.
    """
    common_names = {}

    names = list(scientific_names)

    for start in range(0, len(names), LOOKUP_CHUNK_SIZE):
        chunk = names[start:start + LOOKUP_CHUNK_SIZE]

        try:
            response = requests.post(
                SPECIES_LOOKUP_URL,
                json={"names": chunk},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            results = response.json()

        except (requests.RequestException, ValueError):
            # A lookup hiccup should not break the species table;
            # just skip common names for this chunk.
            continue

        if not isinstance(results, list):
            continue

        # The bulk lookup returns one result per input name, in the
        # same order, with null/empty entries for anything unmatched.
        for original_name, result in zip(chunk, results):

            if not isinstance(result, dict):
                continue

            common = result.get("commonNameSingle")

            if common:
                common_names[original_name] = common

    return common_names


# ------------------------------------------------------------
# Interface
# ------------------------------------------------------------

st.title("🦊 UK Wildlife Explorer")

st.write(
    "Find animal species recorded by the NBN Atlas around a location "
    "in England, Scotland, Wales or Northern Ireland."
)

st.caption(
    "This prototype shows species with qualifying public NBN Atlas "
    "records. It is not an absence map and does not prove that an "
    "unlisted species is absent."
)

st.divider()

# Browser geolocation
st.subheader("1. Choose your location")

location = streamlit_geolocation()

if location and location.get("latitude") is not None:
    browser_lat = float(location["latitude"])
    browser_lon = float(location["longitude"])

    st.session_state["latitude"] = browser_lat
    st.session_state["longitude"] = browser_lon

    accuracy = location.get("accuracy")
    if accuracy:
        st.success(
            f"Location found (browser accuracy approximately "
            f"{accuracy:.0f} m)."
        )
    else:
        st.success("Location found.")

# Manual fallback
with st.expander("Enter coordinates manually"):
    manual_lat = st.number_input(
        "Latitude",
        value=float(st.session_state.get("latitude", 52.50)),
        format="%.6f",
    )

    manual_lon = st.number_input(
        "Longitude",
        value=float(st.session_state.get("longitude", -1.50)),
        format="%.6f",
    )

    if st.button("Use these coordinates"):
        st.session_state["latitude"] = manual_lat
        st.session_state["longitude"] = manual_lon
        st.rerun()

lat = st.session_state.get("latitude", 52.50)
lon = st.session_state.get("longitude", -1.50)

st.caption(f"Search centre: {lat:.5f}, {lon:.5f}")

if not inside_uk(lat, lon):
    st.warning(
        "This location appears to be outside the UK. "
        "Choose a location in England, Scotland, Wales or Northern "
        "Ireland to search the NBN Atlas."
    )
    st.stop()

st.subheader("2. Choose your search area")

size_label = st.radio(
    "Area size",
    ["1 km × 1 km", "10 km × 10 km"],
    horizontal=True,
)

size_km = 1 if size_label.startswith("1 ") else 10

st.subheader("3. Filter by taxon")

taxon = st.selectbox(
    "Taxon",
    list(TAXON_FILTERS.keys()),
)

search = st.button(
    "🔎 Find wildlife",
    type="primary",
    use_container_width=True,
)

# Always show the current map.
st.subheader("Map")

m = build_map(lat, lon, size_km)

st_folium(
    m,
    height=480,
    width=725,
    returned_objects=[],
    key=f"map_{size_km}_{round(lat, 5)}_{round(lon, 5)}",
)

st.caption(
    "The outline is the selected square. For this first web release, "
    "the NBN API search uses its documented radius-search endpoint, "
    "so the returned records are based on the corresponding radius."
)

if search:

    with st.spinner("Searching the NBN Atlas…"):

        try:
            df, record_count = atlas_species(
                lat=lat,
                lon=lon,
                size_km=size_km,
                taxon=taxon,
            )

        except requests.RequestException as exc:
            st.error(
                "The NBN Atlas could not be reached right now."
            )
            st.code(str(exc))
            st.stop()

        except Exception as exc:
            st.error("Something went wrong while reading the Atlas response.")
            st.code(f"{type(exc).__name__}: {exc}")
            st.stop()

        if not df.empty:
            with st.spinner("Looking up common names…"):
                common_names = lookup_common_names(
                    tuple(sorted(df["Species"].unique()))
                )

            df.insert(
                1,
                "Common name",
                df["Species"].map(common_names).fillna("—"),
            )

    st.divider()
    st.subheader("Wildlife recorded in this area")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Species", len(df))

    with col2:
        st.metric("Matching records", f"{record_count:,}")

    if df.empty:
        st.info(
            "No qualifying species records were returned for this search."
        )

    else:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
        )

st.divider()

with st.expander("About the data & licensing"):
    st.markdown(
        """
        **Data source:** National Biodiversity Network (NBN) Atlas,
        covering England, Scotland, Wales and Northern Ireland.

        This prototype queries the public NBN Atlas occurrence service
        and does not request restricted occurrence locations.

        The query is limited to records carrying the NBN's open-use
        licences: CC0, CC-BY and OGL. These licences have different
        attribution requirements, so the licensing and data-partner
        acknowledgements should be checked before a wider or commercial
        release.

        The results represent **recorded observations**, not a complete
        inventory of all animals that definitely occur at the location.

        **Common names** are looked up separately from the NBN Atlas's
        own species database and reflect its preferred vernacular name
        for each species. Some scientific names — particularly for less
        commonly recorded insects and invertebrates — have no widely
        used English common name and will show as "—".
        """
    )

st.caption(
    "NBN Trust (2026). The National Biodiversity Network (NBN) Atlas."
)
