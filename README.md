# 📷 Google Takeout Metadata Embedder

A lightweight Python desktop app that restores EXIF metadata to your photos after a Google Takeout export.

When you download your photos from Google Photos via Takeout, the metadata (date taken, GPS coordinates, title, description) is stripped from the image files and placed in separate `.json` sidecar files. This tool reads those JSON files and writes the metadata back into the EXIF headers of your JPEGs — where it belongs.

---

## Features

- **Automatic pairing** — scans a folder recursively and matches each photo to its JSON sidecar by filename, handling Google's naming quirks (e.g. `photo(1).jpg` → `photo(1).jpg.supplemental-metadata.json`)
- **Preview before processing** — shows a table with each photo's detected date, GPS, and pairing status before touching any file
- **Writes to EXIF** — embeds `DateTimeOriginal`, GPS coordinates (latitude, longitude, altitude), title, and description
- **Backup option** — optionally creates a `.bak` copy of each original before modifying it
- **No internet required** — runs entirely offline; nothing leaves your machine
- **Native GUI** — built with Tkinter, which ships with Python on macOS; no Electron, no browser

---

## Requirements

- Python 3.9+
- [Pillow](https://python-pillow.org/)
- [piexif](https://piexif.readthedocs.io/)

---

## Installation

```bash
# Clone the repo
git clone https://github.com/your-username/takeout-meta.git
cd takeout-meta

# Install dependencies
pip3 install piexif Pillow
```

> On macOS, if `pip3` is not found, use `python3 -m pip install piexif Pillow`

---

## Usage

```bash
python3 takeout_meta.py
```

1. Click **Explorar…** and select your Google Takeout folder (the one containing your photos and their `.json` files — subfolders are scanned recursively)
2. Click **Escanear carpeta** — the table will show all detected photos, their dates, GPS status, and whether a matching JSON was found
3. Optionally enable/disable the **backup** checkbox
4. Click **▶ Incrustar metadata en todas las fotos** to write the EXIF data

---

## How Google Takeout works (and why this is needed)

Google Photos stores metadata separately from the image binary. When you use [Google Takeout](https://takeout.google.com/) to export your library, each photo comes with a companion JSON file:

```
My Photos/
├── vacation.jpg
├── vacation.jpg.supplemental-metadata.json   ← metadata lives here
├── DSC_0042.JPG
└── DSC_0042.JPG.supplemental-metadata.json
```

The JSON contains fields like:

```json
{
  "photoTakenTime": { "timestamp": "1404752881" },
  "geoData": { "latitude": 4.6097, "longitude": -74.0817, "altitude": 2600 },
  "title": "vacation.jpg",
  "description": "Bogotá, Colombia"
}
```

This tool reads those fields and writes them into the EXIF IFD blocks of the JPEG file using the [piexif](https://piexif.readthedocs.io/) library.

---

## What gets embedded

| JSON field | EXIF tag written |
|---|---|
| `photoTakenTime.timestamp` | `DateTime`, `DateTimeOriginal`, `DateTimeDigitized` |
| `geoData.latitude/longitude` | `GPSLatitude`, `GPSLatitudeRef`, `GPSLongitude`, `GPSLongitudeRef` |
| `geoData.altitude` | `GPSAltitude`, `GPSAltitudeRef` |
| `title` | `ImageDescription` |
| `description` | `XPComment` |

---

## Limitations

- Only JPEG files are modified (EXIF is a JPEG/TIFF standard; PNG uses a different metadata scheme)
- PNG, HEIC, and video files are listed but skipped
- If a photo has no matching JSON, it is displayed in the table but left untouched
- Existing EXIF tags in the photo are preserved; only the fields above are overwritten

---

## License

Creative Commons

---

## Acknowledgements

- [piexif](https://github.com/hMatoba/Piexif) by hMatoba
- [Pillow](https://python-pillow.org/) — Python Imaging Library fork
- Built to solve a real problem after a Google Photos → self-hosted migration
