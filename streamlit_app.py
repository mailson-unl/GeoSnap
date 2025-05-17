import streamlit as st
import os
import csv
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import shapefile
import folium
from folium.plugins import FastMarkerCluster
import simplekml
import base64
import io
import zipfile
import pandas as pd

# Core helper functions (copied and adapted from main.py)
def get_exif_data(image_bytes):
    try:
        image = Image.open(image_bytes)
        exif_data = {}
        info = image._getexif() or {}
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == 'GPSInfo':
                gps_data = {}
                for t, v in value.items():
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_data[sub_decoded] = v
                exif_data['GPSInfo'] = gps_data
            else:
                exif_data[decoded] = value
        return exif_data
    except Exception as e:
        st.error(f"Error reading EXIF data: {e}")
        return None

def convert_to_degrees(value):
    def to_float(r):
        try:
            return float(r)
        except (TypeError, ValueError):
            if isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], (int, float)) and isinstance(r[1], (int, float)) and r[1] != 0:
                return r[0] / r[1]
            elif isinstance(r, (int, float)): # It might already be a float if IFD field type is RATIONAL or SRATIONAL
                 return float(r)
            st.warning(f"Could not convert GPS coordinate component to float: {r}")
            raise ValueError("Invalid GPS coordinate component")


    d = to_float(value[0])
    m = to_float(value[1])
    s = to_float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def get_coordinates(exif_data):
    if not exif_data:
        return None
    gps = exif_data.get('GPSInfo')
    if not gps:
        return None
    
    lat_value = gps.get('GPSLatitude')
    lat_ref = gps.get('GPSLatitudeRef')
    lon_value = gps.get('GPSLongitude')
    lon_ref = gps.get('GPSLongitudeRef')

    if lat_value and lon_value and lat_ref and lon_ref:
        try:
            latitude = convert_to_degrees(lat_value)
            if lat_ref != 'N': latitude = -latitude
            longitude = convert_to_degrees(lon_value)
            if lon_ref != 'E': longitude = -longitude
            return (latitude, longitude)
        except ValueError as e:
            st.warning(f"Could not parse GPS coordinates: {e}")
            return None
        except Exception as e:
            st.warning(f"An unexpected error occurred during coordinate conversion: {e}")
            return None
    return None

def save_to_csv_bytes(coords):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['filename', 'latitude', 'longitude'])
    for fn, lat, lon in coords: # Removed placeholder for date
        writer.writerow([fn, lat, lon])
    return output.getvalue().encode('utf-8')

def save_to_kml_bytes(coords):
    kml = simplekml.Kml()
    for fn, lat, lon in coords: # Removed placeholder for date
        kml.newpoint(name=fn, coords=[(lon, lat)])
    return kml.kml().encode('utf-8')

def save_to_shapefile_bytes(coords):
    shp_io = io.BytesIO()
    dbf_io = io.BytesIO()
    shx_io = io.BytesIO()

    with shapefile.Writer(shp=shp_io, dbf=dbf_io, shx=shx_io) as shp:
        shp.field('filename', 'C')
        for fn, lat, lon in coords: # Removed placeholder for date
            shp.point(lon, lat)
            shp.record(fn)
    
    # Create .prj file content
    # WGS 84 Geographic Coordinate System
    prj_text = '''GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'''
    prj_io = io.BytesIO(prj_text.encode('utf-8'))

    return {
        "shp": shp_io.getvalue(),
        "shx": shx_io.getvalue(),
        "dbf": dbf_io.getvalue(),
        "prj": prj_io.getvalue()
    }

# --- Streamlit App UI and Logic ---
st.set_page_config(page_title="GeoSnap - Drone Image Extractor", layout="wide")

st.title("GeoSnap - Drone Image Coordinate Extractor")
st.markdown("Upload your drone images (JPG, JPEG, PNG) to extract GPS coordinates.")

uploaded_files = st.file_uploader(
    "Choose image files",
    accept_multiple_files=True,
    help="Select one or more drone images containing GPS EXIF data. Supported extensions: JPG, JPEG, PNG."
)

if 'coordinates' not in st.session_state:
    st.session_state.coordinates = []
if 'map_html' not in st.session_state:
    st.session_state.map_html = None

if uploaded_files:
    st.info(f"{len(uploaded_files)} file(s) selected.")
    
    extracted_coords_for_df = []

    if st.button("Extract Coordinates", key="extract_button", help="Process uploaded images and extract GPS data."):
        st.session_state.coordinates = [] # Reset previous results
        st.session_state.map_html = None
        
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, uploaded_file in enumerate(uploaded_files):
            # Skip unsupported file types by extension
            if not uploaded_file.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                st.warning(f"Skipping unsupported file type: {uploaded_file.name}")
                continue
            status_text.text(f"Processing {uploaded_file.name}...")
            image_bytes = io.BytesIO(uploaded_file.getvalue())
            exif_data = get_exif_data(image_bytes)
            if exif_data:
                gps_coords = get_coordinates(exif_data)
                if gps_coords:
                    st.session_state.coordinates.append((uploaded_file.name, gps_coords[0], gps_coords[1]))
                    extracted_coords_for_df.append({
                        "filename": uploaded_file.name,
                        "latitude": gps_coords[0],
                        "longitude": gps_coords[1]
                    })
            progress_bar.progress((i + 1) / len(uploaded_files))
        
        status_text.text("Extraction complete!")

        if not st.session_state.coordinates:
            st.warning("No GPS data found in the selected images or failed to parse coordinates.")
        else:
            st.success(f"Successfully extracted coordinates from {len(st.session_state.coordinates)} images.")

# Display extracted coordinates in a table
if st.session_state.coordinates:
    st.subheader("Extracted Coordinates")
    df = pd.DataFrame(st.session_state.coordinates, columns=['Filename', 'Latitude', 'Longitude'])
    st.dataframe(df, use_container_width=True)

    # Map Display
    st.subheader("Map Preview")
    
    # Create map
    map_object = folium.Map(tiles="OpenStreetMap", prefer_canvas=True)
    
    # Add satellite imagery layer
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Esri Satellite',
        overlay=False,
        control=True
    ).add_to(map_object)

    # Add markers
    points = [(lat, lon) for _, lat, lon in st.session_state.coordinates]
    
    if points:
        # Use FastMarkerCluster for potentially many points
        # marker_cluster = FastMarkerCluster(points).add_to(map_object) # FastMarkerCluster might need lat/lon swapped or specific formatting
        
        for fn, lat, lon in st.session_state.coordinates:
            folium.Marker([lat, lon], popup=f"{fn}\nLat: {lat:.5f}, Lon: {lon:.5f}").add_to(map_object)

        # Fit map to bounds
        map_object.fit_bounds(points) # points should be [[min_lat, min_lon], [max_lat, max_lon]] or list of [lat,lon]
                                      # folium automatically calculates bounds if points are added

    folium.LayerControl().add_to(map_object)
    
    # Save map to an in-memory HTML file
    map_data = io.BytesIO()
    map_object.save(map_data, close_file=False)
    st.session_state.map_html = map_data.getvalue().decode()

if st.session_state.map_html:
    st.components.v1.html(st.session_state.map_html, height=500, scrolling=True)


# Export options
if st.session_state.coordinates:
    st.subheader("Export Coordinates")
    
    export_formats = st.multiselect(
        "Select export format(s):",
        options=["CSV", "KML", "Shapefile (ZIP)"],
        default=["CSV", "KML"]
    )

    if st.button("Download Selected Formats", key="download_button"):
        if not export_formats:
            st.warning("Please select at least one format to download.")
        else:
            # Create a zip file in memory if multiple formats or Shapefile is selected
            if len(export_formats) > 1 or "Shapefile (ZIP)" in export_formats:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    if "CSV" in export_formats:
                        csv_bytes = save_to_csv_bytes(st.session_state.coordinates)
                        zip_file.writestr("coordinates.csv", csv_bytes)
                    if "KML" in export_formats:
                        kml_bytes = save_to_kml_bytes(st.session_state.coordinates)
                        zip_file.writestr("coordinates.kml", kml_bytes)
                    if "Shapefile (ZIP)" in export_formats:
                        shp_files = save_to_shapefile_bytes(st.session_state.coordinates)
                        zip_file.writestr("coordinates.shp", shp_files["shp"])
                        zip_file.writestr("coordinates.shx", shp_files["shx"])
                        zip_file.writestr("coordinates.dbf", shp_files["dbf"])
                        zip_file.writestr("coordinates.prj", shp_files["prj"])
                
                st.download_button(
                    label="Download All as ZIP",
                    data=zip_buffer.getvalue(),
                    file_name="geosnap_coordinates.zip",
                    mime="application/zip"
                )
            elif "CSV" in export_formats: # Single CSV
                 csv_bytes = save_to_csv_bytes(st.session_state.coordinates)
                 st.download_button(
                    label="Download CSV",
                    data=csv_bytes,
                    file_name="coordinates.csv",
                    mime="text/csv"
                )
            elif "KML" in export_formats: # Single KML
                kml_bytes = save_to_kml_bytes(st.session_state.coordinates)
                st.download_button(
                    label="Download KML",
                    data=kml_bytes,
                    file_name="coordinates.kml",
                    mime="application/vnd.google-earth.kml+xml"
                )


st.markdown("---")
st.markdown("Developed with Streamlit.")
