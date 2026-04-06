#!/usr/bin/env python3
"""
Google Takeout Metadata Embedder
Incrusta la metadata de los archivos .json de Google Takeout
directamente en el EXIF de las fotos JPG.
"""

import os
import json
import glob
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone
from pathlib import Path

try:
    import piexif
    from PIL import Image, ImageTk
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "piexif", "Pillow", "--break-system-packages", "-q"])
    import piexif
    from PIL import Image, ImageTk


# ── helpers ──────────────────────────────────────────────────────────────────

def get_base_name(path: str) -> str:
    """Quita extensión y sufijos de Google Takeout para obtener nombre base."""
    name = Path(path).name
    name = re.sub(r'\.supplemental-metadata\.json$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(edited\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\.(jpg|jpeg|png|heic|mp4|mov)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\.json$', '', name, flags=re.IGNORECASE)
    return name.strip()


def find_json_for_image(img_path: str, json_map: dict) -> dict | None:
    """Encuentra el JSON correspondiente a una imagen."""
    base = get_base_name(img_path)
    for json_base, data in json_map.items():
        if get_base_name(json_base) == base:
            return data
    return None


def timestamp_to_exif(ts: str) -> str:
    """Convierte Unix timestamp a formato EXIF 'YYYY:MM:DD HH:MM:SS'."""
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone()
    return dt.strftime('%Y:%m:%d %H:%M:%S')


def deg_to_dms_rational(deg: float):
    """Convierte grados decimales a formato DMS para EXIF GPS."""
    abs_deg = abs(deg)
    d = int(abs_deg)
    m_full = (abs_deg - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 6000)
    return [(d, 1), (m, 1), (s, 100)]


def embed_metadata(img_path: str, meta: dict) -> tuple[bool, str]:
    """
    Incrusta metadata JSON en el EXIF del JPEG.
    Retorna (éxito, mensaje).
    """
    try:
        # Cargar EXIF existente o crear vacío
        try:
            exif_dict = piexif.load(img_path)
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        changed = []

        # ── Fecha ────────────────────────────────────────────────────────────
        photo_time = meta.get("photoTakenTime") or meta.get("creationTime")
        if photo_time and photo_time.get("timestamp"):
            dt_str = timestamp_to_exif(photo_time["timestamp"])
            exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_str.encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str.encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str.encode()
            changed.append(f"fecha: {dt_str}")

        # ── GPS ──────────────────────────────────────────────────────────────
        geo = meta.get("geoData") or meta.get("geoDataExif")
        if geo and (geo.get("latitude") != 0 or geo.get("longitude") != 0):
            lat = geo["latitude"]
            lon = geo["longitude"]
            alt = geo.get("altitude", 0)

            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = deg_to_dms_rational(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = deg_to_dms_rational(lon)
            exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
            exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = (int(abs(alt) * 100), 100)
            changed.append(f"GPS: {lat:.5f}, {lon:.5f}")

        # ── Título / descripción ─────────────────────────────────────────────
        title = meta.get("title", "")
        if title:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = title.encode("utf-8", errors="replace")
            changed.append("título")

        desc = meta.get("description", "")
        if desc:
            exif_dict["0th"][piexif.ImageIFD.XPComment] = (desc + "\x00").encode("utf-16-le")
            changed.append("descripción")

        if not changed:
            return True, "sin cambios (metadata vacía)"

        # Escribir EXIF de vuelta en el archivo
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, img_path)

        return True, "✓ " + ", ".join(changed)

    except Exception as e:
        return False, f"✗ Error: {e}"


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Google Takeout — Metadata Embedder")
        self.geometry("780x620")
        self.minsize(640, 480)
        self.configure(bg="#F5F4F0")
        self.resizable(True, True)

        self.folder_path = tk.StringVar()
        self.backup = tk.BooleanVar(value=True)
        self.pairs: list[dict] = []   # [{img, json_data, base}, ...]

        self._build_ui()

    # ── construcción UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = 16

        # Barra superior
        top = tk.Frame(self, bg="#F5F4F0")
        top.pack(fill="x", padx=PAD, pady=(PAD, 8))

        tk.Label(top, text="Google Takeout — Metadata Embedder",
                 font=("Helvetica Neue", 17, "bold"), bg="#F5F4F0", fg="#1A1A1A").pack(side="left")

        # Selector de carpeta
        folder_frame = tk.Frame(self, bg="#F5F4F0")
        folder_frame.pack(fill="x", padx=PAD, pady=4)

        tk.Label(folder_frame, text="Carpeta:", bg="#F5F4F0", fg="#555",
                 font=("Helvetica Neue", 13)).pack(side="left")
        tk.Entry(folder_frame, textvariable=self.folder_path,
                 font=("Helvetica Neue", 12), width=52,
                 relief="flat", bd=1, highlightthickness=1,
                 highlightbackground="#CCCBC4", highlightcolor="#888").pack(side="left", padx=6)
        tk.Button(folder_frame, text="Explorar…", command=self._pick_folder,
                  font=("Helvetica Neue", 12), relief="flat",
                  bg="#E8E7E2", activebackground="#D4D3CE", cursor="hand2").pack(side="left")

        # Opciones + botones
        opts = tk.Frame(self, bg="#F5F4F0")
        opts.pack(fill="x", padx=PAD, pady=6)

        tk.Checkbutton(opts, text="Crear copia de seguridad antes de modificar",
                       variable=self.backup, bg="#F5F4F0",
                       font=("Helvetica Neue", 12), fg="#333",
                       activebackground="#F5F4F0").pack(side="left")

        self.scan_btn = tk.Button(opts, text="Escanear carpeta",
                                  command=self._scan, font=("Helvetica Neue", 12, "bold"),
                                  bg="#1A1A1A", fg="white", relief="flat",
                                  activebackground="#333", cursor="hand2", padx=12)
        self.scan_btn.pack(side="right")

        # Resumen
        self.summary_var = tk.StringVar(value="Selecciona una carpeta y haz clic en Escanear.")
        tk.Label(self, textvariable=self.summary_var, bg="#F5F4F0", fg="#555",
                 font=("Helvetica Neue", 12), anchor="w").pack(fill="x", padx=PAD, pady=2)

        # Tabla
        cols = ("archivo", "fecha", "gps", "estado")
        col_labels = {"archivo": "Archivo", "fecha": "Fecha foto", "gps": "GPS", "estado": "Estado"}

        tree_frame = tk.Frame(self, bg="#F5F4F0")
        tree_frame.pack(fill="both", expand=True, padx=PAD, pady=4)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                 yscrollcommand=scrollbar.set, height=14)
        scrollbar.config(command=self.tree.yview)

        widths = {"archivo": 260, "fecha": 160, "gps": 120, "estado": 200}
        for c in cols:
            self.tree.heading(c, text=col_labels[c])
            self.tree.column(c, width=widths[c], minwidth=60)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Barra de progreso
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=PAD, pady=4)

        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var, bg="#F5F4F0", fg="#555",
                 font=("Helvetica Neue", 11), anchor="w").pack(fill="x", padx=PAD)

        # Botón procesar
        btn_bar = tk.Frame(self, bg="#F5F4F0")
        btn_bar.pack(fill="x", padx=PAD, pady=(4, PAD))

        self.process_btn = tk.Button(btn_bar, text="▶  Incrustar metadata en todas las fotos",
                                     command=self._process,
                                     font=("Helvetica Neue", 13, "bold"),
                                     bg="#2563EB", fg="white", relief="flat",
                                     activebackground="#1D4ED8", cursor="hand2",
                                     padx=16, pady=8, state="disabled")
        self.process_btn.pack(side="left")

        tk.Button(btn_bar, text="Limpiar", command=self._clear,
                  font=("Helvetica Neue", 12), relief="flat",
                  bg="#E8E7E2", activebackground="#D4D3CE", cursor="hand2",
                  padx=12, pady=8).pack(side="left", padx=8)

        # Estilo tabla
        style = ttk.Style()
        style.configure("Treeview", font=("Helvetica Neue", 11), rowheight=24)
        style.configure("Treeview.Heading", font=("Helvetica Neue", 11, "bold"))

    # ── lógica ──────────────────────────────────────────────────────────────

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Selecciona tu carpeta de Google Takeout")
        if path:
            self.folder_path.set(path)
            self._scan()

    def _scan(self):
        folder = self.folder_path.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Selecciona una carpeta válida.")
            return

        # Buscar archivos recursivamente
        img_extensions = ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG")
        images = []
        for ext in img_extensions:
            images.extend(glob.glob(os.path.join(folder, "**", ext), recursive=True))

        # Cargar todos los JSON
        json_map = {}
        for jf in glob.glob(os.path.join(folder, "**", "*.json"), recursive=True):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                json_map[Path(jf).name] = data
            except Exception:
                pass

        # Emparejar
        self.pairs = []
        self.tree.delete(*self.tree.get_children())

        paired = 0
        for img in sorted(images):
            meta = find_json_for_image(img, json_map)
            self.pairs.append({"img": img, "meta": meta})

            name = Path(img).name
            if meta:
                paired += 1
                pt = meta.get("photoTakenTime") or meta.get("creationTime")
                fecha = ""
                if pt and pt.get("timestamp"):
                    dt = datetime.fromtimestamp(int(pt["timestamp"]), tz=timezone.utc).astimezone()
                    fecha = dt.strftime("%Y-%m-%d %H:%M")
                geo = meta.get("geoData") or {}
                gps_val = f"{geo.get('latitude',0):.4f}, {geo.get('longitude',0):.4f}" \
                          if geo.get("latitude") else "—"
                self.tree.insert("", "end", values=(name, fecha, gps_val, "pendiente"),
                                 tags=("paired",))
            else:
                self.tree.insert("", "end", values=(name, "—", "—", "sin JSON"),
                                 tags=("nojson",))

        self.tree.tag_configure("paired", foreground="#1A1A1A")
        self.tree.tag_configure("nojson", foreground="#AAA")

        total = len(images)
        self.summary_var.set(
            f"Encontradas {total} fotos — {paired} con JSON de metadata, "
            f"{total - paired} sin JSON."
        )

        if paired > 0:
            self.process_btn.config(state="normal")
        else:
            self.process_btn.config(state="disabled")
            if total > 0:
                messagebox.showwarning("Sin metadata",
                    "No se encontraron archivos JSON de Takeout en esta carpeta.\n"
                    "Asegúrate de tener los .json junto a las fotos.")

    def _process(self):
        if not self.pairs:
            return
        self.process_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        threading.Thread(target=self._run_embed, daemon=True).start()

    def _run_embed(self):
        items = self.tree.get_children()
        total = len([p for p in self.pairs if p["meta"]])
        done = 0

        for idx, (item, pair) in enumerate(zip(items, self.pairs)):
            if pair["meta"] is None:
                continue

            img_path = pair["img"]
            self.status_var.set(f"Procesando: {Path(img_path).name}")

            # Backup opcional
            if self.backup.get():
                backup_path = img_path + ".bak"
                if not os.path.exists(backup_path):
                    import shutil
                    shutil.copy2(img_path, backup_path)

            ok, msg = embed_metadata(img_path, pair["meta"])
            done += 1

            tag = "ok" if ok else "error"
            self.tree.item(item, values=(
                Path(img_path).name,
                self.tree.item(item)["values"][1],
                self.tree.item(item)["values"][2],
                msg
            ), tags=(tag,))
            self.tree.tag_configure("ok", foreground="#166534")
            self.tree.tag_configure("error", foreground="#991B1B")

            pct = int(done / total * 100)
            self.progress["value"] = pct

        self.status_var.set(f"Completado — {done} fotos procesadas.")
        self.scan_btn.config(state="normal")
        messagebox.showinfo("Listo",
            f"Se procesaron {done} fotos.\n"
            + ("Se crearon copias .bak como respaldo." if self.backup.get() else ""))

    def _clear(self):
        self.pairs = []
        self.tree.delete(*self.tree.get_children())
        self.folder_path.set("")
        self.summary_var.set("Selecciona una carpeta y haz clic en Escanear.")
        self.status_var.set("")
        self.progress["value"] = 0
        self.process_btn.config(state="disabled")


# ── entrada ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
