import os
import csv
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import shapefile
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit,
                             QPushButton, QFileDialog, QVBoxLayout, QHBoxLayout,
                             QMessageBox, QCheckBox)
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl, Qt
import folium
import sys
import simplekml

# EXIF and export helper functions
def get_exif_data(image_path):
    image = Image.open(image_path)
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

def convert_to_degrees(value):
    # Handle both IFDRational objects and tuple pairs
    def to_float(r):
        try:
            return float(r)
        except (TypeError, ValueError):
            return r[0] / r[1]

    d = to_float(value[0])
    m = to_float(value[1])
    s = to_float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def get_coordinates(exif_data):
    gps = exif_data.get('GPSInfo')
    if not gps:
        return None
    lat = gps.get('GPSLatitude')
    lat_ref = gps.get('GPSLatitudeRef')
    lon = gps.get('GPSLongitude')
    lon_ref = gps.get('GPSLongitudeRef')
    if lat and lon and lat_ref and lon_ref:
        latitude = convert_to_degrees(lat)
        if lat_ref != 'N': latitude = -latitude
        longitude = convert_to_degrees(lon)
        if lon_ref != 'E': longitude = -longitude
        return (latitude, longitude)
    return None

def save_to_csv(coords, csv_path):
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['filename', 'latitude', 'longitude'])
        for fn, lat, lon, _ in coords:
            writer.writerow([fn, lat, lon])

def save_to_kml(coords, kml_path):
    kml = simplekml.Kml()
    for fn, lat, lon, _ in coords:
        kml.newpoint(name=fn, coords=[(lon, lat)])
    kml.save(kml_path)

def save_to_shapefile(coords, shp_base):
    # shp_base without extension
    with shapefile.Writer(shp_base) as shp:
        shp.field('filename', 'C')
        for fn, lat, lon, _ in coords:
            shp.point(lon, lat)
            shp.record(fn)
    # write .prj
    prj = shp_base + '.prj'
    prj_text = "EPSG:4326"
    with open(prj, 'w') as f:
        f.write(prj_text)

# Class: GeoSnapExtractor
class GeoSnapExtractor(QWidget):
    def __init__(self):
        super().__init__()
        # Window setup
        self.setWindowTitle("GeoSnap - Drone Image Coordinate Extractor")
        self.setGeometry(100, 100, 1000, 600)
        self.setMinimumSize(800, 500)
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon("drone_icon.png"))

        self.folder_path = ""
        self.output_folder_path = ""
        self.coordinates = []

        self.init_ui()

    def init_ui(self):
        # Set up main two-panel layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Left control panel
        control_layout = QVBoxLayout()
        control_layout.setSpacing(12)

        self.title_label = QLabel("Drone Image Coordinate Extractor")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size:22pt; font-weight:bold;")  # increased for visual hierarchy
        control_layout.addWidget(self.title_label)

        self.folder_entry = QLineEdit()
        self.folder_entry.setReadOnly(True)
        self.folder_entry.setPlaceholderText("Select image folder... (or drag here)")
        self.folder_entry.setStyleSheet("padding-right:24px;")
        control_layout.addWidget(self.folder_entry)
        
        self.browse_button = QPushButton("Browse…")  # ellipsis
        self.browse_button.setFixedHeight(32)
        # subtle button style with hover
        self.browse_button.setStyleSheet(
            '''
            QPushButton {
                border-radius: 8px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            '''
        )
        self.browse_button.clicked.connect(self.browse_folder)
        control_layout.addWidget(self.browse_button)

        # Output folder selection
        self.output_entry = QLineEdit()
        self.output_entry.setReadOnly(True)
        self.output_entry.setPlaceholderText("Select output folder...")
        control_layout.addWidget(self.output_entry)
        self.output_browse = QPushButton("Browse…")
        self.output_browse.setFixedHeight(32)
        self.output_browse.setStyleSheet(self.browse_button.styleSheet())  # reuse style
        self.output_browse.clicked.connect(self.browse_output_folder)
        control_layout.addWidget(self.output_browse)

        self.extract_button = QPushButton("Extract Coordinates")
        self.extract_button.setFixedSize(160, 44)
        self.extract_button.setStyleSheet(
            '''
            QPushButton {
                background-color: #007aff;
                color: white;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #0051c7;
            }
            '''
        )
        self.extract_button.clicked.connect(self.extract_coordinates)
        control_layout.addWidget(self.extract_button)

        # File type selection checkboxes
        self.csv_checkbox = QCheckBox("CSV")
        self.csv_checkbox.setChecked(True)
        self.kml_checkbox = QCheckBox("KML")
        self.kml_checkbox.setChecked(True)
        self.shp_checkbox = QCheckBox("Shapefile")
        self.shp_checkbox.setChecked(True)
        filetype_layout = QHBoxLayout()
        filetype_layout.setSpacing(8)
        filetype_layout.addWidget(self.csv_checkbox)
        filetype_layout.addWidget(self.kml_checkbox)
        filetype_layout.addWidget(self.shp_checkbox)
        control_layout.addLayout(filetype_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:gray; font-size:14pt;")  # increased body font
        control_layout.addWidget(self.status_label)

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.setFixedHeight(32)
        self.open_folder_button.setStyleSheet(
            '''
            QPushButton {
                border-radius: 8px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            '''
        )
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.open_folder_button.setEnabled(False)
        control_layout.addWidget(self.open_folder_button)

        control_layout.addStretch()

        # Right preview panel
        preview_layout = QVBoxLayout()
        preview_layout.setSpacing(12)
        self.map_view = QWebEngineView()
        # allow local file to load external (HTTPS) resources
        settings = self.map_view.settings()
        # Use correct enum reference for WebAttribute
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.map_view.setFixedSize(400, 400)
        # placeholder until extraction
        placeholder = '<div style="font-size:16pt;color:#888;text-align:center;margin-top:160px;">Preview will appear here after extraction</div>'
        self.map_view.setHtml(placeholder)
        self.map_view.setStyleSheet("border:1px solid #ccc; border-radius:8px;")
        preview_layout.addWidget(self.map_view)
        preview_layout.addStretch()

        # Assemble main layout
        main_layout.addLayout(control_layout)
        main_layout.addLayout(preview_layout)
        self.setLayout(main_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            self.folder_entry.setText(folder)
            self.folder_path = folder

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_entry.setText(folder)
            self.output_folder_path = folder

    def dragEnterEvent(self, event):
        # accept folder drag-and-drop
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            if os.path.isdir(path):
                event.acceptProposedAction()

    def dropEvent(self, event):
        path = event.mimeData().urls()[0].toLocalFile()
        if os.path.isdir(path):
            self.folder_entry.setText(path)
            self.folder_path = path

    def extract_coordinates(self):
        # feedback start
        if not self.folder_path:
            QMessageBox.warning(self, "Warning", "Please select an image folder.")
            return
        if not self.output_folder_path:
            QMessageBox.warning(self, "Warning", "Please select an output folder.")
            return
        # ensure at least one format is selected
        if not (self.csv_checkbox.isChecked() or self.kml_checkbox.isChecked() or self.shp_checkbox.isChecked()):
            QMessageBox.warning(self, "Warning", "Select at least one export format.")
            return
        self.status_label.setText("Extracting…")
        self.status_label.setStyleSheet("color:gray; font-size:14pt;")

        self.coordinates = []

        for filename in os.listdir(self.folder_path):
            if filename.lower().endswith(('jpg', 'jpeg', 'png')):
                image_path = os.path.join(self.folder_path, filename)
                exif_data = get_exif_data(image_path)
                if exif_data:
                    gps_coords = get_coordinates(exif_data)
                    if gps_coords:
                        self.coordinates.append((filename, gps_coords[0], gps_coords[1], ""))

        self.update_map()
        # no GPS data found
        if not self.coordinates:
            QMessageBox.information(self, "No GPS Data", "No images with GPS data found.")
            self.status_label.setText("⚠ No GPS data found.")
            self.status_label.setStyleSheet("color:orange; font-size:14pt;")
            return

        # Save outputs to exports folder
        export_dir = self.output_folder_path
        os.makedirs(export_dir, exist_ok=True)
        if self.csv_checkbox.isChecked():
            save_to_csv(self.coordinates, os.path.join(export_dir, 'coordinates.csv'))
        if self.kml_checkbox.isChecked():
            save_to_kml(self.coordinates, os.path.join(export_dir, 'coordinates.kml'))
        if self.shp_checkbox.isChecked():
            save_to_shapefile(self.coordinates, os.path.join(export_dir, 'coordinates'))
        # Update status and enable open folder button
        self.status_label.setText(f"✔ Done! Files saved to: {export_dir}")
        self.status_label.setStyleSheet("color:green; font-size:14pt;")
        self.open_folder_button.setEnabled(True)

    def update_map(self):
        # create map with both street and satellite base layers (no default view)
        map_object = folium.Map(tiles=None)
        # add street map layer
        folium.TileLayer('OpenStreetMap', name='Street Map', control=True).add_to(map_object)
        # add satellite imagery layer
        folium.TileLayer('Esri.WorldImagery', name='Satellite', control=True).add_to(map_object)
        for filename, lat, lon, date in self.coordinates:
            folium.Marker([lat, lon], popup=filename).add_to(map_object)

        # zoom map to the area covering all markers
        if self.coordinates:
            lats = [lat for _, lat, lon, _ in self.coordinates]
            lons = [lon for _, lat, lon, _ in self.coordinates]
            map_object.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
        # add layer control for toggling
        folium.LayerControl(position='topright', collapsed=False).add_to(map_object)
        map_file = os.path.join(os.getcwd(), "map.html")
        map_object.save(map_file)
        self.map_view.setUrl(QUrl.fromLocalFile(map_file))

    def open_output_folder(self):
        if self.output_folder_path:
            os.startfile(self.output_folder_path)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = GeoSnapExtractor()
    main_window.show()
    sys.exit(app.exec())
