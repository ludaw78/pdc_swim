import reflex as rx
import urllib.request
import re
import html
import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Union
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel

# ── 1. CONFIGURATION NAGEURS ─────────────────────────────────────────────────
# Pour ajouter un nageur : ajouter une entrée dans ce dict.
# La clé (ex: "tristan") est utilisée dans l'URL : app.com/?nageur=tristan
# photo : nom du fichier dans assets/ (laisser "" si pas de photo)

SWIMMERS = {
    "tristan":  {"name": "Tristan",  "birth_year": 2011, "gender": "M", "ffn_id": "3518107",  "photo": "photo_tristan.jpg"},
    "louis":    {"name": "Louis",    "birth_year": 2012, "gender": "M", "ffn_id": "3751537",  "photo": "photo_louis.jpg"},
    "anthony":  {"name": "Anthony",  "birth_year": 2010, "gender": "M", "ffn_id": "3700947",  "photo": "photo_anthony.jpg"},
    "matthieu": {"name": "Matthieu", "birth_year": 2011, "gender": "M", "ffn_id": "2982827",  "photo": "photo_matthieu.jpg"},
    "aline":    {"name": "Aline",    "birth_year": 2011, "gender": "F", "ffn_id": "3061675",  "photo": "photo_aline.jpg"},
    "nola":     {"name": "Nola",     "birth_year": 2011, "gender": "F", "ffn_id": "3231817",  "photo": "photo_nola.jpg"},
    "arthur":   {"name": "Arthur",   "birth_year": 2014, "gender": "M", "ffn_id": "3736819",  "photo": "photo_arthur.jpg"},
    "corentin": {"name": "Corentin", "birth_year": 2006, "gender": "M", "ffn_id": "2550147",  "photo": "photo_corentin.jpg"},
}

DEFAULT_SWIMMER = "tristan"  # affiché si pas de paramètre ?nageur= dans l'URL

# ── 2. PARSEUR ────────────────────────────────────────────────────────────────

@dataclass
class Split:
    distance_m: int
    cumulative_time: str
    lap_time: str
    half_time: Optional[str] = None

@dataclass
class Performance:
    epreuve: str
    temps_final: str
    age_categorie: str
    points: str
    club: str
    pays: str
    date: str
    type_compet: str
    competition: str
    lien_resultats: str
    splits: list[Split] = field(default_factory=list)

def strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()

def find_all(pattern: str, text: str) -> list[str]:
    return re.findall(pattern, text, re.DOTALL)

def find_one(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else default

def extract_split_from_cells(cells: list[str], offset: int) -> Optional[Split]:
    if offset + 3 > len(cells): return None
    dist_text = strip_tags(cells[offset])
    dist_match = re.match(r"(\d+)", dist_text)
    if not dist_match: return None
    return Split(
        distance_m=int(dist_match.group(1)),
        cumulative_time=strip_tags(cells[offset+1]),
        lap_time=strip_tags(cells[offset+2]).replace("(", "").replace(")", ""),
        half_time=strip_tags(cells[offset+3]).replace("[", "").replace("]", "") if offset + 3 < len(cells) else None
    )

def parse_splits(tippy_raw: str) -> list[Split]:
    decoded = html.unescape(tippy_raw)
    splits = []
    for row in find_all(r"<tr[^>]*>(.*?)</tr>", decoded):
        cells = find_all(r"<td[^>]*>(.*?)</td>", row)
        raw_td_attrs = find_all(r"<td([^>]*)>", row)
        separator_idx = next((i for i, attrs in enumerate(raw_td_attrs) if "border-right" in attrs), None)
        if separator_idx is not None:
            left  = extract_split_from_cells(cells, 0)
            right = extract_split_from_cells(cells, separator_idx + 1)
            if left:  splits.append(left)
            if right: splits.append(right)
        else:
            s = extract_split_from_cells(cells, 0)
            if s: splits.append(s)
    return sorted(splits, key=lambda s: s.distance_m)

def parse_row(row: str, base_url: str = "https://ffn.extranat.fr") -> Optional[Performance]:
    th = find_one(r"<th[^>]*>(.*?)</th>", row)
    if not th: return None
    tds = find_all(r"<td[^>]*>(.*?)</td>", row)
    if len(tds) < 8: return None
    tippy_matches = re.findall(r'data-tippy-content="((?:[^"\\]|\\.)*)"', tds[0], re.DOTALL)
    if not tippy_matches:
        tippy_matches = re.findall(r"data-tippy-content='((?:[^'\\]|\\.)*)'", tds[0], re.DOTALL)
    raw_tippy = tippy_matches[0] if tippy_matches else None
    splits = parse_splits(raw_tippy.replace("\\\\'", "'").replace("\\'", "'")) if raw_tippy else []
    ps = find_all(r"<p[^>]*>(.*?)</p>", tds[3])
    lien_href = find_one(r'href=["\']([^"\']+)["\']', tds[6])
    return Performance(
        epreuve=strip_tags(th),
        temps_final=strip_tags(tds[0]),
        age_categorie=strip_tags(tds[1]).strip("()"),
        points=strip_tags(tds[2]),
        club=strip_tags(tds[3].split("<p")[0]),
        pays=strip_tags(tds[3].split("<p")[2]) if len(tds[3].split("<p")) > 2 else "",
        date=strip_tags(tds[4]),
        type_compet=strip_tags(tds[5]),
        competition=strip_tags(ps[0]) if ps else strip_tags(tds[3]),
        lien_resultats=base_url + lien_href if lien_href else "",
        splits=splits
    )

# ── 3. TYPES REFLEX ───────────────────────────────────────────────────────────

class SplitRow(BaseModel):
    dist:    str
    cumul:   str
    partiel: str
    half:    str

class Top10Entry(BaseModel):
    rang:  str
    nom:   str
    temps: str
    moi:   bool

class QualifRow(BaseModel):
    picto:  str
    label:  str
    temps:  str
    ecart:  str
    qualif: bool

class Result(BaseModel):
    E: str
    T: str
    P: str
    D: str
    B: str
    S: str
    N: str
    V: str

# ── 4. CONSTANTES ─────────────────────────────────────────────────────────────

GRILLES = {
    "F": {
        "U18+": {
            "50 NL":   ["30.72","29.84","29.00","27.78","27.09","26.84"],
            "100 NL":  ["1:07.53","1:04.44","1:02.21","1:00.14","58.65","58.10"],
            "200 NL":  ["2:27.28","2:20.76","2:15.86","2:10.93","2:07.55","2:06.50"],
            "400 NL":  ["5:08.68","4:55.22","4:45.35","4:35.88","4:27.47","4:26.55"],
            "800 NL":  ["10:34.00","10:13.38","9:59.00","9:28.20","9:09.46","9:08.98"],
            "1500 NL": ["19:58.50","19:33.57","19:05.00","18:13.35","17:39.73","17:36.38"],
            "50 Dos":  ["36.00","34.00","33.05","31.68","30.86","30.61"],
            "100 Dos": ["1:17.04","1:13.68","1:11.11","1:08.42","1:06.53","1:06.11"],
            "200 Dos": ["2:45.31","2:38.27","2:33.30","2:28.96","2:24.78","2:23.92"],
            "50 Bra":  ["39.00","37.55","36.53","35.12","34.14","33.94"],
            "100 Bra": ["1:27.07","1:23.42","1:20.49","1:17.17","1:15.30","1:14.56"],
            "200 Bra": ["3:02.76","2:58.72","2:53.00","2:47.30","2:42.66","2:41.64"],
            "50 Pap":  ["32.93","31.67","30.74","29.36","28.58","28.36"],
            "100 Pap": ["1:16.09","1:12.76","1:09.75","1:05.70","1:04.04","1:03.48"],
            "200 Pap": ["2:49.75","2:42.58","2:36.32","2:28.29","2:23.74","2:23.28"],
            "200 4 N": ["2:47.82","2:40.70","2:35.12","2:29.02","2:25.47","2:23.98"],
            "400 4 N": ["5:50.50","5:41.00","5:28.75","5:16.00","5:07.02","5:05.32"],
        },
        "U18": {
            "50 NL":   ["30.92","30.05","29.15","27.78","27.09","26.84"],
            "100 NL":  ["1:07.98","1:04.89","1:02.53","1:00.14","58.65","58.10"],
            "200 NL":  ["2:28.27","2:21.74","2:16.55","2:10.93","2:07.55","2:06.50"],
            "400 NL":  ["5:10.76","4:57.28","4:46.80","4:35.88","4:27.47","4:26.55"],
            "800 NL":  ["10:38.28","10:17.67","9:59.00","9:28.20","9:09.46","9:08.98"],
            "1500 NL": ["20:06.59","19:41.78","19:05.00","18:13.35","17:39.73","17:36.38"],
            "50 Dos":  ["36.24","34.24","33.21","31.68","30.86","30.61"],
            "100 Dos": ["1:17.56","1:14.19","1:11.47","1:08.42","1:06.53","1:06.11"],
            "200 Dos": ["2:46.42","2:39.28","2:33.99","2:28.96","2:24.78","2:23.92"],
            "50 Bra":  ["39.26","37.81","36.72","35.12","34.14","33.94"],
            "100 Bra": ["1:27.66","1:24.00","1:20.91","1:17.17","1:15.30","1:14.56"],
            "200 Bra": ["3:03.99","2:59.97","2:53.88","2:47.30","2:42.66","2:41.64"],
            "50 Pap":  ["33.15","31.89","30.90","29.36","28.58","28.36"],
            "100 Pap": ["1:16.60","1:13.27","1:10.11","1:05.70","1:04.04","1:03.48"],
            "200 Pap": ["2:50.89","2:43.72","2:37.26","2:28.29","2:23.74","2:23.28"],
            "200 4 N": ["2:48.95","2:41.82","2:35.91","2:29.02","2:25.47","2:23.98"],
            "400 4 N": ["5:52.86","5:43.38","5:30.44","5:16.00","5:07.02","5:05.32"],
        },
        "U17": {
            "50 NL":   ["31.13","30.26","29.42","28.28","27.33","26.84"],
            "100 NL":  ["1:08.44","1:05.34","1:03.13","1:01.26","59.19","58.10"],
            "200 NL":  ["2:29.27","2:22.73","2:17.83","2:13.10","2:08.60","2:06.50"],
            "400 NL":  ["5:12.85","4:59.35","4:48.74","4:37.78","4:28.39","4:26.55"],
            "800 NL":  ["10:42.56","10:21.97","9:59.00","9:29.18","9:09.94","9:08.98"],
            "1500 NL": ["20:14.68","19:50.00","19:05.00","18:20.28","17:43.08","17:36.38"],
            "50 Dos":  ["36.49","34.48","33.51","32.18","31.10","30.61"],
            "100 Dos": ["1:18.08","1:14.71","1:12.05","1:09.28","1:06.94","1:06.11"],
            "200 Dos": ["2:47.54","2:40.49","2:35.31","2:30.73","2:25.64","2:23.92"],
            "50 Bra":  ["39.53","38.08","37.01","35.53","34.33","33.94"],
            "100 Bra": ["1:28.25","1:24.59","1:21.70","1:18.70","1:16.04","1:14.56"],
            "200 Bra": ["3:05.23","3:01.22","2:55.29","2:49.39","2:43.67","2:41.64"],
            "50 Pap":  ["33.37","32.11","31.16","29.79","28.79","28.36"],
            "100 Pap": ["1:17.12","1:13.78","1:10.76","1:06.85","1:04.59","1:03.48"],
            "200 Pap": ["2:52.04","2:44.86","2:38.17","2:29.24","2:24.20","2:23.28"],
            "200 4 N": ["2:50.09","2:42.95","2:37.47","2:32.09","2:26.95","2:23.98"],
            "400 4 N": ["5:55.23","5:45.77","5:33.01","5:19.52","5:08.72","5:05.32"],
        },
        "U16": {
            "50 NL":   ["31.66","30.77","29.93","28.81","27.71","26.84"],
            "100 NL":  ["1:09.59","1:06.44","1:04.19","1:02.30","59.91","58.10"],
            "200 NL":  ["2:31.77","2:25.12","2:20.28","2:16.07","2:10.84","2:06.50"],
            "400 NL":  ["5:18.09","5:04.37","4:53.85","4:43.52","4:32.62","4:26.55"],
            "800 NL":  ["10:53.34","10:32.39","10:04.00","9:44.04","9:21.58","9:08.98"],
            "1500 NL": ["20:35.05","20:09.95","19:15.00","18:38.79","17:55.76","17:36.38"],
            "50 Dos":  ["37.10","35.05","34.07","32.70","31.45","30.61"],
            "100 Dos": ["1:19.39","1:15.96","1:13.34","1:10.77","1:08.05","1:06.11"],
            "200 Dos": ["2:50.35","2:43.18","2:37.77","2:32.68","2:26.81","2:23.92"],
            "50 Bra":  ["40.19","38.71","37.62","36.10","34.72","33.94"],
            "100 Bra": ["1:29.73","1:26.01","1:22.94","1:19.48","1:16.43","1:14.56"],
            "200 Bra": ["3:08.33","3:04.26","2:58.23","2:52.23","2:45.61","2:41.64"],
            "50 Pap":  ["33.93","32.65","31.69","30.33","29.17","28.36"],
            "100 Pap": ["1:18.41","1:15.02","1:11.95","1:07.97","1:05.36","1:03.48"],
            "200 Pap": ["2:54.93","2:47.62","2:41.47","2:34.34","2:28.41","2:23.28"],
            "200 4 N": ["2:52.94","2:45.68","2:39.97","2:34.07","2:28.15","2:23.98"],
            "400 4 N": ["6:01.19","5:51.57","5:38.69","5:25.26","5:12.75","5:05.32"],
        },
        "U15": {
            "50 NL":   ["31.76","30.85","29.98","29.27","28.01","26.84"],
            "100 NL":  ["1:09.83","1:06.63","1:04.59","1:03.25","1:00.53","58.10"],
            "200 NL":  ["2:32.29","2:25.55","2:21.08","2:17.79","2:11.86","2:06.50"],
            "400 NL":  ["5:19.18","5:05.26","4:56.06","4:49.32","4:36.87","4:26.55"],
            "800 NL":  ["10:55.56","10:34.23","10:10.00","9:51.04","9:25.59","9:08.98"],
            "1500 NL": ["21:04.42","20:38.12","20:05.00","19:49.92","18:53.26","17:36.38"],
            "50 Dos":  ["37.22","35.16","34.33","33.41","31.98","30.61"],
            "100 Dos": ["1:19.66","1:16.19","1:13.93","1:12.35","1:09.24","1:06.11"],
            "200 Dos": ["2:50.93","2:43.65","2:38.96","2:35.79","2:29.09","2:23.92"],
            "50 Bra":  ["40.33","38.83","37.93","36.94","35.35","33.94"],
            "100 Bra": ["1:30.03","1:26.26","1:23.41","1:20.54","1:17.08","1:14.56"],
            "200 Bra": ["3:08.97","3:04.80","2:59.20","2:54.23","2:46.73","2:41.64"],
            "50 Pap":  ["34.05","32.75","31.92","30.91","29.58","28.36"],
            "100 Pap": ["1:18.68","1:15.23","1:12.52","1:09.53","1:06.54","1:03.48"],
            "200 Pap": ["2:55.52","2:48.11","2:42.80","2:37.96","2:31.16","2:23.28"],
            "200 4 N": ["2:53.53","2:46.16","2:41.29","2:37.68","2:30.89","2:23.98"],
            "400 4 N": ["6:02.42","5:52.59","5:40.54","5:29.19","5:15.02","5:05.32"],
        },
        "U14": {
            "50 NL":   ["32.41","31.48","30.75","30.00","28.58","26.84"],
            "100 NL":  ["1:11.24","1:07.98","1:06.11","1:05.44","1:02.33","58.10"],
            "200 NL":  ["2:35.38","2:28.50","2:24.51","2:23.06","2:16.25","2:06.50"],
            "400 NL":  ["5:25.66","5:11.46","5:02.94","4:59.08","4:44.84","4:26.55"],
            "800 NL":  ["11:08.87","10:47.12","10:25.00","10:13.83","9:44.60","9:08.98"],
            "1500 NL": ["21:04.42","20:38.12","20:05.00","19:49.92","18:53.26","17:36.38"],
            "50 Dos":  ["37.98","35.97","35.17","34.44","32.80","30.61"],
            "100 Dos": ["1:21.28","1:18.40","1:16.49","1:14.41","1:10.17","1:06.11"],
            "200 Dos": ["2:57.35","2:52.03","2:47.03","2:40.03","2:32.41","2:23.92"],
            "50 Bra":  ["41.15","39.62","38.82","38.22","36.40","33.94"],
            "100 Bra": ["1:31.86","1:28.01","1:25.45","1:23.64","1:19.66","1:14.56"],
            "200 Bra": ["3:14.96","3:09.11","3:04.78","3:00.55","2:51.96","2:41.64"],
            "50 Pap":  ["34.74","33.41","32.67","31.99","30.47","28.36"],
            "100 Pap": ["1:20.27","1:16.76","1:14.61","1:12.36","1:08.92","1:03.48"],
            "200 Pap": ["2:59.53","2:54.14","2:50.27","2:46.72","2:38.79","2:23.28"],
            "200 4 N": ["2:57.05","2:49.54","2:44.74","2:41.83","2:34.13","2:23.98"],
            "400 4 N": ["6:09.78","5:59.76","5:49.29","5:43.70","5:27.34","5:05.32"],
        },
    },
    "M": {
        "U18+": {
            "50 NL":   ["26.35","25.98","24.77","24.44","23.62","23.62"],
            "100 NL":  ["58.50","56.46","54.56","53.25","51.45","51.45"],
            "200 NL":  ["2:11.60","2:05.50","2:00.47","1:57.39","1:53.42","1:53.42"],
            "400 NL":  ["4:42.50","4:25.51","4:18.36","4:08.94","4:00.52","4:00.52"],
            "800 NL":  ["9:40.00","9:07.90","8:55.00","8:37.19","8:19.70","8:19.70"],
            "1500 NL": ["18:21.00","18:01.00","17:35.00","16:32.77","15:59.20","15:59.20"],
            "50 Dos":  ["31.40","30.89","29.17","27.96","27.01","27.01"],
            "100 Dos": ["1:08.90","1:05.78","1:02.86","1:00.34","58.30","58.30"],
            "200 Dos": ["2:31.30","2:22.66","2:18.42","2:12.77","2:08.28","2:08.28"],
            "50 Bra":  ["33.99","33.47","31.57","30.69","29.65","29.65"],
            "100 Bra": ["1:15.90","1:13.99","1:11.26","1:07.56","1:05.27","1:05.27"],
            "200 Bra": ["2:48.90","2:43.18","2:35.07","2:29.28","2:24.24","2:24.24"],
            "50 Pap":  ["28.75","28.60","26.58","25.96","25.09","25.09"],
            "100 Pap": ["1:05.84","1:03.91","59.66","57.75","55.79","55.79"],
            "200 Pap": ["2:31.50","2:25.38","2:18.34","2:11.88","2:07.42","2:07.42"],
            "200 4 N": ["2:30.20","2:22.60","2:17.69","2:13.15","2:08.65","2:08.65"],
            "400 4 N": ["5:19.65","5:03.65","4:53.68","4:44.33","4:34.71","4:34.71"],
        },
        "U18": {
            "50 NL":   ["26.98","26.60","25.48","24.84","24.12","23.62"],
            "100 NL":  ["59.90","57.82","56.12","54.42","52.84","51.45"],
            "200 NL":  ["2:14.76","2:08.51","2:03.05","1:58.94","1:55.48","1:53.42"],
            "400 NL":  ["4:49.28","4:31.88","4:23.30","4:09.85","4:02.58","4:00.52"],
            "800 NL":  ["9:53.90","9:21.05","9:10.00","8:40.26","8:25.11","8:19.70"],
            "1500 NL": ["18:47.42","18:26.94","17:45.00","16:30.90","16:02.04","15:59.20"],
            "50 Dos":  ["32.15","31.63","30.10","28.52","27.69","27.01"],
            "100 Dos": ["1:10.55","1:07.36","1:04.30","1:01.49","59.70","58.30"],
            "200 Dos": ["2:34.93","2:26.08","2:21.39","2:14.55","2:10.64","2:08.28"],
            "50 Bra":  ["34.81","34.27","32.40","31.00","30.10","29.65"],
            "100 Bra": ["1:17.72","1:15.77","1:12.76","1:08.33","1:06.34","1:05.27"],
            "200 Bra": ["2:52.95","2:47.10","2:38.33","2:31.01","2:26.62","2:24.24"],
            "50 Pap":  ["29.44","29.29","27.46","26.31","25.55","25.09"],
            "100 Pap": ["1:07.42","1:05.44","1:01.41","58.85","57.14","55.79"],
            "200 Pap": ["2:35.14","2:28.87","2:21.23","2:13.32","2:09.44","2:07.42"],
            "200 4 N": ["2:33.80","2:26.02","2:20.51","2:14.41","2:10.50","2:08.65"],
            "400 4 N": ["5:27.32","5:10.94","4:59.80","4:47.44","4:39.07","4:34.71"],
        },
        "U17": {
            "50 NL":   ["27.35","26.97","25.91","25.48","24.62","23.62"],
            "100 NL":  ["1:00.72","58.61","56.95","55.45","53.58","51.45"],
            "200 NL":  ["2:16.60","2:10.27","2:04.91","2:01.26","1:57.16","1:53.42"],
            "400 NL":  ["4:53.24","4:35.60","4:27.26","4:14.73","4:06.12","4:00.52"],
            "800 NL":  ["10:02.05","9:28.72","9:15.00","8:48.92","8:31.04","8:19.70"],
            "1500 NL": ["19:02.84","18:42.08","17:55.00","16:47.06","16:13.01","15:59.20"],
            "50 Dos":  ["32.59","32.06","30.55","29.06","28.08","27.01"],
            "100 Dos": ["1:11.52","1:08.28","1:05.30","1:02.82","1:00.70","58.30"],
            "200 Dos": ["2:37.05","2:28.08","2:23.29","2:16.29","2:11.69","2:08.28"],
            "50 Bra":  ["35.28","34.74","32.96","31.86","30.79","29.65"],
            "100 Bra": ["1:18.78","1:16.80","1:13.85","1:09.62","1:07.27","1:05.27"],
            "200 Bra": ["2:55.32","2:49.38","2:40.35","2:32.48","2:27.33","2:24.24"],
            "50 Pap":  ["29.84","29.69","27.91","26.96","26.05","25.09"],
            "100 Pap": ["1:08.34","1:06.34","1:02.39","1:00.22","58.19","55.79"],
            "200 Pap": ["2:37.26","2:30.90","2:23.44","2:16.24","2:11.64","2:07.42"],
            "200 4 N": ["2:35.91","2:28.02","2:22.68","2:17.25","2:12.61","2:08.65"],
            "400 4 N": ["5:31.80","5:15.19","5:04.20","4:52.58","4:42.69","4:34.71"],
        },
        "U16": {
            "50 NL":   ["27.80","27.41","26.39","26.12","25.12","23.62"],
            "100 NL":  ["1:01.72","59.57","58.03","56.93","54.74","51.45"],
            "200 NL":  ["2:18.84","2:12.40","2:07.12","2:03.93","1:59.17","1:53.42"],
            "400 NL":  ["4:58.04","4:40.11","4:32.71","4:23.22","4:13.10","4:00.52"],
            "800 NL":  ["10:11.90","9:38.03","9:25.00","9:04.18","8:43.25","8:19.70"],
            "1500 NL": ["19:21.56","19:00.46","18:10.00","17:17.49","16:37.59","15:59.20"],
            "50 Dos":  ["33.13","32.59","31.15","29.97","28.82","27.01"],
            "100 Dos": ["1:12.69","1:09.40","1:06.56","1:04.64","1:02.16","58.30"],
            "200 Dos": ["2:39.62","2:30.51","2:26.14","2:20.52","2:15.12","2:08.28"],
            "50 Bra":  ["35.86","35.31","33.58","32.72","31.47","29.65"],
            "100 Bra": ["1:20.07","1:18.06","1:15.31","1:11.75","1:08.99","1:05.27"],
            "200 Bra": ["2:58.19","2:52.15","2:43.14","2:35.66","2:29.68","2:24.24"],
            "50 Pap":  ["30.33","30.17","28.47","27.78","26.72","25.09"],
            "100 Pap": ["1:09.46","1:07.43","1:03.46","1:01.83","59.46","55.79"],
            "200 Pap": ["2:39.83","2:33.38","2:26.21","2:20.16","2:14.77","2:07.42"],
            "200 4 N": ["2:38.46","2:30.44","2:25.49","2:21.36","2:15.93","2:08.65"],
            "400 4 N": ["5:37.23","5:20.35","5:07.25","4:49.63","4:48.11","4:34.71"],
        },
        "U15": {
            "50 NL":   ["28.59","28.19","27.17","27.00","25.84","23.62"],
            "100 NL":  ["1:03.48","1:01.26","59.77","58.93","56.40","51.45"],
            "200 NL":  ["2:22.79","2:16.17","2:11.09","2:08.86","2:03.32","1:53.42"],
            "400 NL":  ["5:06.51","4:48.08","4:41.51","4:30.83","4:19.17","4:00.52"],
            "800 NL":  ["10:29.30","9:54.47","9:38.00","9:20.25","8:56.13","8:19.70"],
            "1500 NL": ["19:54.59","19:32.89","18:25.00","17:53.12","17:06.91","15:59.20"],
            "50 Dos":  ["34.07","33.52","32.10","31.08","29.75","27.01"],
            "100 Dos": ["1:14.76","1:11.37","1:08.50","1:06.67","1:03.80","58.30"],
            "200 Dos": ["2:44.16","2:34.79","2:30.50","2:25.31","2:19.06","2:08.28"],
            "50 Bra":  ["36.88","36.31","34.60","33.90","32.44","29.65"],
            "100 Bra": ["1:22.35","1:20.28","1:17.76","1:15.06","1:11.83","1:05.27"],
            "200 Bra": ["3:03.26","2:57.05","2:48.63","2:43.48","2:36.44","2:24.24"],
            "50 Pap":  ["31.19","31.03","29.34","28.81","27.57","25.09"],
            "100 Pap": ["1:11.44","1:09.34","1:05.59","1:04.45","1:01.68","55.79"],
            "200 Pap": ["2:44.38","2:37.74","2:30.37","2:24.15","2:17.95","2:07.42"],
            "200 4 N": ["2:42.97","2:34.72","2:29.74","2:25.89","2:19.61","2:08.65"],
            "400 4 N": ["5:46.82","5:29.46","5:19.15","5:10.49","4:57.12","4:34.71"],
        },
        "U14": {
            "50 NL":   ["30.61","29.69","28.93","28.02","26.69","23.62"],
            "100 NL":  ["1:07.43","1:05.41","1:03.62","1:01.26","58.35","51.45"],
            "200 NL":  ["2:28.70","2:24.24","2:20.06","2:14.21","2:07.82","1:53.42"],
            "400 NL":  ["5:15.19","5:05.73","4:56.81","4:44.19","4:30.66","4:00.52"],
            "800 NL":  ["10:45.26","10:25.90","10:16.22","9:48.60","9:20.58","8:19.70"],
            "1500 NL": ["20:50.00","20:12.50","19:50.00","18:51.63","17:57.75","15:59.20"],
            "50 Dos":  ["37.08","35.87","34.64","32.56","31.01","27.01"],
            "100 Dos": ["1:20.82","1:17.73","1:14.66","1:10.88","1:07.51","58.30"],
            "200 Dos": ["2:54.40","2:46.97","2:41.06","2:34.72","2:27.36","2:08.28"],
            "50 Bra":  ["40.30","39.09","37.89","36.08","34.37","29.65"],
            "100 Bra": ["1:29.26","1:26.58","1:23.75","1:19.26","1:15.49","1:05.27"],
            "200 Bra": ["3:12.81","3:08.55","3:01.74","2:53.67","2:45.40","2:24.24"],
            "50 Pap":  ["34.40","33.37","31.83","30.12","28.69","25.09"],
            "100 Pap": ["1:18.91","1:16.54","1:13.17","1:07.77","1:04.55","55.79"],
            "200 Pap": ["2:59.09","2:51.52","2:44.48","2:34.90","2:27.53","2:07.42"],
            "200 4 N": ["2:47.85","2:42.81","2:38.67","2:33.78","2:26.46","2:08.65"],
            "400 4 N": ["6:03.22","5:52.32","5:41.48","5:25.29","5:09.80","4:34.71"],
        },
    },
}

NIVEAUX_QUALIF = [
    ("jaune",      "🟡", 'Ligue "Jaune"'),
    ("vert",       "🟢", 'Ligue "Vert"'),
    ("ligue",      "🔵", 'Ligue "Bleu"'),
    ("challenge",  "🏆", "Challenge national"),
    ("france_u18", "🥇", "France U18"),
    ("elite",      "⭐", "Élite"),
]

NIVEAU_IDX = {"jaune": 0, "vert": 1, "ligue": 2, "challenge": 3, "france_u18": 4, "elite": 5}

SEP_CHAMP = "§"
SEP_SPLIT = ";"

EPREUVE_CODES = {
    "M": {
        "50 NL": 51, "100 NL": 52, "200 NL": 53, "400 NL": 54, "800 NL": 55, "1500 NL": 56,
        "50 Dos": 61, "100 Dos": 62, "200 Dos": 63,
        "50 Bra": 71, "100 Bra": 72, "200 Bra": 73,
        "50 Pap": 81, "100 Pap": 82, "200 Pap": 83,
        "100 4 N": 90, "200 4 N": 91, "400 4 N": 92,
    },
    "F": {
        "50 NL": 1, "100 NL": 2, "200 NL": 3, "400 NL": 4, "800 NL": 5, "1500 NL": 6,
        "50 Dos": 11, "100 Dos": 12, "200 Dos": 13,
        "50 Bra": 21, "100 Bra": 22, "200 Bra": 23,
        "50 Pap": 31, "100 Pap": 32, "200 Pap": 33,
        "100 4 N": 40, "200 4 N": 41, "400 4 N": 42,
    },
}

def current_season_year() -> int:
    return datetime.now().year

GRILLE_QUALIF_FULL = {
    gender: {
        cat: {epr: GRILLES[gender][cat][epr][4] for epr in GRILLES[gender][cat]}
        for cat in GRILLES[gender] if cat in ["U14","U15","U16","U17","U18"]
    }
    for gender in ["M", "F"]
}

def grille_qualif_full(gender: str) -> dict:
    return GRILLE_QUALIF_FULL.get(gender, {})

def parse_ranking_row(html_content: str, swimmer_id: str) -> dict:
    result = {"dept": "-", "region": "-", "national": "-",
              "dept_tc": "-", "region_tc": "-", "national_tc": "-"}
    rows = find_all(r"<tr[^>]*>(.*?)</tr>", html_content)
    target_row = next((r for r in rows if swimmer_id in r), None)
    if not target_row:
        return result
    all_tippies = re.findall(r'data-tippy-content="((?:[^"\\]|\\.)*)"', target_row, re.DOTALL)
    if not all_tippies:
        all_tippies = re.findall(r"data-tippy-content='((?:[^'\\]|\\.)*)'", target_row, re.DOTALL)
    raw_tippy = next((t for t in all_tippies if "Rang" in html.unescape(t.replace("\\\\'", "'").replace("\\'", "'"))), None)
    if not raw_tippy:
        return result
    tippy = html.unescape(raw_tippy.replace("\\\\'", "'").replace("\\'", "'"))

    def extract_rank(pattern):
        m = re.search(pattern, tippy, re.DOTALL)
        if not m: return "-"
        clean = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return clean.split(" : ")[0].strip()

    result["national"]    = extract_rank(r"Rang national par cat[^→]*→\s*<b>(.*?)</b>")
    result["region"]      = extract_rank(r"Rang r[ée]gional[^→]*par cat[^→]*→\s*<b>(.*?)</b>")
    result["dept"]        = extract_rank(r"Rang d[ée]part[^→]*par cat[^→]*→\s*<b>(.*?)</b>")
    result["national_tc"] = extract_rank(r"Rang national toutes cat[^→]*→\s*<b>(.*?)</b>")
    result["region_tc"]   = extract_rank(r"Rang r[ée]gional[^→]*toutes cat[^→]*→\s*<b>(.*?)</b>")
    result["dept_tc"]     = extract_rank(r"Rang d[ée]part[^→]*toutes cat[^→]*→\s*<b>(.*?)</b>")
    return result

def parse_top10(html_content: str, swimmer_id: str) -> list:
    result = []
    rows = find_all(r"<tr[^>]*>(.*?)</tr>", html_content)
    count = 0
    for row in rows:
        tds = find_all(r"<td[^>]*>(.*?)</td>", row)
        ths = find_all(r"<th[^>]*>(.*?)</th>", row)
        if not tds or not ths: continue
        rang = strip_tags(tds[0]).rstrip(".")
        if not rang.isdigit(): continue
        nom = strip_tags(ths[0])
        try:
            nom = re.sub(r'\s*\(\d{4}\s*/\s*\d+\s*ans\)\s*[A-Z]{2,3}\s*$', '', nom)
            nom = re.sub(r'\s+', ' ', nom).strip()
        except:
            pass
        temps = strip_tags(tds[2]) if len(tds) > 2 else "-"
        is_me = swimmer_id in row
        result.append({"rang": rang, "nom": nom, "temps": temps, "moi": is_me})
        count += 1
        if count >= 10: break
    return result

def to_sec(t) -> float:
    try:
        t = str(t).replace(" ", "").strip()
        if ":" in t:
            m, s = t.split(":")
            return int(m) * 60 + float(s)
        return float(t)
    except:
        return 9999.0

def format_min_sec_short(s: float) -> str:
    m = int(s // 60); sec = int(s % 60)
    return f"{m}:{sec:02d}" if m > 0 else f"{sec}s"

def encode_splits(splits: list[Split]) -> str:
    return json.dumps([
        {"d": s.distance_m, "c": s.cumulative_time, "l": s.lap_time, "h": s.half_time or ""}
        for s in splits
    ])

def decode_splits(raw: str) -> list[SplitRow]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return [SplitRow(dist=str(i["d"]) + "m", cumul=i["c"], partiel=i["l"], half=i["h"]) for i in items]
    except Exception:
        rows = []
        for seg in raw.split(SEP_SPLIT):
            parts = seg.split(SEP_CHAMP)
            if len(parts) == 4:
                rows.append(SplitRow(dist=parts[0] + "m", cumul=parts[1], partiel=parts[2], half=parts[3]))
        return rows

def _fetch_url(url: str, retries: int = 2) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://ffn.extranat.fr/webffn/nat_rankings.php",
        "Connection": "keep-alive",
    }
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=8) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(1)
    raise last_exc

def _fetch_perf(args: tuple) -> list:
    """Fetch des performances pour un bassin donné (fonction module-level pour ThreadPoolExecutor)."""
    bc, bl, ffn_id = args
    url = f"https://ffn.extranat.fr/webffn/nat_recherche.php?idact=nat&idrch_id={ffn_id}&idopt=prf&idbas={bc}"
    html_content = _fetch_url(url)
    perfs = []
    for row in find_all(r"<tr\b[^>]*class=[^>]*border-b[^>]*>(.*?)</tr>", html_content):
        perf = parse_row(row)
        if perf:
            perfs.append({
                "E": perf.epreuve, "T": perf.temps_final, "P": perf.points,
                "D": perf.date, "B": bl, "S": encode_splits(perf.splits),
                "N": perf.competition, "V": perf.type_compet,
            })
    return perfs

def _fetch_one(args: tuple) -> tuple:
    bc, bl, epr_name, idepr, sai, cat, scope, ffn_id = args
    if cat > 18:
        base = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}"
    else:
        base = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}&idcat={cat}"
    suffix = {"dept": "&iddep=1611", "region": "&idreg=3004", "national": ""}[scope]
    try:
        h = _fetch_url(base + suffix)
        rank = parse_ranking_row(h, ffn_id) if scope == "dept" else None
        top  = parse_top10(h, ffn_id)
        return (bl, epr_name, scope, rank, top)
    except:
        fallback_rank = {"dept": "-", "region": "-", "national": "-"} if scope == "dept" else None
        return (bl, epr_name, scope, fallback_rank, [])
    bc, bl, epr_name, idepr, sai, cat, scope, ffn_id = args
    if cat > 18:
        base = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}"
    else:
        base = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}&idcat={cat}"
    suffix = {"dept": "&iddep=1611", "region": "&idreg=3004", "national": ""}[scope]
    try:
        h = _fetch_url(base + suffix)
        rank = parse_ranking_row(h, ffn_id) if scope == "dept" else None
        top  = parse_top10(h, ffn_id)
        return (bl, epr_name, scope, rank, top)
    except:
        fallback_rank = {"dept": "-", "region": "-", "national": "-"} if scope == "dept" else None
        return (bl, epr_name, scope, fallback_rank, [])

# ── 5. STATE ──────────────────────────────────────────────────────────────────

class State(rx.State):
    # Navigation : "" = accueil, "tristan" = page nageur, "tristan|100 Bra" = page nage
    active_swimmer_key: str = ""
    loading_init: bool = True
    current_bassin: str = "50m"
    selected_nage_state: str = ""
    # Données par nageur — clé = swimmer_key
    all_results_json:   str = rx.LocalStorage("{}", name="multi_results_v1")
    all_rankings_json:  str = rx.LocalStorage("{}", name="multi_ranks_v1")
    all_top10_json:     str = rx.LocalStorage("{}", name="multi_top10_v1")
    all_last_update:    str = rx.LocalStorage("{}", name="multi_upd_v1")
    loading: bool = False
    # Dialogs
    top10_dialog_open:  bool = False
    top10_dialog_title: str = ""
    top10_dialog_key:   str = ""
    top10_loading:      bool = False
    dialog_open:        bool = False
    dialog_key:         str = ""
    dialog_lieu:        str = ""
    dialog_type:        str = ""
    dialog_date:        str = ""
    dialog_splits_data: list[SplitRow] = []

    def on_load(self):
        """Lit les paramètres ?nageur= et &nage= dans l'URL au chargement."""
        url = self.router.url
        key = ""
        nage = ""
        if "nageur=" in url:
            try:
                key = url.split("nageur=")[1].split("&")[0].strip()
            except:
                key = ""
        if "nage=" in url:
            try:
                nage = url.split("nage=")[1].split("&")[0].replace("+", " ").strip()
            except:
                nage = ""
        if key and key in SWIMMERS:
            self.active_swimmer_key = key
            self.selected_nage_state = nage if nage else ""
        else:
            self.active_swimmer_key = ""
            self.selected_nage_state = ""
        self.loading_init = False
        return rx.call_script("document.title = 'PdC Swim'")

    def on_load_route(self):
        """Lit la clé nageur depuis le path /nageur/[key]."""
        url = self.router.url
        parts = [p for p in url.split("?")[0].split("/") if p]
        key = parts[-1] if parts else ""
        if key and key in SWIMMERS:
            self.active_swimmer_key = key
            self.selected_nage_state = ""
        else:
            self.active_swimmer_key = ""
            self.selected_nage_state = ""
        self.loading_init = False
        # Injecter le manifest spécifique au nageur + titre
        name = SWIMMERS.get(key, {}).get("name", "")
        return rx.call_script(
            f"document.title = '{name} Swim';"
            f"var l=document.querySelector('link[rel=manifest]');"
            f"if(l){{l.href='/{key}-manifest.json';}}"
            f"else{{var n=document.createElement('link');n.rel='manifest';n.href='/{key}-manifest.json';document.head.appendChild(n);}}"
        )

    # ── Propriétés du nageur actif ────────────────────────────────────────────

    @rx.var(cache=True)
    def swimmer(self) -> dict:
        if self.active_swimmer_key not in SWIMMERS:
            return {"name": "", "ffn_id": "", "gender": "M", "birth_year": 2000, "photo": ""}
        return SWIMMERS[self.active_swimmer_key]

    @rx.var(cache=True)
    def swimmer_name(self) -> str:
        return self.swimmer.get("name", "")

    @rx.var(cache=True)
    def swimmer_ffn_id(self) -> str:
        return self.swimmer.get("ffn_id", "")

    @rx.var(cache=True)
    def swimmer_gender(self) -> str:
        return self.swimmer.get("gender", "M")

    @rx.var(cache=True)
    def swimmer_birth_year(self) -> int:
        return self.swimmer.get("birth_year", 2000)

    @rx.var(cache=True)
    def swimmer_photo(self) -> str:
        return self.swimmer.get("photo", "")

    # ── Données actives ───────────────────────────────────────────────────────

    @rx.var(cache=True)
    def active_results(self) -> list:
        try:
            return json.loads(self.all_results_json).get(self.active_swimmer_key, [])
        except:
            return []

    @rx.var(cache=True)
    def active_rankings(self) -> dict:
        try:
            return json.loads(self.all_rankings_json).get(self.active_swimmer_key, {})
        except:
            return {}

    @rx.var(cache=True)
    def active_top10(self) -> dict:
        try:
            return json.loads(self.all_top10_json).get(self.active_swimmer_key, {})
        except:
            return {}

    # Conservées pour compatibilité avec le reste du code
    @rx.var(cache=True)
    def results_json(self) -> str:
        return json.dumps(self.active_results)

    @rx.var(cache=True)
    def rankings_json(self) -> str:
        return json.dumps(self.active_rankings)

    @rx.var(cache=True)
    def top10_json(self) -> str:
        return json.dumps(self.active_top10)

    @rx.var(cache=True)
    def last_up_display(self) -> str:
        try:
            d = json.loads(self.all_last_update)
            val = float(d.get(self.active_swimmer_key, 0))
            if val <= 0: return ""
            from datetime import timezone
            dt = datetime.fromtimestamp(val, tz=timezone.utc).astimezone()
            return f"MAJ : {dt.strftime('%d/%m/%Y %H:%M')}"
        except:
            return ""

    # ── Navigation ────────────────────────────────────────────────────────────

    def select_swimmer(self, key: str):
        self.active_swimmer_key = key
        self.selected_nage_state = ""
        self.current_bassin = "50m"
        return rx.call_script(f"window.history.replaceState(null, '', '?nageur={key}')")

    def nav_to_accueil(self):
        self.active_swimmer_key = ""
        self.selected_nage_state = ""
        return rx.call_script("window.history.replaceState(null, '', '/')")

    def change_bassin(self, v: Union[str, list[str]]):
        self.current_bassin = v[0] if isinstance(v, list) else v
        return rx.call_script("window.scrollTo({top: 0, behavior: 'instant'})")

    def nav_to_nage(self, n: str):
        self.selected_nage_state = n
        yield
        # Charger les classements si pas en cache
        nage = n.rstrip(".")
        swimmer_key = self.active_swimmer_key
        bl = self.current_bassin
        if self.active_rankings.get(f"{nage}|{bl}"):
            return  # déjà en cache
        ffn_id     = self.swimmer_ffn_id
        birth_year = self.swimmer_birth_year
        gender     = self.swimmer_gender
        sai        = current_season_year()
        cat        = sai - birth_year
        idepr = EPREUVE_CODES.get(gender, EPREUVE_CODES["M"]).get(nage)
        if not idepr: return
        for bc, bll in [("25", "25m"), ("50", "50m")]:
            try:
                _, epr_name, _, rank, top = _fetch_one((bc, bll, nage, idepr, sai, cat, "dept", ffn_id))
                all_rankings = json.loads(self.all_rankings_json) if self.all_rankings_json not in ("{}", "") else {}
                nr = all_rankings.get(swimmer_key, {})
                nr[f"{epr_name}|{bll}"] = rank
                all_rankings[swimmer_key] = nr
                self.all_rankings_json = json.dumps(all_rankings)
                all_top10 = json.loads(self.all_top10_json) if self.all_top10_json not in ("{}", "") else {}
                nt = all_top10.get(swimmer_key, {})
                nt[f"{epr_name}|{bll}|dept"] = top
                all_top10[swimmer_key] = nt
                self.all_top10_json = json.dumps(all_top10)
                yield
            except Exception as e:
                print(f"[nav_to_nage] ERREUR {nage}|{bll}: {e}")

    def nav_back_to_nageur(self):
        self.selected_nage_state = "" 

    # ── Catégorie ─────────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def current_category(self) -> str:
        return f"U{current_season_year() - self.swimmer_birth_year}"

    @rx.var(cache=True)
    def is_senior(self) -> bool:
        return (current_season_year() - self.swimmer_birth_year) > 18


    # ── Qualifications ────────────────────────────────────────────────────────

    _QUALIF_KEY_MAP = {
        "NL": "NL", "LIBRE": "NL",
        "BRA": "Bra", "DOS": "Dos", "PAP": "Pap", "4 N": "4 N",
    }

    def get_qualif_key(self, nage_full: str) -> str:
        n = nage_full.upper()
        dist = re.search(r'\d+', n)
        dist_str = dist.group() if dist else ""
        type_n = next((v for k, v in self._QUALIF_KEY_MAP.items() if k in n), "")
        return f"{dist_str} {type_n}".strip()

    @rx.var(cache=True)
    def qualif_time_val(self) -> str:
        if self.current_bassin != "50m": return ""
        gqf = grille_qualif_full(self.swimmer_gender)
        return gqf.get(self.current_category, {}).get(self.get_qualif_key(self.selected_nage), "")

    @rx.var(cache=True)
    def qualif_rows(self) -> list[QualifRow]:
        if self.current_bassin != "50m" or not self.selected_nage: return []
        age = current_season_year() - self.swimmer_birth_year
        if age < 14: return []
        cat = self.current_category
        cat_key = cat if cat in ["U14","U15","U16","U17","U18"] else "U18+"
        key = self.get_qualif_key(self.selected_nage)
        best = self.best_time_val
        rows = []
        for niveau, picto, label in NIVEAUX_QUALIF:
            if niveau == "france_u18" and age > 18:
                continue
            idx = NIVEAU_IDX[niveau]
            vals = GRILLES.get(self.swimmer_gender, {}).get(cat_key, {}).get(key, [])
            t_str = vals[idx] if len(vals) > idx else ""
            if not t_str:
                rows.append(QualifRow(picto=picto, label=label, temps="-", ecart="-", qualif=False))
                continue
            try:
                secs = to_sec(t_str)
                m = int(secs // 60); s = secs - m * 60
                temps_fmt = f"{m:02d}:{s:05.2f}"
            except:
                temps_fmt = t_str
            if best:
                try:
                    diff = to_sec(best) - secs
                    qualif = diff <= 0
                    ecart = f"-{abs(diff):.2f}s" if qualif else f"+{diff:.2f}s"
                except:
                    qualif, ecart = False, "-"
            else:
                qualif, ecart = False, "-"
            rows.append(QualifRow(picto=picto, label=label, temps=temps_fmt, ecart=ecart, qualif=qualif))
        return rows

    # ── Résultats ─────────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def current_results_list(self) -> list[Result]:
        try: return [Result(**r) for r in json.loads(self.results_json)]
        except: return []

    @rx.var(cache=True)
    def available_nages(self) -> list[str]:
        return sorted(
            list({r.E for r in self.current_results_list if r.B == self.current_bassin}),
            key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0,
        )

    @rx.var(cache=True)
    def nages_nl(self) -> list[str]:
        return [n for n in self.available_nages if "NL" in n.upper() or "LIBRE" in n.upper()]

    @rx.var(cache=True)
    def nages_bra(self) -> list[str]:
        return [n for n in self.available_nages if "BRA" in n.upper()]

    @rx.var(cache=True)
    def nages_pap(self) -> list[str]:
        return [n for n in self.available_nages if "PAP" in n.upper()]

    @rx.var(cache=True)
    def nages_dos(self) -> list[str]:
        return [n for n in self.available_nages if "DOS" in n.upper()]

    @rx.var(cache=True)
    def nages_4n(self) -> list[str]:
        return [n for n in self.available_nages if "4 N" in n.upper()]

    @rx.var(cache=True)
    def selected_nage(self) -> str:
        return self.selected_nage_state

    @rx.var(cache=True)
    def filtered_data(self) -> list[Result]:
        if not self.selected_nage: return []
        d = [r for r in self.current_results_list if r.E == self.selected_nage and r.B == self.current_bassin]
        return sorted(d, key=lambda x: datetime.strptime(x.D, "%d/%m/%Y"), reverse=True)

    @rx.var(cache=True)
    def best_time_val(self) -> str:
        if not self.filtered_data: return ""
        try: return min(self.filtered_data, key=lambda x: to_sec(x.T)).T
        except: return ""

    @rx.var(cache=True)
    def chart_data(self) -> list[dict]:
        """Données pour Recharts : liste de {date, secs, label, qualif}."""
        d = sorted(self.filtered_data, key=lambda x: datetime.strptime(x.D, "%d/%m/%Y"))
        if not d: return []
        q_val = self.qualif_time_val
        q_secs = to_sec(q_val) if q_val else None
        result = []
        for x in d:
            s = to_sec(x.T)
            d_iso = datetime.strptime(x.D, "%d/%m/%Y").strftime("%Y-%m-%d")
            result.append({
                "date": x.D,
                "month": x.D[3:],
                "iso": d_iso,
                "secs": round(s, 2),
                "label": x.T,
                "lieu": x.N,
                "type": x.V,
            })
        return result

    @rx.var(cache=True)
    def chart_config(self) -> dict:
        """Calcul atomique de step/min/max/ticks pour le graphe."""
        d = self.chart_data
        if not d: return {"step": 2, "min": 0, "max": 10, "ticks": []}
        mn_raw = min(r["secs"] for r in d)
        mx_raw = max(r["secs"] for r in d)
        amp = mx_raw - mn_raw if mx_raw > mn_raw else 1
        step = 1
        for s in [1, 2, 5, 10, 15, 20, 30, 60]:
            if amp / s <= 7:
                step = s
                break
        y_min = max(0, (int(mn_raw) // step) * step)
        y_max = (int(mx_raw) // step + 1) * step
        ticks = list(range(y_min, y_max + step, step))
        return {"step": step, "min": y_min, "max": y_max, "ticks": ticks}

    @rx.var(cache=True)
    def chart_step(self) -> int:
        return self.chart_config.get("step", 2)

    @rx.var(cache=True)
    def chart_y_min(self) -> int:
        return self.chart_config.get("min", 0)

    @rx.var(cache=True)
    def chart_y_max(self) -> int:
        return self.chart_config.get("max", 100)

    @rx.var(cache=True)
    def chart_ticks(self) -> list[dict]:
        ticks = self.chart_config.get("ticks", [])
        result = []
        for v in ticks:
            m = int(v // 60); s = v % 60
            label = f"{m:02d}:{s:02d}"
            result.append({"value": v, "label": label})
        return result

    @rx.var(cache=True)
    def chart_tick_values(self) -> list[int]:
        return [int(t["value"]) for t in self.chart_ticks]

    @rx.var(cache=True)
    def chart_tick_labels(self) -> list[str]:
        return [t["label"] for t in self.chart_ticks]

    @rx.var(cache=True)
    def chart_json(self) -> str:
        cfg = self.chart_config
        return json.dumps({
            "data": self.chart_data,
            "min": cfg.get("min", 0),
            "max": cfg.get("max", 100),
            "ticks": cfg.get("ticks", []),
        })

    def render_chart(self):
        payload = self.chart_json
        return rx.call_script(
            f"""(function(){{
  function draw(){{
  var el=document.getElementById('swc');
  if(!el||!window.Chart){{setTimeout(draw,100);return;}}
  if(el._ch){{el._ch.destroy();}}
  var p={payload};
  console.log('chart min/max/ticks:', p.min, p.max, p.ticks);
  var d=p.data; var mn=p.min; var mx=p.max; var tk=p.ticks;
  var fmt=function(v){{
    var m=String(Math.floor(v/60)).padStart(2,'0');
    var s=String(Math.round(v%60)).padStart(2,'0');
    return m+':'+s;
  }};
  el._ch=new Chart(el,{{type:'line',
    data:{{datasets:[{{data:d.map(function(x){{return{{x:x.iso,y:x.secs,label:x.label,lieu:x.lieu,date:x.date,type:x.type}};}})
    ,borderColor:'#3b82f6',borderWidth:2,pointBackgroundColor:'#3b82f6',pointRadius:3,tension:0,pointHoverRadius:5}}]}},
    options:{{plugins:{{legend:{{display:false}},tooltip:{{
      callbacks:{{
        title:function(items){{var r=items[0].raw;return r.lieu+' ('+r.date+')';}},
        afterTitle:function(items){{return items[0].raw.type;}},
        label:function(c){{return 'Temps : '+c.raw.label;}}
      }},
      displayColors:false,
      titleFont:{{size:11}},
      bodyFont:{{size:11}}
    }}}},
    scales:{{y:{{min:mn,max:mx,
      ticks:{{values:tk,callback:fmt,font:{{size:9}},autoSkip:false,maxTicksLimit:20}},
      afterBuildTicks:function(axis){{axis.ticks=tk.map(function(v){{return{{value:v}};}});}},
      grid:{{color:'#e5e7eb'}}}},
    x:{{type:'time',time:{{unit:'month',displayFormats:{{month:'MM/yyyy'}}}},ticks:{{font:{{size:9}}}},grid:{{display:false}}}}}}}}
  }});
  }} draw();
}})();"""
        )

    # ── Classements ───────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def current_rankings(self) -> dict:
        try: return json.loads(self.rankings_json)
        except: return {}

    @rx.var(cache=True)
    def selected_nage_rankings(self) -> dict:
        nage = self.selected_nage.rstrip(".")
        key = f"{nage}|{self.current_bassin}"
        return self.current_rankings.get(key, {"dept": "—", "region": "—", "national": "—"})

    @rx.var(cache=True)
    def ranking_national_txt(self) -> str:
        return self.selected_nage_rankings.get("national", "-")

    @rx.var(cache=True)
    def ranking_region_txt(self) -> str:
        return self.selected_nage_rankings.get("region", "-")

    @rx.var(cache=True)
    def ranking_dept_txt(self) -> str:
        return self.selected_nage_rankings.get("dept", "-")

    @rx.var(cache=True)
    def ranking_national_tc_txt(self) -> str:
        return self.selected_nage_rankings.get("national_tc", "-")

    @rx.var(cache=True)
    def ranking_region_tc_txt(self) -> str:
        return self.selected_nage_rankings.get("region_tc", "-")

    @rx.var(cache=True)
    def ranking_dept_tc_txt(self) -> str:
        return self.selected_nage_rankings.get("dept_tc", "-")

    @rx.var(cache=True)
    def ranking_title(self) -> str:
        return f"Classement {current_season_year()}"

    # ── Refresh ───────────────────────────────────────────────────────────────

    def force_refresh(self):
        if self.loading: return
        if self.active_swimmer_key not in SWIMMERS: return
        self.loading = True
        yield
        ffn_id     = self.swimmer_ffn_id
        birth_year = self.swimmer_birth_year
        sai        = current_season_year()
        cat        = sai - birth_year
        key        = self.active_swimmer_key

        try:
            all_results  = json.loads(self.all_results_json)  if self.all_results_json  not in ("{}", "") else {}
            all_upd      = json.loads(self.all_last_update)   if self.all_last_update   not in ("{}", "") else {}

            # ── Performances 25m + 50m en parallèle ───────────────────
            new_res = []
            with ThreadPoolExecutor(max_workers=2) as ex:
                futures_perf = [ex.submit(_fetch_perf, (bc, bl, ffn_id)) for bc, bl in [("25", "25m"), ("50", "50m")]]
                for f in futures_perf:
                    try:
                        new_res.extend(f.result(timeout=20))
                    except Exception as e:
                        print(f"[force_refresh] fetch_perf ERREUR: {e}")

            all_results[key] = new_res
            all_upd[key]     = time.time()
            self.all_results_json  = json.dumps(all_results)
            self.all_last_update   = json.dumps(all_upd)
            # Effacer les classements pour forcer un rechargement à la demande
            all_rankings = json.loads(self.all_rankings_json) if self.all_rankings_json not in ("{}", "") else {}
            all_rankings[key] = {}
            self.all_rankings_json = json.dumps(all_rankings)

        except Exception as e:
            print(f"[force_refresh] ERREUR: {type(e).__name__}: {e}")
        finally:
            self.loading = False
            yield

    # ── Top 10 ────────────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def top10_dialog_data(self) -> list[Top10Entry]:
        try:
            d = json.loads(self.top10_json)
            entries = d.get(self.top10_dialog_key, [])
            return [Top10Entry(**e) for e in entries]
        except:
            return []

    def open_top10(self, scope: str):
        nage = self.selected_nage.rstrip(".")
        self.top10_dialog_key = f"{nage}|{self.current_bassin}|{scope}"
        tc = scope.endswith("_tc")
        base_scope = scope.replace("_tc", "")
        labels = {"national": "France", "region": "AURA", "dept": "Isère"}
        cat = current_season_year() - self.swimmer_birth_year
        suffix = " TC" if tc else f" U{cat}"
        self.top10_dialog_title = f"Top 10 {labels[base_scope]}{suffix} — {nage} ({self.current_bassin})"
        self.top10_dialog_open = True
        all_top10 = json.loads(self.top10_json) if self.top10_json not in ("{}", "") else {}
        if f"{nage}|{self.current_bassin}|{scope}" in all_top10:
            return
        self.top10_loading = True
        yield
        idepr = EPREUVE_CODES.get(self.swimmer_gender, EPREUVE_CODES["M"]).get(nage, None)
        if idepr is None:
            self.top10_loading = False
            return
        sai    = current_season_year()
        cat_val = sai - self.swimmer_birth_year
        bc = "50" if self.current_bassin == "50m" else "25"
        bl = self.current_bassin
        ffn_id = self.swimmer_ffn_id
        if tc or cat_val > 18:
            base_url = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}"
            suffix_map = {"national": "", "national_tc": "", "region": "&idreg=3004", "region_tc": "&idreg=3004", "dept": "&iddep=1611", "dept_tc": "&iddep=1611"}
            url = base_url + suffix_map.get(scope, "")
        else:
            base_url = f"https://ffn.extranat.fr/webffn/nat_rankings.php?idact=nat&idopt=sai&go=epr&idbas={bc}&idepr={idepr}&idsai={sai}&idcat={cat_val}"
            suffix_map = {"national": "", "region": "&idreg=3004", "dept": "&iddep=1611"}
            url = base_url + suffix_map.get(scope, "")
        try:
            h = _fetch_url(url)
            top = parse_top10(h, ffn_id)
        except:
            top = []

        all_top10_store = json.loads(self.all_top10_json) if self.all_top10_json not in ("{}", "") else {}
        nageur_top10 = all_top10_store.get(self.active_swimmer_key, {})
        nageur_top10[f"{nage}|{bl}|{scope}"] = top
        all_top10_store[self.active_swimmer_key] = nageur_top10
        self.all_top10_json = json.dumps(all_top10_store)
        self.top10_loading = False

    def close_top10(self):
        self.top10_dialog_open = False

    # ── Splits dialog ─────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def dialog_splits(self) -> list[SplitRow]:
        return self.dialog_splits_data

    def open_dialog(self, key: str, lieu: str, type_compet: str, date: str):
        self.dialog_key  = key
        self.dialog_lieu = lieu
        self.dialog_type = type_compet
        self.dialog_date = date
        rows: list[SplitRow] = []
        for r in self.filtered_data:
            if r.D + r.T == key and r.S:
                rows = decode_splits(r.S)
                break
        self.dialog_splits_data = rows
        self.dialog_open = True

    def close_dialog(self):
        self.dialog_open = False

# ── 6. COMPOSANTS UI ─────────────────────────────────────────────────────────

def qualif_row_ui(r: QualifRow) -> rx.Component:
    return rx.hstack(
        rx.text(r.picto, font_size="0.9em", width="22px"),
        rx.text(r.label, font_size="0.75em", color=rx.color("gray", 11), flex_grow="1"),
        rx.text(r.temps, font_size="0.75em", font_weight="bold", color=rx.color("gray", 12), width="64px", text_align="right"),
        rx.text(r.ecart, font_size="0.72em", font_weight="bold",
            color=rx.cond(r.qualif, rx.color("green", 9), rx.color("red", 9)),
            width="60px", text_align="right",
        ),
        spacing="2", align="center", width="100%",
    )

def top10_row_ui(entry: Top10Entry) -> rx.Component:
    return rx.hstack(
        rx.text(entry.rang + ".",
            font_size="0.75em", color=rx.color("gray", 10), width="26px", text_align="right",
            font_weight=rx.cond(entry.moi, "bold", "normal"),
        ),
        rx.text(entry.nom,
            font_size="0.75em", flex_grow="1",
            color=rx.cond(entry.moi, rx.color("blue", 9), rx.color("gray", 12)),
            font_weight=rx.cond(entry.moi, "bold", "normal"),
        ),
        rx.text(entry.temps,
            font_size="0.75em", font_weight="bold",
            color=rx.cond(entry.moi, rx.color("blue", 9), rx.color("gray", 12)),
        ),
        spacing="2", align="center", width="100%",
        background_color=rx.cond(entry.moi, rx.color("blue", 2), "transparent"),
        border_radius="4px", padding_x="4px",
    )

def top10_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.text(State.top10_dialog_title, font_weight="bold", font_size="0.85em", color=rx.color("gray", 12)),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button(rx.icon(tag="x", size=16), variant="ghost", size="1", on_click=State.close_top10),
                    ),
                    width="100%", align="center",
                ),
                rx.divider(),
                rx.cond(
                    State.top10_loading,
                    rx.center(rx.spinner(size="3"), padding="20px"),
                    rx.cond(
                        State.top10_dialog_data.length() > 0,
                        rx.vstack(rx.foreach(State.top10_dialog_data, top10_row_ui), spacing="1", width="100%"),
                        rx.text("Aucune donnée", font_size="0.8em", color=rx.color("gray", 10)),
                    ),
                ),
                spacing="3", width="100%",
            ),
            background_color=rx.color("gray", 1),
            border="1px solid var(--gray-4)",
            border_radius="16px",
            padding="16px",
            max_width="420px",
            width="92vw",
        ),
        open=State.top10_dialog_open,
        on_open_change=State.close_top10,
    )

def split_row_ui(s: SplitRow) -> rx.Component:
    return rx.hstack(
        rx.text(s.dist + " :", font_size="0.75em", color=rx.color("gray", 10), width="52px", text_align="right"),
        rx.text(s.cumul,       font_size="0.75em", font_weight="bold", color=rx.color("gray", 12), width="64px"),
        rx.cond(
            s.partiel != "",
            rx.text("(" + s.partiel + ")", font_size="0.75em", color=rx.color("blue", 9), width="62px"),
            rx.box(width="62px"),
        ),
        rx.cond(
            s.half != "",
            rx.text("[" + s.half + "]", font_size="0.72em", color=rx.color("green", 9)),
            rx.box(),
        ),
        spacing="2", align="center",
    )

def splits_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text(State.dialog_lieu, font_weight="bold", font_size="0.9em", color=rx.color("gray", 12)),
                        rx.text(State.dialog_date + "  " + State.dialog_type, font_size="0.72em", color=rx.color("gray", 10)),
                        spacing="0", align_items="start",
                    ),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button(rx.icon(tag="x", size=16), variant="ghost", size="1", on_click=State.close_dialog),
                    ),
                    width="100%", align="start",
                ),
                rx.divider(),
                rx.cond(
                    State.dialog_splits.length() > 0,
                    rx.vstack(
                        rx.foreach(State.dialog_splits, split_row_ui),
                        spacing="1", align_items="start", width="100%", overflow_y="auto", max_height="55vh",
                    ),
                    rx.text("Aucun temps de passage", font_size="0.8em", color=rx.color("gray", 10)),
                ),
                spacing="3", width="100%",
            ),
            background_color=rx.color("gray", 1),
            border="1px solid var(--gray-4)",
            border_radius="16px",
            padding="16px",
            max_width="360px",
            width="92vw",
        ),
        open=State.dialog_open,
        on_open_change=State.close_dialog,
    )

def swimmer_card(key: str, sw: dict) -> rx.Component:
    """Carte nageur compacte — photo 60px."""
    photo = sw.get("photo", "")
    age = current_season_year() - sw["birth_year"]
    cat = "TC" if age > 18 else f"U{age}"
    return rx.box(
        rx.hstack(
            rx.cond(
                photo != "",
                rx.image(src=f"/{photo}", width="52px", height="52px", border_radius="50%", object_fit="cover"),
                rx.box(
                    rx.text(sw["name"][0], font_size="1.2em", font_weight="bold", color=rx.color("blue", 9)),
                    width="52px", height="52px", border_radius="50%",
                    background_color=rx.color("blue", 3),
                    display="flex", align_items="center", justify_content="center",
                    flex_shrink="0",
                ),
            ),
            rx.vstack(
                rx.text(sw["name"], font_weight="bold", font_size="0.9em", color=rx.color("gray", 12)),
                rx.text(cat, font_size="0.75em", color=rx.color("gray", 10)),
                spacing="0", align_items="start",
            ),
            spacing="3", align="center",
        ),
        padding="10px 14px",
        border_radius="10px",
        border="1px solid var(--gray-4)",
        background_color=rx.color("gray", 2),
        cursor="pointer",
        _hover={"background_color": rx.color("blue", 2), "border_color": rx.color("blue", 6)},
        on_click=State.select_swimmer(key),
        width="100%",
    )


def header_accueil() -> rx.Component:
    return rx.hstack(
        rx.image(src="/icon.jpg", width="40px", height="40px", border_radius="8px", object_fit="cover"),
        rx.text("Pont de Claix Natation", font_weight="bold", font_size="0.95em", color=rx.color("gray", 12)),
        rx.spacer(),
        rx.color_mode.button(variant="ghost"),
        width="100%", align="center", padding_x="1em", padding_y="0.6em",
        border_bottom="1px solid var(--gray-4)",
        background_color=rx.color("gray", 1),
    )

def header_nageur() -> rx.Component:
    return rx.hstack(
        rx.image(
            src="/icon.jpg", width="40px", height="40px", border_radius="8px", object_fit="cover",
            cursor="pointer", on_click=State.nav_to_accueil,
        ),
        rx.spacer(),
        rx.hstack(
            rx.cond(
                State.swimmer_photo != "",
                rx.image(src="/" + State.swimmer_photo, width="36px", height="36px", border_radius="50%", object_fit="cover"),
                rx.box(
                    rx.text(State.swimmer_name[0], font_size="1.1em", font_weight="bold", color=rx.color("blue", 9)),
                    width="36px", height="36px", border_radius="50%",
                    background_color=rx.color("blue", 3),
                    display="flex", align_items="center", justify_content="center",
                ),
            ),
            rx.text(State.swimmer_name, font_weight="bold", font_size="0.9em", color=rx.color("gray", 12)),
            spacing="2", align="center",
            cursor="pointer", on_click=State.nav_back_to_nageur,
        ),
        rx.spacer(),
        rx.hstack(
            rx.color_mode.button(variant="ghost"),
            rx.button(rx.icon(tag="refresh-cw"), on_click=State.force_refresh, variant="ghost", loading=State.loading),
            spacing="1",
        ),
        width="100%", align="center", padding_x="1em", padding_y="0.6em",
        border_bottom="1px solid var(--gray-4)",
        background_color=rx.color("gray", 1),
        position="sticky", top="0", z_index="10",
    )

def header_nage() -> rx.Component:
    return header_nageur()

def index():
    l_style = dict(font_size="0.75em", font_weight="bold", color=rx.color("gray", 11), margin_bottom="4px", margin_left="4px")
    return rx.theme(
        rx.center(
        splits_dialog(),
        top10_dialog(),
        rx.cond(
            State.loading_init,
            rx.center(rx.spinner(size="3"), min_height="100vh"),
            rx.cond(
            State.active_swimmer_key == "",
            # ── PAGE ACCUEIL : grille nageurs ────────────────────────
            rx.vstack(
                header_accueil(),
                rx.vstack(
                    rx.text("Garçons", font_size="0.8em", font_weight="bold", color=rx.color("gray", 10), padding_x="1em"),
                    rx.vstack(
                        *[swimmer_card(k, v) for k, v in sorted(
                            ((k, v) for k, v in SWIMMERS.items() if v["gender"] == "M"),
                            key=lambda x: x[1]["birth_year"], reverse=True
                        )],
                        spacing="2", width="100%", padding_x="1em",
                    ),
                    rx.text("Filles", font_size="0.8em", font_weight="bold", color=rx.color("gray", 10), padding_x="1em", padding_top="0.5em"),
                    rx.vstack(
                        *[swimmer_card(k, v) for k, v in sorted(
                            ((k, v) for k, v in SWIMMERS.items() if v["gender"] == "F"),
                            key=lambda x: x[1]["birth_year"], reverse=True
                        )],
                        spacing="2", width="100%", padding_x="1em",
                    ),
                    spacing="2", width="100%", padding_y="1em",
                ),
                width=["100%", "420px"], spacing="0",
            ),
            rx.cond(
                State.selected_nage == "",
                # ── PAGE NAGEUR : liste des nages ────────────────────
                rx.vstack(
                    header_nageur(),
                    rx.vstack(
                        rx.vstack(
                            rx.text("Bassin", style=l_style),
                            rx.segmented_control.root(
                                rx.segmented_control.item("25m", value="25m"),
                                rx.segmented_control.item("50m", value="50m"),
                                on_change=State.change_bassin, value=State.current_bassin, width="100%",
                            ),
                            width="100%", align_items="start", spacing="0",
                        ),
                        rx.vstack(
                            rx.text("Nage", style=l_style),
                            rx.cond(
                                State.available_nages.length() > 0,
                                rx.vstack(
                                    rx.grid(rx.foreach(State.nages_nl,  lambda n: rx.button(n, on_click=lambda: State.nav_to_nage(n), variant="soft", width="100%")), columns="2", spacing="2", width="100%"),
                                    rx.divider(),
                                    rx.grid(rx.foreach(State.nages_bra, lambda n: rx.button(n, on_click=lambda: State.nav_to_nage(n), variant="soft", width="100%")), columns="2", spacing="2", width="100%"),
                                    rx.divider(),
                                    rx.grid(rx.foreach(State.nages_pap, lambda n: rx.button(n, on_click=lambda: State.nav_to_nage(n), variant="soft", width="100%")), columns="2", spacing="2", width="100%"),
                                    rx.divider(),
                                    rx.grid(rx.foreach(State.nages_dos, lambda n: rx.button(n, on_click=lambda: State.nav_to_nage(n), variant="soft", width="100%")), columns="2", spacing="2", width="100%"),
                                    rx.divider(),
                                    rx.grid(rx.foreach(State.nages_4n,  lambda n: rx.button(n, on_click=lambda: State.nav_to_nage(n), variant="soft", width="100%")), columns="2", spacing="2", width="100%"),
                                    spacing="2", width="100%",
                                ),
                                rx.center(
                                    rx.vstack(
                                        rx.text("Pas encore de données", font_size="0.9em", color=rx.color("gray", 10), font_weight="bold"),
                                        rx.hstack(
                                            rx.text("Appuyez sur", font_size="0.8em", color=rx.color("gray", 9)),
                                            rx.icon(tag="refresh-cw", size=14, color=rx.color("gray", 9)),
                                            rx.text("pour charger", font_size="0.8em", color=rx.color("gray", 9)),
                                            spacing="1", align="center",
                                        ),
                                        spacing="2", align="center",
                                    ),
                                    min_height="200px", width="100%",
                                ),
                            ),
                            width="100%", align_items="start", spacing="1",
                        ),
                        rx.text(State.last_up_display, font_size="0.7em", color=rx.color("gray", 10)),
                        spacing="4", padding="1em", width="100%",
                    ),
                    width=["100%", "420px"], spacing="0",
                ),
                # ── PAGE NAGE : détail ───────────────────────────────
                rx.vstack(
                    header_nage(),
                    rx.vstack(
                        rx.hstack(
                            rx.heading(State.selected_nage + " (" + State.current_bassin + ")", size="4", color=rx.color("gray", 12)),
                            rx.spacer(),
                            rx.button(
                                rx.hstack(rx.icon(tag="chevron-left", size=16), rx.text("Retour", font_size="0.8em"), spacing="1", align="center"),
                                on_click=State.nav_back_to_nageur,
                                variant="ghost", color_scheme="gray", size="1",
                            ),
                            width="100%", align="center",
                        ),
                        rx.segmented_control.root(
                            rx.segmented_control.item("25m", value="25m"),
                            rx.segmented_control.item("50m", value="50m"),
                            on_change=State.change_bassin, value=State.current_bassin, width="100%",
                        ),
                        rx.hstack(
                            rx.badge("RECORD : " + State.best_time_val, color_scheme="blue", variant="solid", size="3", flex_grow="1"),
                            width="100%",
                        ),
                        # ── Classements ──────────────────────────────
                        rx.vstack(
                            rx.text(State.ranking_title, font_size="0.72em", font_weight="bold", color=rx.color("gray", 11)),
                            rx.cond(
                                State.is_senior,
                                # ── Senior : TC uniquement ───────────
                                rx.hstack(
                                    rx.vstack(
                                        rx.hstack(rx.html('<svg width="16" height="11" viewBox="0 0 3 2" style="display:inline-block;vertical-align:middle;border-radius:1px;"><rect width="1" height="2" fill="#002395"/><rect width="1" height="2" x="1" fill="#fff"/><rect width="1" height="2" x="2" fill="#ed2939"/></svg>'), rx.text("France", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                        rx.text(State.ranking_national_tc_txt, font_size="1em", font_weight="bold", color=rx.color("blue", 9)),
                                        spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("national_tc"),
                                    ),
                                    rx.divider(orientation="vertical", height="32px"),
                                    rx.vstack(
                                        rx.hstack(rx.text("🏔", font_size="0.8em"), rx.text("AURA", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                        rx.text(State.ranking_region_tc_txt, font_size="1em", font_weight="bold", color=rx.color("green", 9)),
                                        spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("region_tc"),
                                    ),
                                    rx.divider(orientation="vertical", height="32px"),
                                    rx.vstack(
                                        rx.hstack(rx.text("📍", font_size="0.8em"), rx.text("Isère", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                        rx.text(State.ranking_dept_tc_txt, font_size="1em", font_weight="bold", color=rx.color("orange", 9)),
                                        spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("dept_tc"),
                                    ),
                                    width="100%", align="center", padding_top="8px",
                                ),
                                # ── Jeune : onglets cat + TC ─────────
                                rx.tabs.root(
                                    rx.tabs.list(
                                        rx.tabs.trigger(State.current_category, value="cat", flex_grow="1"),
                                        rx.tabs.trigger("TC", value="tc", flex_grow="1"),
                                        width="100%",
                                    ),
                                    rx.tabs.content(
                                        rx.hstack(
                                            rx.vstack(
                                                rx.hstack(rx.html('<svg width="16" height="11" viewBox="0 0 3 2" style="display:inline-block;vertical-align:middle;border-radius:1px;"><rect width="1" height="2" fill="#002395"/><rect width="1" height="2" x="1" fill="#fff"/><rect width="1" height="2" x="2" fill="#ed2939"/></svg>'), rx.text("France", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_national_txt, font_size="1em", font_weight="bold", color=rx.color("blue", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("national"),
                                            ),
                                            rx.divider(orientation="vertical", height="32px"),
                                            rx.vstack(
                                                rx.hstack(rx.text("🏔", font_size="0.8em"), rx.text("AURA", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_region_txt, font_size="1em", font_weight="bold", color=rx.color("green", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("region"),
                                            ),
                                            rx.divider(orientation="vertical", height="32px"),
                                            rx.vstack(
                                                rx.hstack(rx.text("📍", font_size="0.8em"), rx.text("Isère", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_dept_txt, font_size="1em", font_weight="bold", color=rx.color("orange", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("dept"),
                                            ),
                                            width="100%", align="center", padding_top="8px",
                                        ),
                                        value="cat",
                                    ),
                                    rx.tabs.content(
                                        rx.hstack(
                                            rx.vstack(
                                                rx.hstack(rx.html('<svg width="16" height="11" viewBox="0 0 3 2" style="display:inline-block;vertical-align:middle;border-radius:1px;"><rect width="1" height="2" fill="#002395"/><rect width="1" height="2" x="1" fill="#fff"/><rect width="1" height="2" x="2" fill="#ed2939"/></svg>'), rx.text("France", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_national_tc_txt, font_size="1em", font_weight="bold", color=rx.color("blue", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("national_tc"),
                                            ),
                                            rx.divider(orientation="vertical", height="32px"),
                                            rx.vstack(
                                                rx.hstack(rx.text("🏔", font_size="0.8em"), rx.text("AURA", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_region_tc_txt, font_size="1em", font_weight="bold", color=rx.color("green", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("region_tc"),
                                            ),
                                            rx.divider(orientation="vertical", height="32px"),
                                            rx.vstack(
                                                rx.hstack(rx.text("📍", font_size="0.8em"), rx.text("Isère", font_size="0.7em", color=rx.color("gray", 11)), spacing="1", align="center"),
                                                rx.text(State.ranking_dept_tc_txt, font_size="1em", font_weight="bold", color=rx.color("orange", 9)),
                                                spacing="0", align_items="center", flex_grow="1", cursor="pointer", on_click=State.open_top10("dept_tc"),
                                            ),
                                            width="100%", align="center", padding_top="8px",
                                        ),
                                        value="tc",
                                    ),
                                    default_value="cat", width="100%",
                                ),
                            ),
                            spacing="1", align_items="start",
                            width="100%", padding="8px 12px",
                            border_radius="8px",
                            background_color=rx.color("gray", 2),
                            border="1px solid var(--gray-4)",
                        ),
                        # ── Qualifications ───────────────────────────
                        rx.cond(
                            State.qualif_rows.length() > 0,
                            rx.vstack(
                                rx.text("Qualifications", font_size="0.72em", font_weight="bold", color=rx.color("gray", 11)),
                                rx.foreach(State.qualif_rows, qualif_row_ui),
                                spacing="1", align_items="start",
                                width="100%", padding="8px 12px",
                                border_radius="8px",
                                background_color=rx.color("gray", 2),
                                border="1px solid var(--gray-4)",
                            ),
                        ),
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("Date"),
                                    rx.table.column_header_cell("Temps"),
                                    rx.table.column_header_cell("Pts"),
                                ),
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.filtered_data,
                                    lambda r: rx.table.row(
                                        rx.table.cell(r.D),
                                        rx.table.cell(rx.text(r.T, font_weight=rx.cond(r.T == State.best_time_val, "bold", "normal"), color=rx.cond(r.T == State.best_time_val, rx.color("blue", 9), rx.color("gray", 12)))),
                                        rx.table.cell(rx.text(r.P, color=rx.color("gray", 11))),
                                        cursor="pointer",
                                        _hover={"background_color": "var(--gray-3)"},
                                        on_click=State.open_dialog(r.D + r.T, r.N, r.V, r.D),
                                    ),
                                ),
                            ),
                            width="100%", size="1", variant="surface",
                        ),
                        rx.box(
                            rx.el.canvas(
                                id="swc",
                                style={"width": "100%", "height": "220px"},
                                on_mount=State.render_chart,
                            ),
                            width="100%", border="1px solid var(--gray-4)",
                            border_radius="12px", overflow="hidden", padding="10px",
                        ),
                        spacing="4", padding="0.8em", width="100%", padding_bottom="5em",
                    ),
                    width=["100%", "420px"], spacing="0",
                ),
            ),
            ),
        ),
        min_height="0",
        ),
        appearance="inherit",
    )

app = rx.App(
    theme=rx.theme(appearance="inherit"),
    head_components=[
        rx.el.script(src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"),
        rx.el.script(src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"),
        rx.el.script("document.documentElement.lang='fr';"),
        rx.el.title("PdC Swim"),
        rx.el.meta(http_equiv="content-language", content="fr"),
        rx.el.style("html { overflow-y: scroll; }"),
        rx.el.link(rel="icon", type="image/jpeg", href="/icon.jpg"),
        rx.el.link(rel="apple-touch-icon", sizes="512x512", href="/icon.jpg"),
        rx.el.meta(name="apple-mobile-web-app-capable", content="yes"),
        rx.el.meta(name="apple-mobile-web-app-status-bar-style", content="default"),
        rx.el.meta(name="apple-mobile-web-app-title", content="PdC Swim"),
        rx.el.meta(name="mobile-web-app-capable", content="yes"),
    ],
)
app.add_page(index, route="/", on_load=State.on_load)
app.add_page(index, route="/nageur/tristan",  on_load=State.on_load_route)
app.add_page(index, route="/nageur/louis",    on_load=State.on_load_route)
app.add_page(index, route="/nageur/anthony",  on_load=State.on_load_route)
app.add_page(index, route="/nageur/matthieu", on_load=State.on_load_route)
app.add_page(index, route="/nageur/aline",    on_load=State.on_load_route)
app.add_page(index, route="/nageur/nola",     on_load=State.on_load_route)
app.add_page(index, route="/nageur/arthur",   on_load=State.on_load_route)
app.add_page(index, route="/nageur/corentin", on_load=State.on_load_route)