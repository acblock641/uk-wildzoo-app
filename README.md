# UK Wildlife Explorer

A simple public Streamlit web app that queries the NBN Atlas for animal
species recorded around a user's location in England, Scotland, Wales or
Northern Ireland.

This is a UK-wide sibling of the Isle of Man Wildlife Explorer app, kept as
a separate project. The app logic is the same; the differences are:

- No `stateProvince` filter is applied, so searches are not restricted to
  a single area — the NBN Atlas radius search alone determines the area.
- The location-validation bounding box covers the whole of the UK
  (England, Scotland, Wales, Northern Ireland) including outlying islands
  such as Shetland, the Outer Hebrides and the Isles of Scilly, rather
  than just the Isle of Man.
- Branding/copy updated accordingly.

## Files

- `streamlit_app.py` — the app
- `requirements.txt` — Python dependencies

## Run locally

From a terminal:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Then open the local URL Streamlit gives you.

## Deploy publicly

The easiest route is Streamlit Community Cloud:

1. Create a GitHub account at https://github.com/ if you do not already have one.
2. Create a **public** GitHub repository (separate from your Isle of Man
   repository, e.g. `uk-wildlife-explorer`).
3. Upload `streamlit_app.py` and `requirements.txt` to the repository.
4. Go to https://share.streamlit.io/
5. Sign in with GitHub.
6. Choose **Create app**.
7. Select your repository, branch (`main`) and file:
   `streamlit_app.py`
8. Choose an app subdomain, e.g. `uk-wildlife-explorer`.
9. Deploy.

The resulting URL will be:

`https://YOUR-SUBDOMAIN.streamlit.app`

Anyone with that public URL can use the app.

## Important data note

The NBN Atlas has dataset-level and record-level licensing and access-control
conditions. This prototype queries only public Atlas data and restricts
records to CC0, CC-BY and OGL. Before using the app commercially or publishing
it as a mature service, review the NBN guidance on data use and attribution and
make sure the Data Partners and datasets used by the app are credited as
required.

## Location privacy

The app does not write user locations to a database. Browser location is only
requested when the user presses the geolocation control and the selected
coordinates are then used for the Atlas query.

Browser geolocation requires a secure context (HTTPS), which Streamlit
Community Cloud provides.

## Scale note

Because this app searches the whole of the UK rather than one small island,
species counts and record totals for busy urban or well-recorded areas may
be noticeably larger than in the Isle of Man version. The 1 km / 10 km
search-area logic and the radius-vs-square caveat are unchanged from that
version.
