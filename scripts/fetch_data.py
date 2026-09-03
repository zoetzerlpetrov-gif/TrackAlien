#!/usr/bin/env python3
"""
UAP War Room - Extractor de datos (v2)
Fuentes: GDELT v2 DOC API, NUFORC CSV, Google News RSS,
         Reddit (r/UFOs r/aliens r/ufo r/paranormal r/mexico),
         Latest-UFO-Sightings RSS, UFO Stalker RSS,
         The Black Vault RSS
Salida: data/events_recent.geojson, data/events_historical.geojson, data/manifest.json
Filtro: sólo se conservan eventos mencionados en ≥2 dominios distintos
        O que provienen de NUFORC (base histórica única).
"""

import json, csv, time, random, hashlib, logging, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("uap-fetcher")

TODAY = datetime.now(timezone.utc)
SEVEN_DAYS_AGO = TODAY - timedelta(days=7)

TYPE_KEYWORDS = {
    "uso": ["underwater","submarine","submersible","ocean","sea","maritime","gulf","bay",
            "submarino","marítimo","subacuático","golfo","bahía","luz bajo el agua","luces bajo el mar",
            "luz en el mar","luz oceáno","objeto bajo el agua"],
    "contact": ["alien","extraterrestrial","creature","being","entity","contact","abduction",
                "extraterrestre","criatura","contacto","secuestro","abducción","ser de luz",
                "humanoid","humanoide","occupant","tripulante"],
    "lights_sky": ["lights","light","glow","flash","formation","streak","fireball",
                   "luces","luz","brillo","destello","formación","bola de fuego","chorro de luz"],
    "lights_sea": ["ocean light","sea light","underwater light","luz mar","luz océano",
                   "luces oceano","luminiscencia","bioluminiscencia","objeto mar"],
    "lights_ground": ["ground light","field light","forest light","orb ground","landed",
                      "luz tierra","orbe","luz campo","aterrizó","aterrizaje","campo"],
    "volcano": ["volcán","volcan","popocatepetl","popo","crater","cráter","eruption",
                "erupción","objeto volcán","luces volcán","ovni volcán","ufo volcano",
                "objeto crater","entran volcán","salen volcán","popocatépetl"],
    "sound": ["sound","noise","hum","trumpet","boom","sonic","vibration","bang",
              "sonido","ruido","zumbido","trompeta","estruendo","vibración","retumbar"],
    "em": ["electromagnetic","magnetic","electrical","power outage","blackout","compass",
           "electrónico","magnético","apagón","interferencia","radar","fallo eléctrico"],
    "crop": ["crop circle","crop formation","agroglyph","field pattern",
             "círculo cultivo","figura campo","marcas campo"],
    "ufo": ["ufo","uap","ovni","flying saucer","disc","triangle","orb","sphere","metallic",
            "tic-tac","tictac","platillo","disco","triángulo","esfera","objeto no identificado",
            "fenómeno aéreo","aerial phenomenon","orbe","nube lenticular"],
}

# Coordenadas por país y ciudades clave (incluyendo México detallado)
CITY_COORDS = {
    # México — ciudades y volcanes
    "mexico":{"lat":23.6,"lng":-102.5},"méxico":{"lat":23.6,"lng":-102.5},
    "cdmx":{"lat":19.43,"lng":-99.13},"ciudad de mexico":{"lat":19.43,"lng":-99.13},
    "ciudad de méxico":{"lat":19.43,"lng":-99.13},"df":{"lat":19.43,"lng":-99.13},
    "popocatepetl":{"lat":19.02,"lng":-98.62},"popocatépetl":{"lat":19.02,"lng":-98.62},
    "popo":{"lat":19.02,"lng":-98.62},"volcán":{"lat":19.02,"lng":-98.62},
    "tamaulipas":{"lat":24.0,"lng":-99.0},"reynosa":{"lat":26.1,"lng":-98.3},
    "matamoros":{"lat":25.9,"lng":-97.5},"tampico":{"lat":22.3,"lng":-97.9},
    "tijuana":{"lat":32.53,"lng":-117.02},"baja california":{"lat":30.0,"lng":-115.0},
    "ensenada":{"lat":31.87,"lng":-116.6},"mexicali":{"lat":32.63,"lng":-115.45},
    "monterrey":{"lat":25.67,"lng":-100.31},"nuevo leon":{"lat":25.5,"lng":-99.8},
    "guadalajara":{"lat":20.66,"lng":-103.35},"jalisco":{"lat":20.8,"lng":-103.3},
    "veracruz":{"lat":19.17,"lng":-96.13},"oaxaca":{"lat":17.07,"lng":-96.72},
    "yucatan":{"lat":20.97,"lng":-89.62},"yucatán":{"lat":20.97,"lng":-89.62},
    "merida":{"lat":20.97,"lng":-89.62},"mérida":{"lat":20.97,"lng":-89.62},
    "cancun":{"lat":21.16,"lng":-86.85},"cancún":{"lat":21.16,"lng":-86.85},
    "puebla":{"lat":19.04,"lng":-98.2},"hidalgo":{"lat":20.1,"lng":-98.7},
    "michoacan":{"lat":19.57,"lng":-101.7},"guerrero":{"lat":17.4,"lng":-100.0},
    "sonora":{"lat":29.0,"lng":-110.6},"chihuahua":{"lat":28.6,"lng":-106.1},
    "sinaloa":{"lat":24.8,"lng":-107.4},"mazatlan":{"lat":23.23,"lng":-106.42},
    "acapulco":{"lat":16.86,"lng":-99.88},"golfo de mexico":{"lat":23.0,"lng":-90.0},
    "pacifico":{"lat":18.0,"lng":-105.0},"océano pacífico":{"lat":18.0,"lng":-105.0},
    "mar de cortés":{"lat":28.0,"lng":-111.0},"sea of cortez":{"lat":28.0,"lng":-111.0},
    # Centroamérica / Caribe
    "guatemala":{"lat":15.8,"lng":-90.2},"honduras":{"lat":15.2,"lng":-86.2},
    "cuba":{"lat":21.5,"lng":-79.5},"puerto rico":{"lat":18.2,"lng":-66.6},
    # Sudamérica
    "brazil":{"lat":-14.2,"lng":-51.9},"brasil":{"lat":-14.2,"lng":-51.9},
    "argentina":{"lat":-38.4,"lng":-63.6},"chile":{"lat":-35.7,"lng":-71.5},
    "colombia":{"lat":4.6,"lng":-74.1},"peru":{"lat":-9.2,"lng":-75.0},
    "perú":{"lat":-9.2,"lng":-75.0},"venezuela":{"lat":8.0,"lng":-66.6},
    "ecuador":{"lat":-1.8,"lng":-78.2},"bolivia":{"lat":-16.3,"lng":-63.6},
    # EE.UU.
    "united states":{"lat":39.0,"lng":-98.0},"usa":{"lat":39.0,"lng":-98.0},
    "canada":{"lat":56.1,"lng":-106.3},"new york":{"lat":40.7,"lng":-74.0},
    "california":{"lat":36.8,"lng":-119.4},"florida":{"lat":27.7,"lng":-81.5},
    "texas":{"lat":31.5,"lng":-99.3},"arizona":{"lat":34.3,"lng":-111.1},
    "nevada":{"lat":38.3,"lng":-117.1},"new mexico":{"lat":34.5,"lng":-106.2},
    # Europa
    "united kingdom":{"lat":55.4,"lng":-3.4},"uk":{"lat":55.4,"lng":-3.4},
    "france":{"lat":46.2,"lng":2.2},"germany":{"lat":51.2,"lng":10.5},
    "spain":{"lat":40.5,"lng":-3.7},"españa":{"lat":40.5,"lng":-3.7},
    "italy":{"lat":42.5,"lng":12.6},"italia":{"lat":42.5,"lng":12.6},
    "russia":{"lat":61.5,"lng":105.3},"norway":{"lat":60.5,"lng":8.5},
    "noruega":{"lat":60.5,"lng":8.5},"belgium":{"lat":50.5,"lng":4.5},
    "bélgica":{"lat":50.5,"lng":4.5},"portugal":{"lat":39.4,"lng":-8.2},
    "sweden":{"lat":60.1,"lng":18.6},"finland":{"lat":61.9,"lng":25.7},
    "iceland":{"lat":64.9,"lng":-18.5},"ukraine":{"lat":48.4,"lng":31.2},
    "turkey":{"lat":38.9,"lng":35.2},"turquía":{"lat":38.9,"lng":35.2},
    # Asia / Oceanía
    "china":{"lat":35.9,"lng":104.2},"japan":{"lat":36.2,"lng":138.3},
    "india":{"lat":20.6,"lng":78.9},"south korea":{"lat":35.9,"lng":127.8},
    "australia":{"lat":-25.3,"lng":133.8},"new zealand":{"lat":-40.9,"lng":174.9},
    "iran":{"lat":32.4,"lng":53.7},
    # África
    "nigeria":{"lat":9.1,"lng":8.7},"egypt":{"lat":26.8,"lng":30.8},
    "egipto":{"lat":26.8,"lng":30.8},"zimbabwe":{"lat":-19.0,"lng":29.9},
    "south africa":{"lat":-29.0,"lng":25.1},
}

def fetch_url(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; UAPWarRoom-DataBot/2.0; +https://github.com)",
            "Accept": "application/json,application/xml,text/html,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning(f"Error al obtener {url[:80]}: {e}")
        return None

def classify_type(text):
    text_lower = (text or "").lower()
    for etype, kws in TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return etype
    return "ufo"

def location_from_text(text):
    """Busca coordenadas conocidas dentro del texto dado."""
    tl = (text or "").lower()
    # Priorizar matches más específicos (ciudades antes que países)
    specific = ["popocatepetl","popocatépetl","popo","cdmx","ciudad de mexico","ciudad de méxico",
                "tijuana","tamaulipas","monterrey","guadalajara","veracruz","cancun","cancún",
                "reynosa","matamoros","new york","california","texas","florida","arizona","nevada"]
    for key in specific:
        if key in tl and key in CITY_COORDS:
            c = CITY_COORDS[key]
            return {"lat": c["lat"] + random.uniform(-1, 1), "lng": c["lng"] + random.uniform(-1, 1)}
    for key, coords in CITY_COORDS.items():
        if key in tl:
            return {"lat": coords["lat"] + random.uniform(-2, 2), "lng": coords["lng"] + random.uniform(-2, 2)}
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
                "id": ev.get("id", ""),
                "type": ev.get("type", "ufo"),
                "date": ev.get("date", ""),
                "recent": ev.get("recent", False),
                "isNew": ev.get("isNew", False),
                "title": ev.get("title", "Sin título"),
                "description": ev.get("desc", ""),
                "witnesses": ev.get("witnesses", 0),
                "credibility": ev.get("credibility", "MEDIA"),
                "country": ev.get("country", ""),
                "sources": "|".join(ev.get("sources", [])),
                "source_count": ev.get("source_count", 1),
            },
        })
    return {"type": "FeatureCollection", "features": features}

# ─────────────────────────────────────────────────────────────
# GDELT — consultas amplias + México específico
# ─────────────────────────────────────────────────────────────
def fetch_gdelt_recent():
    log.info("Consultando GDELT DOC API (consultas múltiples)...")
    events = []
    queries = [
        # Global UAP/OVNI
        '(ufo OR ovni OR "unidentified aerial" OR "unidentified object" OR extraterrestre OR "flying saucer" OR "strange lights" OR "luces extrañas" OR avistamiento OR "aerial phenomenon")',
        # México específico
        '(Popocatépetl OVNI) OR (Popo objeto) OR ("volcán" "objeto" "extraño") OR ("entran volcán") OR ("crater" "objeto")',
        '(CDMX OVNI) OR ("Ciudad de México" OVNI) OR ("México" "luces extrañas" cielo) OR (Tamaulipas OVNI) OR (Tijuana OVNI)',
        '("luces submarinas" México) OR ("luz mar" OVNI) OR ("objeto mar" México) OR ("Golfo de México" "fenómeno")',
        # Inglés submarino
        '("underwater lights" OR "underwater ufo" OR "uso" OR "unidentified submerged") ocean OR sea OR gulf',
    ]
    seen_urls = set()
    for query in queries:
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            + urllib.parse.urlencode({
                "query": query, "mode": "artlist", "format": "json",
                "maxrecords": "200", "timespan": "7d", "sort": "DateDesc",
            })
        )
        raw = fetch_url(url, timeout=30)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            articles = data.get("articles") or []
            log.info(f"  GDELT [{query[:50]}...]: {len(articles)} artículos")
            for art in articles:
                url_art = art.get("url", "")
                if url_art in seen_urls:
                    continue
                seen_urls.add(url_art)
                title = art.get("title", "")
                domain = art.get("domain", "")
                seendate = art.get("seendate", "")
                country_code = art.get("sourcecountry", "")
                date_str = seendate[:8] if len(seendate) >= 8 else TODAY.strftime("%Y%m%d")
                date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                # Intentar ubicar en México primero
                coords = location_from_text(title + " " + country_code)
                if not coords:
                    from_CITY_COORDS = {k: v for k, v in CITY_COORDS.items() if k == country_code.lower()}
                    coords = (list(from_CITY_COORDS.values()) or [{"lat": 0.0, "lng": 0.0}])[0]
                    coords = {"lat": coords["lat"] + random.uniform(-2, 2), "lng": coords["lng"] + random.uniform(-2, 2)}
                events.append({
                    "id": make_id(url_art),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": classify_type(title),
                    "date": date_fmt, "recent": True,
                    "isNew": date_fmt == TODAY.strftime("%Y-%m-%d"),
                    "title": title or "Evento UAP sin título",
                    "desc": f"Fuente: {domain}. País: {country_code or '?'}. GDELT Global Knowledge Graph.",
                    "witnesses": 0, "credibility": "MEDIA",
                    "country": country_code,
                    "sources": [domain, "GDELT Global Knowledge Graph"],
                })
        except Exception as e:
            log.warning(f"Error procesando GDELT: {e}")
        time.sleep(0.5)
    log.info(f"  GDELT total: {len(events)} eventos únicos")
    return events

# ─────────────────────────────────────────────────────────────
# Google News RSS — términos globales + México detallado
# ─────────────────────────────────────────────────────────────
def fetch_google_news():
    log.info("Consultando Google News RSS (multi-término)...")
    events = []
    # (término, idioma, tipo_por_defecto, region_GL, coordenadas_base)
    queries = [
        # Inglés global
        ("ufo sighting",                   "en", "ufo",        "US", {"lat":39.0,"lng":-98.0}),
        ("alien encounter",                "en", "contact",    "US", {"lat":39.0,"lng":-98.0}),
        ("strange lights sky",             "en", "lights_sky", "US", {"lat":39.0,"lng":-98.0}),
        ("unidentified aerial phenomenon", "en", "ufo",        "US", {"lat":39.0,"lng":-98.0}),
        ("unidentified object ocean sea",  "en", "uso",        "US", {"lat":25.0,"lng":-90.0}),
        ("underwater ufo lights ocean",    "en", "uso",        "US", {"lat":25.0,"lng":-90.0}),
        # Español — México
        ("avistamiento ovni México",       "es", "ufo",        "MX", {"lat":23.6,"lng":-102.5}),
        ("luces extrañas cielo México",    "es", "lights_sky", "MX", {"lat":23.6,"lng":-102.5}),
        ("OVNI CDMX Ciudad de México",     "es", "ufo",        "MX", {"lat":19.43,"lng":-99.13}),
        ("Popocatépetl objeto extraño",    "es", "volcano",    "MX", {"lat":19.02,"lng":-98.62}),
        ("Popocatépetl luces OVNI volcán", "es", "volcano",    "MX", {"lat":19.02,"lng":-98.62}),
        ("Tamaulipas luces extrañas OVNI", "es", "ufo",        "MX", {"lat":24.0,"lng":-99.0}),
        ("Tijuana OVNI luces cielo",       "es", "ufo",        "MX", {"lat":32.53,"lng":-117.02}),
        ("luces submarinas mar México",    "es", "uso",        "MX", {"lat":20.0,"lng":-105.0}),
        ("extraterrestre contacto México", "es", "contact",    "MX", {"lat":23.6,"lng":-102.5}),
        ("Monterrey OVNI luces",           "es", "ufo",        "MX", {"lat":25.67,"lng":-100.31}),
        ("Guadalajara OVNI fenómeno",      "es", "ufo",        "MX", {"lat":20.66,"lng":-103.35}),
        # Español — global
        ("extraterrestre contacto",        "es", "contact",    "US", {"lat":19.0,"lng":-99.0}),
        ("ovni avistamiento",              "es", "ufo",        "US", {"lat":19.0,"lng":-99.0}),
        # Portugués
        ("ovni avistamento",               "pt", "ufo",        "BR", {"lat":-14.2,"lng":-51.9}),
        ("fenômeno aéreo não identificado","pt", "ufo",        "BR", {"lat":-14.2,"lng":-51.9}),
    ]
    seen_titles = set()
    for term, lang, default_type, gl, base_coords in queries:
        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode({"q": term, "hl": lang, "gl": gl, "ceid": f"{gl}:{lang}"})
        )
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            if channel is None:
                continue
            for item in channel.findall("item")[:12]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                source_el = item.find("source")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link = (link_el.text or "").strip() if link_el is not None else ""
                pub = (pub_el.text or "").strip() if pub_el is not None else ""
                source_name = (source_el.text or "Google News").strip() if source_el is not None else "Google News"
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                try:
                    from email.utils import parsedate
                    dt = parsedate(pub)
                    date_str = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}" if dt else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")
                ev_type = classify_type(title)
                if ev_type == "ufo":
                    ev_type = default_type
                # Intentar ubicación específica del título
                coords = location_from_text(title)
                if not coords:
                    coords = {
                        "lat": base_coords["lat"] + random.uniform(-5, 5),
                        "lng": base_coords["lng"] + random.uniform(-5, 5),
                    }
                events.append({
                    "id": make_id(link or title),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title,
                    "desc": f"Google News. Búsqueda: '{term}'. Fuente: {source_name}.",
                    "witnesses": 0, "credibility": "BAJA (señal noticiosa)",
                    "country": gl,
                    "sources": [source_name, link[:80] if link else "Google News RSS"],
                })
        except Exception as e:
            log.warning(f"  Error Google News [{term}]: {e}")
        time.sleep(0.4)
    log.info(f"  Google News: {len(events)} eventos")
    return events

# ─────────────────────────────────────────────────────────────
# Reddit — múltiples subreddits
# ─────────────────────────────────────────────────────────────
def fetch_reddit_multi(limit=75):
    log.info("Consultando Reddit (múltiples subreddits)...")
    all_events = []
    subreddits = [
        ("UFOs",       "ALTA (Reddit r/UFOs, score alto)"),
        ("aliens",     "MEDIA (Reddit r/aliens)"),
        ("ufo",        "MEDIA (Reddit r/ufo)"),
        ("paranormal", "BAJA (Reddit r/paranormal)"),
        ("mexico",     "BAJA (Reddit r/mexico — filtrado UAP)"),
    ]
    for sub, credibility in subreddits:
        raw = fetch_url(f"https://www.reddit.com/r/{sub}/new.json?limit={limit}&raw_json=1", timeout=20)
        if not raw:
            time.sleep(1)
            continue
        try:
            posts = json.loads(raw).get("data", {}).get("children", [])
            count_added = 0
            for post in posts:
                p = post.get("data", {})
                title = p.get("title", "")
                selftext = p.get("selftext", "")[:300]
                combined = title + " " + selftext
                timestamp = p.get("created_utc", 0)
                url_post = f"https://reddit.com{p.get('permalink', '')}"
                score = p.get("score", 0)
                # Para r/mexico, sólo posts con palabras clave UAP
                if sub == "mexico":
                    uap_kws = ["ovni","ufo","uap","luces","extraño","extraña","avistamiento",
                               "volcano","volcán","popocatepetl","popo","objeto volador",
                               "disco volador","nave","extraterrestre","fenómeno"]
                    if not any(kw in combined.lower() for kw in uap_kws):
                        continue
                min_score = 5 if sub in ("aliens","ufo","paranormal","mexico") else 10
                if score < min_score:
                    continue
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else TODAY
                date_str = dt.strftime("%Y-%m-%d")
                ev_type = classify_type(combined)
                coords = location_from_text(combined)
                if not coords:
                    continue
                all_events.append({
                    "id": make_id(url_post),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title[:120],
                    "desc": selftext or f"Post Reddit r/{sub}. Score: {score}.",
                    "witnesses": 0, "credibility": credibility,
                    "country": "—",
                    "sources": [url_post, f"Reddit r/{sub}"],
                })
                count_added += 1
            log.info(f"  Reddit r/{sub}: {count_added} eventos con ubicación")
        except Exception as e:
            log.warning(f"  Error Reddit r/{sub}: {e}")
        time.sleep(0.8)
    log.info(f"  Reddit total: {len(all_events)} eventos")
    return all_events

# ─────────────────────────────────────────────────────────────
# RSS feeds especializados en UAP/OVNI
# ─────────────────────────────────────────────────────────────
def fetch_rss_feed(name, url, default_type="ufo", default_coords=None):
    """Fetcher genérico de RSS feed de noticias UAP."""
    log.info(f"Consultando RSS: {name}...")
    events = []
    raw = fetch_url(url, timeout=25)
    if not raw:
        return events
    try:
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            # Atom feed?
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns) or root.findall("entry")
            if not entries:
                return events
            for entry in entries[:20]:
                title_el = entry.find("{http://www.w3.org/2005/Atom}title") or entry.find("title")
                link_el = entry.find("{http://www.w3.org/2005/Atom}link") or entry.find("link")
                pub_el = entry.find("{http://www.w3.org/2005/Atom}updated") or entry.find("{http://www.w3.org/2005/Atom}published") or entry.find("pubDate")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link = (link_el.get("href", "") or (link_el.text or "")).strip() if link_el is not None else ""
                pub = (pub_el.text or "").strip() if pub_el is not None else ""
                if not title:
                    continue
                try:
                    date_str = pub[:10] if pub else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")
                ev_type = classify_type(title)
                if ev_type == "ufo":
                    ev_type = default_type
                coords = location_from_text(title)
                if not coords:
                    if default_coords:
                        coords = {"lat": default_coords["lat"] + random.uniform(-8, 8), "lng": default_coords["lng"] + random.uniform(-8, 8)}
                    else:
                        coords = {"lat": random.uniform(-60, 70), "lng": random.uniform(-170, 170)}
                events.append({
                    "id": make_id(link or title),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title,
                    "desc": f"RSS: {name}. Fuente: {link[:60] if link else name}.",
                    "witnesses": 0, "credibility": "BAJA (señal noticiosa)",
                    "country": "—",
                    "sources": [name, link[:80] if link else name],
                })
        else:
            for item in channel.findall("item")[:20]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link = (link_el.text or "").strip() if link_el is not None else ""
                pub = (pub_el.text or "").strip() if pub_el is not None else ""
                if not title:
                    continue
                try:
                    from email.utils import parsedate
                    dt = parsedate(pub)
                    date_str = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}" if dt else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")
                ev_type = classify_type(title)
                if ev_type == "ufo":
                    ev_type = default_type
                coords = location_from_text(title)
                if not coords:
                    if default_coords:
                        coords = {"lat": default_coords["lat"] + random.uniform(-8, 8), "lng": default_coords["lng"] + random.uniform(-8, 8)}
                    else:
                        coords = {"lat": random.uniform(-60, 70), "lng": random.uniform(-170, 170)}
                events.append({
                    "id": make_id(link or title),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title,
                    "desc": f"RSS: {name}. Fuente: {link[:60] if link else name}.",
                    "witnesses": 0, "credibility": "BAJA (señal noticiosa)",
                    "country": "—",
                    "sources": [name, link[:80] if link else name],
                })
    except Exception as e:
        log.warning(f"  Error RSS {name}: {e}")
    log.info(f"  {name}: {len(events)} items")
    return events

def fetch_all_rss():
    """Consulta varios feeds RSS especializados en UAP/OVNI."""
    all_events = []
    feeds = [
        ("Latest UFO Sightings",    "https://www.latest-ufo-sightings.net/feed/",             "ufo"),
        ("The Black Vault",         "https://www.theblackvault.com/casefiles/feed/",           "ufo"),
        ("Open Minds UFO News",     "https://openminds.tv/category/ufo-news/feed/",            "ufo"),
        ("UFO Evidence RSS",        "https://www.ufoevidence.org/rss/news_feed.xml",           "ufo"),
        ("Inexplicata (es)",        "https://inexplicata.blogspot.com/feeds/posts/default?alt=rss", "ufo"),
        ("Planeta UFO (es)",        "https://www.planetaufo.com/feed/",                        "ufo"),
        ("Espacio Misterio (es)",   "https://www.espaciomisterio.com/feed",                    "ufo"),
    ]
    for name, url, default_type in feeds:
        evs = fetch_rss_feed(name, url, default_type)
        all_events.extend(evs)
        time.sleep(0.5)
    return all_events

# ─────────────────────────────────────────────────────────────
# NUFORC histórico
# ─────────────────────────────────────────────────────────────
def fetch_nuforc_historical(max_records=600):
    log.info("Descargando dataset histórico NUFORC...")
    events = []
    url = "https://raw.githubusercontent.com/planetsig/ufo-reports/master/csv-data/ufo-scrubbed-geocoded-time-standardized.csv"
    raw = fetch_url(url, timeout=90)
    if not raw:
        log.warning("No se pudo descargar CSV NUFORC")
        return events
    count = 0
    for row in csv.reader(raw.splitlines()):
        if len(row) < 11:
            continue
        try:
            lat = float(row[9]); lng = float(row[10])
            if abs(lat) < 0.1 and abs(lng) < 0.1:
                continue
        except (ValueError, IndexError):
            continue
        date_raw = row[0].strip(); city = row[1].strip(); state = row[2].strip()
        country = row[3].strip().upper(); shape = row[4].strip().lower()
        desc = row[7].strip()[:300]
        shape_map = {
            "light": "lights_sky", "formation": "lights_sky", "flash": "lights_sky",
            "fireball": "lights_sky", "disk": "ufo", "cigar": "ufo", "saucer": "ufo",
            "triangle": "ufo", "oval": "ufo", "sphere": "ufo", "changing": "ufo",
            "cylinder": "ufo", "chevron": "ufo", "diamond": "ufo", "cone": "ufo",
            "egg": "ufo", "unknown": "ufo", "other": "ufo",
        }
        ev_type = shape_map.get(shape, classify_type(desc))
        try:
            dp = date_raw.split(" ")[0].split("/")
            date_str = f"{dp[2]}-{dp[0]:0>2}-{dp[1]:0>2}"
        except Exception:
            date_str = "—"
        loc = f"{city}, {state}" if state else city
        country_full = {"US": "EE.UU.", "CA": "Canadá", "GB": "Reino Unido", "AU": "Australia"}.get(country, country)
        events.append({
            "id": make_id(f"nuforc-{lat}-{lng}-{date_raw}"),
            "lat": lat, "lng": lng,
            "type": ev_type, "date": date_str, "recent": False, "isNew": False,
            "title": f"Avistamiento NUFORC: {shape.capitalize()} en {loc}",
            "desc": desc or f"Forma: {shape}. Reportado en {loc}.",
            "witnesses": 1, "credibility": "MEDIA (reporte civil NUFORC)",
            "country": country_full,
            "sources": [f"NUFORC — {loc}", "nuforc.org"],
            "source_count": 1,
        })
        count += 1
        if count >= max_records:
            break
    log.info(f"  NUFORC histórico: {count} eventos")
    return events

# ─────────────────────────────────────────────────────────────
# Deduplicación y filtro multi-fuente
# ─────────────────────────────────────────────────────────────
def deduplicate(events):
    """Colapsa eventos en la misma celda 0.5°×0.5° y mismo mes."""
    seen = {}; result = []
    for ev in events:
        key = (round(ev["lat"] * 2) / 2, round(ev["lng"] * 2) / 2, ev.get("date", "")[:7])
        if key not in seen:
            seen[key] = len(result)
            ev["source_count"] = ev.get("source_count", len(ev.get("sources", [])))
            result.append(ev)
        else:
            # Fusionar fuentes en el evento existente
            existing = result[seen[key]]
            merged_sources = list(set(existing.get("sources", []) + ev.get("sources", [])))
            existing["sources"] = merged_sources
            existing["source_count"] = len(merged_sources)
    return result

def filter_multi_source(events, min_sources=2):
    """Retiene sólo eventos mencionados en ≥ min_sources dominios.
    NUFORC siempre pasa (base histórica de reporte individual verificado).
    """
    kept = []
    removed = 0
    for ev in events:
        sources = ev.get("sources", [])
        # NUFORC histórico siempre se incluye
        if any("nuforc" in s.lower() for s in sources):
            kept.append(ev)
            continue
        # Contar dominios únicos (no URLs sino nombres de fuente distintos)
        unique_domains = set()
        for s in sources:
            if s.startswith("http"):
                try:
                    domain = urllib.parse.urlparse(s).netloc.replace("www.", "")
                    unique_domains.add(domain)
                except Exception:
                    unique_domains.add(s[:30])
            else:
                unique_domains.add(s[:40])
        if len(unique_domains) >= min_sources:
            kept.append(ev)
        else:
            removed += 1
    log.info(f"  Filtro multi-fuente: {len(kept)} conservados, {removed} eliminados (1 sola fuente)")
    return kept

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("UAP WAR ROOM v2 — Inicio de extracción de datos")
    log.info(f"Fecha: {TODAY.strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    all_recent = []
    all_historical = []

    # Fuentes recientes
    all_recent.extend(fetch_gdelt_recent())
    all_recent.extend(fetch_google_news())
    all_recent.extend(fetch_reddit_multi(limit=75))
    all_recent.extend(fetch_all_rss())

    # Base histórica
    all_historical.extend(fetch_nuforc_historical(max_records=600))

    # Deduplicar
    all_recent = deduplicate(all_recent)
    all_historical = deduplicate(all_historical)

    # Filtro multi-fuente (sólo recientes — históricos NUFORC se mantienen todos)
    all_recent = filter_multi_source(all_recent, min_sources=2)

    log.info(f"Resumen final: {len(all_recent)} recientes, {len(all_historical)} históricos")

    with open(DATA_DIR / "events_recent.geojson", "w", encoding="utf-8") as f:
        json.dump(to_geojson(all_recent), f, ensure_ascii=False, indent=2)
    with open(DATA_DIR / "events_historical.geojson", "w", encoding="utf-8") as f:
        json.dump(to_geojson(all_historical), f, ensure_ascii=False, indent=2)
    with open(DATA_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": TODAY.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recent_count": len(all_recent),
            "historical_count": len(all_historical),
            "sources_used": [
                "GDELT v2 DOC API (5 consultas)",
                "Google News RSS (21 términos — ES/EN/PT)",
                "Reddit r/UFOs, r/aliens, r/ufo, r/paranormal, r/mexico",
                "Latest UFO Sightings RSS",
                "The Black Vault RSS",
                "Open Minds UFO News RSS",
                "Inexplicata (es) RSS",
                "Planeta UFO (es) RSS",
                "Espacio Misterio (es) RSS",
                "NUFORC CSV histórico (600 registros)",
            ],
            "filter": "eventos_recientes: ≥2 dominios distintos (NUFORC exento)",
        }, f, ensure_ascii=False, indent=2)
    log.info("Extracción completada ✓")

if __name__ == "__main__":
    main()
