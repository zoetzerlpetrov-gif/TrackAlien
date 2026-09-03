#!/usr/bin/env python3
"""
UAP War Room — Extractor de datos
=================================
Consulta múltiples fuentes abiertas y genera GeoJSON con eventos UAP/fenómenos
no humanos para el mapa interactivo.

Fuentes:
  - GDELT v2 DOC API  (noticias globales geolocalizadas, sin API key)
  - NUFORC public data (CSV histórico + scraping reciente)
  - Google News RSS   (términos en es/en/pt/fr)
  - Reddit r/UFOs     (JSON público, sin auth)

Salida:
  data/events_recent.geojson       (últimos 7 días)
  data/events_historical.geojson   (casos documentados históricos)
  data/manifest.json               (metadatos de la corrida)
"""

import json
import os
import csv
import time
import random
import hashlib
import logging
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Configuración ──────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("uap-fetcher")

TODAY = datetime.now(timezone.utc)
SEVEN_DAYS_AGO = TODAY - timedelta(days=7)

# Términos de búsqueda en múltiples idiomas
SEARCH_TERMS = {
    "en": ["ufo sighting","unidentified aerial phenomenon","uap sighting",
           "alien encounter","unidentified flying object","strange lights sky",
           "unidentified object sky","flying saucer","extraterrestrial"],
    "es": ["avistamiento ovni","objeto volador no identificado","luces extrañas cielo",
           "fenómeno aéreo no identificado","contacto extraterrestre","ovni avistamiento"],
    "pt": ["avistamento ovni","fenômeno aéreo não identificado","luzes estranhas céu",
           "objeto voador não identificado"],
    "fr": ["observation ovni","phénomène aérien non identifié","lumières étranges ciel"],
}

# Tipos de evento — clasificación por palabras clave en el título/descripción
TYPE_KEYWORDS = {
    "uso":          ["underwater","submarine","submersible","ocean","sea","maritime","usmar",
                     "submarino","marítimo","oceáno","subacuático"],
    "contact":      ["alien","extraterrestrial","creature","being","entity","contact","abduction",
                     "extraterrestre","criatura","contacto","ser","secuestro"],
    "lights_sky":   ["lights","light","glow","flash","formation","lumières","luces","luz","brillo"],
    "lights_sea":   ["ocean light","sea light","underwater light","bioluminescent unidentified",
                     "luz mar","luz océano"],
    "lights_ground":["ground light","field light","forest light","orb ground",
                     "luz tierra","orbe","luz campo"],
    "sound":        ["sound","noise","hum","trumpet","boom","sonic","vibration",
                     "sonido","ruido","zumbido","trompeta","estruendo"],
    "em":           ["electromagnetic","magnetic","electrical","power outage","blackout","compass",
                     "electrónico","magnético","apagón","brújula"],
    "crop":         ["crop circle","crop formation","agroglyph","field pattern",
                     "círculo cultivo","figura campo","círculos trigo"],
    "ufo":          ["ufo","uap","ovni","flying saucer","disc","triangle","orb","sphere","metallic",
                     "platillo","disco","triángulo","esfera"],
}

# Coordenadas aproximadas de capitales/ciudades para búsqueda por nombre
CITY_COORDS = {
    "united states":{"lat":39.0,"lng":-98.0}, "usa":{"lat":39.0,"lng":-98.0},
    "mexico":{"lat":23.6,"lng":-102.5}, "méxico":{"lat":23.6,"lng":-102.5},
    "brazil":{"lat":-14.2,"lng":-51.9}, "brasil":{"lat":-14.2,"lng":-51.9},
    "argentina":{"lat":-38.4,"lng":-63.6},
    "chile":{"lat":-35.7,"lng":-71.5},
    "colombia":{"lat":4.6,"lng":-74.1},
    "peru":{"lat":-9.2,"lng":-75.0}, "perú":{"lat":-9.2,"lng":-75.0},
    "united kingdom":{"lat":55.4,"lng":-3.4}, "uk":{"lat":55.4,"lng":-3.4},
    "france":{"lat":46.2,"lng":2.2}, "france":{"lat":46.2,"lng":2.2},
    "germany":{"lat":51.2,"lng":10.5},
    "spain":{"lat":40.5,"lng":-3.7}, "españa":{"lat":40.5,"lng":-3.7},
    "russia":{"lat":61.5,"lng":105.3},
    "china":{"lat":35.9,"lng":104.2},
    "japan":{"lat":36.2,"lng":138.3},
    "india":{"lat":20.6,"lng":78.9},
    "australia":{"lat":-25.3,"lng":133.8},
    "canada":{"lat":56.1,"lng":-106.3},
    "norway":{"lat":60.5,"lng":8.5}, "noruega":{"lat":60.5,"lng":8.5},
    "belgium":{"lat":50.5,"lng":4.5}, "bélgica":{"lat":50.5,"lng":4.5},
    "iran":{"lat":32.4,"lng":53.7},
    "nigeria":{"lat":9.1,"lng":8.7},
    "egypt":{"lat":26.8,"lng":30.8}, "egipto":{"lat":26.8,"lng":30.8},
    "zimbabwe":{"lat":-19.0,"lng":29.9},
    "ukraine":{"lat":48.4,"lng":31.2},
    "turkey":{"lat":38.9,"lng":35.2}, "turquía":{"lat":38.9,"lng":35.2},
    "south korea":{"lat":35.9,"lng":127.8},
    "new zealand":{"lat":-40.9,"lng":174.9},
    "portugal":{"lat":39.4,"lng":-8.2},
    "sweden":{"lat":60.1,"lng":18.6}, "suecia":{"lat":60.1,"lng":18.6},
    "finland":{"lat":61.9,"lng":25.7}, "finlandia":{"lat":61.9,"lng":25.7},
    "iceland":{"lat":64.9,"lng":-18.5}, "islandia":{"lat":64.9,"lng":-18.5},
}

# ─── Utilidades ─────────────────────────────────────────────────────────────

def fetch_url(url, timeout=20):
    """GET simple con headers de navegador para evitar bloqueos."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; UAPWarRoom-DataBot/1.0; research purposes)",
        "Accept": "application/json,application/xml,text/html,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning(f"Error al obtener {url}: {e}")
        return None


def classify_type(text):
    """Clasifica el tipo de evento según palabras clave en el texto."""
    text_lower = (text or "").lower()
    for etype, kws in TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return etype
    return "ufo"  # default


def country_to_coords(country_text):
    """Convierte nombre de país a coordenadas aproximadas."""
    if not country_text:
        return None
    ct = country_text.lower().strip()
    for key, coords in CITY_COORDS.items():
        if key in ct or ct in key:
            # Añadir pequeño ruido para evitar marcadores apilados
            return {
                "lat": coords["lat"] + random.uniform(-2, 2),
                "lng": coords["lng"] + random.uniform(-2, 2)
            }
    return None


def make_id(text):
    return "G" + hashlib.md5(text.encode()).hexdigest()[:8].upper()


def to_geojson(events):
    features = []
    for ev in events:
        if not ev.get("lat") or not ev.get("lng"):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [ev["lng"], ev["lat"]]},
            "properties": {
                "id":          ev.get("id", ""),
                "type":        ev.get("type", "ufo"),
                "date":        ev.get("date", ""),
                "recent":      ev.get("recent", False),
                "isNew":       ev.get("isNew", False),
                "title":       ev.get("title", "Sin título"),
                "description": ev.get("desc", ""),
                "witnesses":   ev.get("witnesses", 0),
                "credibility": ev.get("credibility", "MEDIA"),
                "country":     ev.get("country", ""),
                "sources":     "|".join(ev.get("sources", [])),
            }
        })
    return {"type": "FeatureCollection", "features": features}


# ─── Fuente 1: GDELT DOC API ────────────────────────────────────────────────

def fetch_gdelt_recent():
    """
    Consulta GDELT v2 DOC API para artículos recientes sobre UAP/OVNI/fenómenos.
    Devuelve lista de eventos con coordenadas aproximadas (por país de la fuente).
    """
    log.info("Consultando GDELT DOC API...")
    events = []

    # Términos combinados para una sola query (GDELT tiene límite de caracteres)
    query = "(ufo OR ovni OR \"unidentified aerial\" OR extraterrestre OR \"strange lights\" OR \"luces extrañas\" OR \"avistamiento\" OR \"flying saucer\")"
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        + urllib.parse.urlencode({
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": "250",
            "timespan": "7d",
            "sort": "DateDesc",
        })
    )

    raw = fetch_url(url)
    if not raw:
        return events

    try:
        data = json.loads(raw)
        articles = data.get("articles") or []
        log.info(f"  GDELT: {len(articles)} artículos")

        for art in articles:
            title    = art.get("title", "")
            url_art  = art.get("url", "")
            domain   = art.get("domain", "")
            seendate = art.get("seendate", "")
            # GDELT devuelve 'sourcecountry' con código ISO2 en algunos modos
            country_code = art.get("sourcecountry", "")

            # Convertir fecha GDELT (YYYYMMDDHHMMSS) a YYYY-MM-DD
            date_str = seendate[:8] if len(seendate) >= 8 else TODAY.strftime("%Y%m%d")
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            coords = country_to_coords(country_code) or {"lat": 0.0, "lng": 0.0}
            ev_type = classify_type(title)

            events.append({
                "id":     make_id(url_art),
                "lat":    coords["lat"],
                "lng":    coords["lng"],
                "type":   ev_type,
                "date":   date_fmt,
                "recent": True,
                "isNew":  date_fmt == TODAY.strftime("%Y-%m-%d"),
                "title":  title or "Evento UAP sin título",
                "desc":   f"Fuente: {domain}. Cobertura detectada por GDELT en {country_code or 'ubicación desconocida'}.",
                "witnesses": 0,
                "credibility": "MEDIA",
                "country": country_code,
                "sources": [domain, "GDELT Global Knowledge Graph"],
            })
    except Exception as e:
        log.warning(f"Error procesando GDELT: {e}")

    log.info(f"  GDELT: {len(events)} eventos procesados")
    return events


# ─── Fuente 2: Google News RSS ──────────────────────────────────────────────

def fetch_google_news():
    """
    Consulta Google News RSS para términos en varios idiomas.
    Devuelve eventos recientes con coordenadas aproximadas.
    """
    log.info("Consultando Google News RSS...")
    events = []

    # Mapa simple de términos a tipo de evento
    queries = [
        ("ufo sighting", "en", "ufo"),
        ("avistamiento ovni", "es", "ufo"),
        ("alien encounter", "en", "contact"),
        ("extraterrestre contacto", "es", "contact"),
        ("strange lights sky", "en", "lights_sky"),
        ("luces extrañas cielo", "es", "lights_sky"),
        ("unidentified aerial phenomenon", "en", "ufo"),
        ("fenômeno aéreo não identificado", "pt", "ufo"),
        ("ovni avistamento", "pt", "ufo"),
        ("unidentified object ocean", "en", "uso"),
    ]

    seen_titles = set()

    for term, lang, default_type in queries:
        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode({"q": term, "hl": lang, "gl": "US", "ceid": f"US:{lang}"})
        )
        raw = fetch_url(url)
        if not raw:
            continue

        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            if channel is None:
                continue
            items = channel.findall("item")
            log.info(f"  Google News [{term}]: {len(items)} artículos")

            for item in items[:10]:  # máximo 10 por término
                title_el = item.find("title")
                link_el  = item.find("link")
                pub_el   = item.find("pubDate")

                title = (title_el.text or "").strip() if title_el is not None else ""
                link  = (link_el.text or "").strip()  if link_el  is not None else ""
                pub   = (pub_el.text or "").strip()   if pub_el   is not None else ""

                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                # Parsear fecha RFC2822
                try:
                    from email.utils import parsedate
                    dt = parsedate(pub)
                    date_str = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}" if dt else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")

                ev_type = classify_type(title) if classify_type(title) != "ufo" else default_type

                # Coordenadas: sin geocoding real → posición aleatoria plausible
                # En producción usar Nominatim para extraer ciudad del título
                # Por ahora: coordenadas de un país/región inferido del idioma
                base_coords = {
                    "en": {"lat": 39.0,  "lng": -98.0},
                    "es": {"lat": 19.4,  "lng": -99.1},
                    "pt": {"lat": -14.2, "lng": -51.9},
                }.get(lang, {"lat": 0.0, "lng": 0.0})

                events.append({
                    "id":     make_id(link),
                    "lat":    base_coords["lat"] + random.uniform(-10, 10),
                    "lng":    base_coords["lng"] + random.uniform(-10, 10),
                    "type":   ev_type,
                    "date":   date_str,
                    "recent": True,
                    "isNew":  date_str == TODAY.strftime("%Y-%m-%d"),
                    "title":  title,
                    "desc":   f"Noticia detectada en Google News. Término de búsqueda: '{term}'.",
                    "witnesses": 0,
                    "credibility": "BAJA (señal noticiosa)",
                    "country": "—",
                    "sources": [link[:80] if link else "Google News", "Google News RSS"],
                })
        except Exception as e:
            log.warning(f"  Error Google News [{term}]: {e}")

        time.sleep(0.5)  # amable con el servidor

    log.info(f"  Google News: {len(events)} eventos totales")
    return events


# ─── Fuente 3: NUFORC histórico (CSV público de GitHub) ─────────────────────

def fetch_nuforc_historical(max_records=500):
    """
    Descarga el CSV histórico de NUFORC desde GitHub (~80k registros, ~20MB).
    Retorna una muestra de los casos más relevantes con coordenadas reales.
    """
    log.info("Descargando dataset histórico NUFORC...")
    events = []

    # CSV público con lat/lon: github.com/planetsig/ufo-reports
    url = "https://raw.githubusercontent.com/planetsig/ufo-reports/master/csv-data/ufo-scrubbed-geocoded-time-standardized.csv"
    raw = fetch_url(url, timeout=60)
    if not raw:
        log.warning("No se pudo descargar CSV NUFORC")
        return events

    lines = raw.splitlines()
    reader = csv.reader(lines)

    # Columnas: datetime,city,state,country,shape,duration (seconds),duration (hours/min),
    #           comments,date posted,latitude,longitude
    count = 0
    for row in reader:
        if len(row) < 11:
            continue
        try:
            lat = float(row[9])
            lng = float(row[10])
            if abs(lat) < 0.1 and abs(lng) < 0.1:
                continue  # coordenadas inválidas
        except (ValueError, IndexError):
            continue

        date_raw = row[0].strip()
        city     = row[1].strip()
        state    = row[2].strip()
        country  = row[3].strip().upper()
        shape    = row[4].strip().lower()
        desc     = row[7].strip()[:300]

        # Clasificar tipo
        shape_map = {
            "light":    "lights_sky",
            "formation":"lights_sky",
            "flash":    "lights_sky",
            "other":    "other",
            "disk":     "ufo",
            "cigar":    "ufo",
            "saucer":   "ufo",
            "triangle": "ufo",
            "oval":     "ufo",
            "sphere":   "ufo",
            "fireball": "lights_sky",
            "changing": "ufo",
            "cylinder": "ufo",
            "chevron":  "ufo",
            "diamond":  "ufo",
            "cone":     "ufo",
            "egg":      "ufo",
            "unknown":  "ufo",
        }
        ev_type = shape_map.get(shape, classify_type(desc))

        # Parsear fecha
        try:
            date_parts = date_raw.split(" ")[0].split("/")
            date_str = f"{date_parts[2]}-{date_parts[0]:0>2}-{date_parts[1]:0>2}"
        except Exception:
            date_str = "—"

        loc = f"{city}, {state}" if state else city
        country_full = {"us":"EE.UU.","ca":"Canadá","gb":"Reino Unido","au":"Australia"}.get(country.lower(), country)

        events.append({
            "id":     make_id(f"nuforc-{lat}-{lng}-{date_raw}"),
            "lat":    lat,
            "lng":    lng,
            "type":   ev_type,
            "date":   date_str,
            "recent": False,
            "isNew":  False,
            "title":  f"Avistamiento NUFORC: {shape.capitalize()} en {loc}",
            "desc":   desc or f"Forma: {shape}. Reportado en {loc}.",
            "witnesses": 1,
            "credibility": "MEDIA (reporte civil NUFORC)",
            "country": country_full,
            "sources": [f"NUFORC — {loc}", "nuforc.org"],
        })
        count += 1
        if count >= max_records:
            break

    log.info(f"  NUFORC histórico: {count} eventos")
    return events


# ─── Fuente 4: Reddit r/UFOs ────────────────────────────────────────────────

def fetch_reddit_ufos(limit=50):
    """
    Consulta el JSON público de Reddit para r/UFOs (posts recientes).
    """
    log.info("Consultando Reddit r/UFOs...")
    events = []
    url = f"https://www.reddit.com/r/UFOs/new.json?limit={limit}&raw_json=1"
    raw = fetch_url(url)
    if not raw:
        return events

    try:
        data = json.loads(raw)
        posts = data.get("data", {}).get("children", [])
        log.info(f"  Reddit: {len(posts)} posts")

        for post in posts:
            p = post.get("data", {})
            title = p.get("title", "")
            selftext = p.get("selftext", "")[:200]
            timestamp = p.get("created_utc", 0)
            url_post = f"https://reddit.com{p.get('permalink','')}"
            flair = (p.get("link_flair_text") or "").lower()
            score = p.get("score", 0)

            # Solo posts con algo de score para filtrar spam/clickbait
            if score < 10:
                continue

            # Fecha
            if timestamp:
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
            else:
                date_str = TODAY.strftime("%Y-%m-%d")

            ev_type = classify_type(title + " " + selftext)

            # Intentar extraer ubicación del flair o del título
            coords = None
            for country_name, c in CITY_COORDS.items():
                if country_name in title.lower() or country_name in selftext.lower():
                    coords = {
                        "lat": c["lat"] + random.uniform(-3, 3),
                        "lng": c["lng"] + random.uniform(-3, 3)
                    }
                    break
            if not coords:
                # Sin ubicación clara: saltar
                continue

            events.append({
                "id":     make_id(url_post),
                "lat":    coords["lat"],
                "lng":    coords["lng"],
                "type":   ev_type,
                "date":   date_str,
                "recent": True,
                "isNew":  date_str == TODAY.strftime("%Y-%m-%d"),
                "title":  title[:120],
                "desc":   selftext or f"Post en Reddit r/UFOs. Score: {score}.",
                "witnesses": 0,
                "credibility": "MEDIA (Reddit r/UFOs)",
                "country": "—",
                "sources": [url_post, "Reddit r/UFOs"],
            })
    except Exception as e:
        log.warning(f"Error Reddit: {e}")

    log.info(f"  Reddit: {len(events)} eventos con ubicación")
    return events


# ─── Deduplicación ──────────────────────────────────────────────────────────

def deduplicate(events, radius_km=50):
    """
    Elimina eventos duplicados por proximidad geográfica y fecha similares.
    """
    seen = {}
    result = []
    for ev in events:
        # Clave simple: cuadrícula de 0.5°
        key = (round(ev["lat"]*2)/2, round(ev["lng"]*2)/2, ev.get("date","")[:7])
        if key not in seen:
            seen[key] = True
            result.append(ev)
    return result


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("UAP WAR ROOM — Inicio de extracción de datos")
    log.info(f"Fecha: {TODAY.strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    all_recent = []
    all_historical = []

    # 1. GDELT (recientes)
    gdelt_events = fetch_gdelt_recent()
    all_recent.extend(gdelt_events)

    # 2. Google News (recientes)
    gnews_events = fetch_google_news()
    all_recent.extend(gnews_events)

    # 3. Reddit (recientes)
    reddit_events = fetch_reddit_ufos(limit=100)
    all_recent.extend(reddit_events)

    # 4. NUFORC histórico
    nuforc_hist = fetch_nuforc_historical(max_records=500)
    all_historical.extend(nuforc_hist)

    # Deduplicar
    all_recent     = deduplicate(all_recent)
    all_historical = deduplicate(all_historical)

    log.info(f"\nResumen:")
    log.info(f"  Eventos recientes   : {len(all_recent)}")
    log.info(f"  Eventos históricos  : {len(all_historical)}")

    # Guardar GeoJSON
    recent_path = DATA_DIR / "events_recent.geojson"
    hist_path   = DATA_DIR / "events_historical.geojson"
    manifest_path = DATA_DIR / "manifest.json"

    with open(recent_path, "w", encoding="utf-8") as f:
        json.dump(to_geojson(all_recent), f, ensure_ascii=False, indent=2)
    log.info(f"  ✓ {recent_path}")

    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(to_geojson(all_historical), f, ensure_ascii=False, indent=2)
    log.info(f"  ✓ {hist_path}")

    manifest = {
        "updated_at":     TODAY.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recent_count":   len(all_recent),
        "historical_count": len(all_historical),
        "sources_used":   ["GDELT", "Google News RSS", "Reddit r/UFOs", "NUFORC CSV"],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info(f"  ✓ {manifest_path}")
    log.info("=" * 60)
    log.info("Extracción completada")


if __name__ == "__main__":
    main()
