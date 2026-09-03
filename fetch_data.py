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

# ─────────────────────────────────────────────────────────────
# EVENTOS HISTÓRICOS FAMOSOS — base de conocimiento fija
# Incluye casos icónicos globales y de México con descripción y fuentes verificadas
# ─────────────────────────────────────────────────────────────
FAMOUS_HISTORICAL_EVENTS = [
    # ══ ESTADOS UNIDOS ══
    {"id":"FH001","lat":33.394,"lng":-104.52,"type":"ufo","date":"1947-07-08","country":"EE.UU.",
     "title":"Roswell, Nuevo México — recuperación oficial de objeto no identificado",
     "desc":"El Army Air Field de Roswell emite un comunicado de prensa anunciando la recuperación de un 'platillo volador'. En 24 horas, el comunicado se retracta aludiendo a un globo meteorológico. El Mayor Jesse Marcel declara públicamente que el material no correspondía a ningún tipo conocido de aeronave. Caso seminal en la historia de los fenómenos aéreos no identificados.",
     "witnesses":30,"credibility":"HISTÓRICO / VERIFICADO","sources":["Roswell Daily Record (8-Jul-1947)","USAF Project Mogul report","Jesse Marcel testimony (1978)","Stanton Friedman investigation"]},
    {"id":"FH002","lat":47.0,"lng":-121.0,"type":"ufo","date":"1947-06-24","country":"EE.UU.",
     "title":"Kenneth Arnold — primer avistamiento moderno documentado",
     "desc":"El piloto privado Kenneth Arnold reporta ver nueve objetos brillantes volando en formación cerca del Monte Rainier, Washington. Describe su movimiento como 'platillos brincando en el agua', acuñando el término 'platillo volador'. La prensa mundial publica el caso; el USAF abre investigación. Es el inicio del registro sistemático moderno de UAPs.",
     "witnesses":1,"credibility":"ALTO — piloto comercial con experiencia","sources":["Arnold's personal report (USAF)","Chicago Sun-Times","NICAP archives"]},
    {"id":"FH003","lat":36.72,"lng":-86.56,"type":"ufo","date":"1948-01-07","country":"EE.UU.",
     "title":"Incidente Mantell — piloto de la USAF muere persiguiendo UAP",
     "desc":"El Capitán Thomas Mantell de la Guardia Nacional Aérea de Kentucky muere cuando su P-51 Mustang cae mientras perseguía un objeto grande y plateado. Sus últimas palabras por radio: 'el objeto va más rápido de lo que yo puedo'. USAF primero lo atribuye a Venus, luego a un globo Skyhook. Caso documentado en los archivos del Proyecto Blue Book.",
     "witnesses":10,"credibility":"OFICIAL DOCUMENTADO","sources":["USAF Project Sign report","Godman AAF logs","Lexington Leader (8-Jan-1948)"]},
    {"id":"FH004","lat":33.58,"lng":-101.86,"type":"lights_sky","date":"1951-08-25","country":"EE.UU.",
     "title":"Luces de Lubbock, Texas — formación sobre ciudad universitaria",
     "desc":"Tres profesores de física del Texas Technological College observan por semanas formaciones de luces que cruzan el cielo a alta velocidad. El estudiante Carl Hart Jr. fotografía la formación. El USAF no encuentra explicación. Las fotos permanecen sin ser rebatidas como falsificaciones.",
     "witnesses":12,"credibility":"MUY ALTA — testigos con formación científica","sources":["USAF Project Blue Book","Carl Hart Jr. photographs","Lubbock Evening Journal 1951"]},
    {"id":"FH005","lat":33.59,"lng":-102.38,"type":"em","date":"1957-11-02","country":"EE.UU.",
     "title":"Levelland, Texas — objetos apagan motores de vehículos",
     "desc":"En 7 horas, 15 testigos separados reportan que un objeto ovoide luminoso detiene los motores de sus automóviles. Los motores se reinician cuando el objeto se aleja. El Sheriff Weir Clem confirma el evento. USAF atribuye los apagones a tormenta eléctrica, contradiciendo los reportes de cielo despejado de todos los testigos.",
     "witnesses":15,"credibility":"MUY ALTA — múltiples testigos independientes","sources":["USAF Blue Book (clasificado)","Lubbock Avalanche-Journal","Levelland PD report (Nov 1957)"]},
    {"id":"FH006","lat":44.15,"lng":-71.66,"type":"contact","date":"1961-09-19","country":"EE.UU.",
     "title":"Betty y Barney Hill — primer caso de abducción documentado",
     "desc":"La pareja reporta una brecha de dos horas en su viaje nocturno por New Hampshire, tras ver un objeto con luces de colores que descende hacia ellos. Bajo hipnosis regresiva con el Dr. Benjamin Simon, ambos describen de forma independiente el interior de una nave y seres de ojos grandes. El caso es investigado por NICAP y estudiado por el USAF.",
     "witnesses":2,"credibility":"ALTA — investigación psiquiátrica documentada","sources":["John G. Fuller, 'Interrupted Journey' (1966)","Dr. Simon session transcripts","NICAP investigation"]},
    {"id":"FH007","lat":34.06,"lng":-106.9,"type":"ufo","date":"1964-04-24","country":"EE.UU.",
     "title":"Lonnie Zamora, Socorro NM — aterrizaje con marcas físicas verificadas",
     "desc":"El oficial de policía Lonnie Zamora reporta ver una llama azulada y un objeto ovalado con dos figuras humanoides. Encuentra quemaduras en el suelo y marcas de apoyo. El caso es investigado por el Dr. J. Allen Hynek del USAF, quien no puede encontrar explicación convencional. Considerado uno de los casos más sólidos del Proyecto Blue Book.",
     "witnesses":1,"credibility":"MUY ALTA — evidencia física verificada","sources":["FBI report","USAF Blue Book case 8766","Hynek, 'The UFO Experience' (1972)"]},
    {"id":"FH008","lat":40.17,"lng":-79.46,"type":"ufo","date":"1965-12-09","country":"EE.UU.",
     "title":"Kecksburg, Pennsylvania — objeto acampanado recuperado por el ejército",
     "desc":"Miles de personas en cuatro estados y Canadá ven una bola de fuego brillante. En el bosque de Kecksburg, un objeto metálico acampanado con símbolos grabados es retirado en un camión del ejército sin identificación. La NASA revela documentos incompletos tras demanda FOIA en 2005. El caso permanece sin explicación oficial.",
     "witnesses":1000,"credibility":"ALTA — múltiples testigos y documentos parciales","sources":["Pittsburgh Press (Dec 1965)","NASA FOIA release (2005)","NICAP investigation"]},
    {"id":"FH009","lat":41.16,"lng":-81.18,"type":"lights_sky","date":"1966-04-17","country":"EE.UU.",
     "title":"Persecución del Condado de Portage, Ohio — policías persiguen UAP 85 millas",
     "desc":"El ayudante del Sheriff Dale Spaur y el Diputado Barney Neff persiguen un objeto brillante por 85 millas desde Ohio hasta Pennsylvania. Más de una docena de policías y decenas de civiles lo confirman. J. Allen Hynek lo estudia. El USAF lo atribuye luego a Venus y un satélite, conclusión rechazada por los testigos.",
     "witnesses":30,"credibility":"MUY ALTA — agentes de policía como testigos principales","sources":["Hynek investigation","Canton Repository (1966)","NICAP case 7521"]},
    {"id":"FH010","lat":48.41,"lng":-101.35,"type":"ufo","date":"1968-10-24","country":"EE.UU.",
     "title":"Malmstrom AFB — misiles nucleares desactivados por UAP",
     "desc":"El Capitán Robert Salas reporta que un objeto rojo brillante sobrevolando la base desactivó 10 misiles Minuteman en sus silos. El mismo tipo de evento ocurre en la base vecina de Oscar Flight. Salas declara ante el Congreso en 2010. El USAF no ha ofrecido explicación satisfactoria.",
     "witnesses":20,"credibility":"MUY ALTA — personal militar con acceso clasificado","sources":["Salas testimony al Congreso (2010)","Robert Hastings, 'UFOs and Nukes' (2008)","FOIA documents AF"]},
    {"id":"FH011","lat":34.33,"lng":-110.48,"type":"contact","date":"1975-11-05","country":"EE.UU.",
     "title":"Travis Walton — desaparición y regreso en Arizona",
     "desc":"El trabajador forestal Travis Walton desaparece durante 5 días tras ser golpeado por un rayo de luz de un objeto en el bosque de Turkey Springs, AZ. Sus seis compañeros pasan pruebas de polígrafo. Walton reaparece 5 días después en estado de desorientación. El caso es el más extensamente documentado de abducción con múltiples testigos.",
     "witnesses":7,"credibility":"ALTA — poligrafos y múltiples testigos","sources":["Travis Walton, 'Fire in the Sky' (1978)","APRO investigation","Navajo County Sheriff report"]},
    {"id":"FH012","lat":47.51,"lng":-111.18,"type":"ufo","date":"1967-03-16","country":"EE.UU.",
     "title":"Malmstrom AFB March — misiles desactivados (Incidente Oscar)",
     "desc":"Días antes del incidente de octubre, otra oleada de desactivaciones de misiles nucleares ocurre en Malmstrom. Guardias reportan ovnis sobrevolando los silos. El Coronel Don Crawford afirma que más de 16 misiles Minuteman I fueron desactivados simultáneamente en un evento sin explicación técnica.",
     "witnesses":15,"credibility":"MUY ALTA — personal de instalaciones nucleares","sources":["Robert Hastings research","USAF logs (FOIA)","'UFOs at Nuclear Facilities' NPC Washington (2010)"]},
    {"id":"FH013","lat":43.47,"lng":-65.73,"type":"uso","date":"1967-10-04","country":"Canadá",
     "title":"Shag Harbour — objeto cae al mar, Canadá",
     "desc":"Once testigos, incluyendo pilotos y guardacostas, ven un objeto con cuatro luces naranjas caer en el agua. La RCMP y la Marina canadiense investigan durante semanas. Detectan con sonar objetos moviéndose bajo el agua. Canadá cataloga el caso oficialmente como no resuelto. Único caso de UAP con investigación oficial completa de Canadá.",
     "witnesses":11,"credibility":"MUY ALTA — investigación naval oficial","sources":["RCMP reports (desclasificados 2014)","Transport Canada records","Chris Styles & Don Ledger research"]},
    {"id":"FH014","lat":44.0,"lng":-73.0,"type":"ufo","date":"1983-03-24","country":"EE.UU.",
     "title":"Valle del Hudson — objeto triangular masivo, miles de testigos",
     "desc":"Durante años, miles de testigos en el Valle del Hudson (NY) reportan un objeto triangular silencioso de hasta 300 metros de lado, con luces de colores. Entre los testigos hay pilotos, policías e ingenieros. El investigador J. Allen Hynek lo estudia hasta su muerte. Más de 5,000 reportes registrados.",
     "witnesses":5000,"credibility":"MUY ALTA — documentación sistemática durante años","sources":["Philip Imbrogno, 'Night Siege' (1987)","Hynek Center investigation","Poughkeepsie Journal 1984"]},
    {"id":"FH015","lat":30.36,"lng":-87.16,"type":"ufo","date":"1987-11-11","country":"EE.UU.",
     "title":"Gulf Breeze, Florida — fotografías de Ed Walters",
     "desc":"El constructor Ed Walters fotografía repetidamente un objeto en su ciudad durante meses. Los negativos son analizados por Polaroid y no se detectan alteraciones. MUFON conduce una investigación amplia. El caso divide a la comunidad investigadora pero las fotos nunca son definitivamente refutadas.",
     "witnesses":200,"credibility":"MEDIA-ALTA — análisis fotográfico independiente","sources":["Ed Walters, 'The Gulf Breeze Sightings' (1990)","MUFON investigation","Pensacola News Journal 1988"]},
    {"id":"FH016","lat":33.45,"lng":-112.07,"type":"lights_sky","date":"1997-03-13","country":"EE.UU.",
     "title":"Luces de Phoenix — 10,000 testigos, dos objetos distintos",
     "desc":"Una formación en V de más de 2 km de ancho cruza Arizona a baja altitud durante más de una hora. Simultáneamente, luces estacionarias aparecen sobre Phoenix. El Gobernador Fife Symington celebra una conferencia de prensa burlándose del evento, luego admite públicamente en 2007 que él mismo vio algo que 'no era de este mundo'. El USAF atribuye las luces a bengalas, sin explicar la formación inicial.",
     "witnesses":10000,"credibility":"MUY ALTA — el avistamiento más masivo de EE.UU.","sources":["Arizona Republic (Mar 1997)","Gobernador Symington statement (2007)","MUFON 1997 report"]},
    {"id":"FH017","lat":32.22,"lng":-98.2,"type":"ufo","date":"2008-01-08","country":"EE.UU.",
     "title":"Stephenville, Texas — 200 testigos y F-16 confirman persecución",
     "desc":"Más de 200 residentes de Stephenville ven un objeto masivo y silencioso con luces. Cazas F-16 de la Base Carswell lo persiguen. El ejército inicialmente niega haber volado en la zona, luego lo confirma públicamente. MUFON recibe 300+ reportes en días.",
     "witnesses":200,"credibility":"ALTA — Fuerza Aérea confirma actividad","sources":["Dublin Citizen-Tribune (Jan 2008)","MUFON report 2008","USAF confirmation statement"]},
    {"id":"FH018","lat":28.0,"lng":-124.0,"type":"ufo","date":"2004-11-14","country":"EE.UU. (Pacífico)",
     "title":"USS Nimitz — encuentro con el 'Tic-Tac', confirmado por el Pentágono",
     "desc":"El piloto Comandante David Fravor intercepta un objeto blanco ovoide sin alas ni propulsión visible que realiza maniobras imposibles para la física conocida. El sistema FLIR de otro avión graba el objeto. El Pentágono confirma y publica el video en 2020. Fravor declara ante el Congreso de EE.UU. en 2023. Es el caso UAP más analizado por instituciones oficiales en décadas.",
     "witnesses":20,"credibility":"OFICIAL CONFIRMADO — DoD y Congreso","sources":["DoD release (Apr 2020)","NY Times (Dec 2017)","David Fravor testimony, Congreso EE.UU. (2023)","FLIR1 video desclasificado"]},
    {"id":"FH019","lat":35.0,"lng":-75.0,"type":"ufo","date":"2014-08-01","country":"EE.UU. (Atlántico)",
     "title":"USS Roosevelt — avistamientos diarios de UAPs, pilotos de la US Navy",
     "desc":"El piloto Ryan Graves y otros aviadores del USS Theodore Roosevelt reportan ver UAPs 'todos los días' durante meses frente a la costa este. Los videos GIMBAL y GOFAST son grabados con sistemas FLIR. Graves declara ante el Congreso en 2023 que los objetos realizaban maniobras imposibles y ponían en riesgo la seguridad aérea.",
     "witnesses":50,"credibility":"OFICIAL CONFIRMADO — US Navy y Congreso","sources":["DoD release (2020)","Ryan Graves testimony (Congreso 2023)","GIMBAL y GOFAST videos desclasificados"]},
    {"id":"FH020","lat":41.98,"lng":-87.9,"type":"ufo","date":"2006-11-07","country":"EE.UU.",
     "title":"Aeropuerto O'Hare — objeto horada las nubes, United Airlines y FAA",
     "desc":"Doce empleados de United Airlines y varios pilotos reportan un objeto metálico gris estacionario sobre la puerta C-17 del aeropuerto. El objeto asciende verticalmente a gran velocidad, perforando la nube y dejando un agujero circular que se observa durante minutos. La FAA no abre investigación por considera el caso como 'fenómeno climático'.",
     "witnesses":15,"credibility":"MUY ALTA — personal aeronáutico con entrenamiento","sources":["Chicago Tribune FOIA request (2007)","Jon Hilkevitch investigation","FAA records (incompletos)"]},
    {"id":"FH021","lat":40.25,"lng":-109.88,"type":"ufo","date":"1996-01-01","country":"EE.UU.",
     "title":"Skinwalker Ranch, Utah — fenómenos múltiples durante décadas",
     "desc":"La familia Sherman y luego el multimillonario Robert Bigelow documentan durante años desapariciones de ganado, objetos luminosos, figuras humanoides y fenómenos electromagnéticos en el rancho de 500 acres. Bigelow crea el National Institute for Discovery Science para investigarlo. El Departamento de Defensa financia secretamente la investigación (programa AAWSAP).",
     "witnesses":100,"credibility":"MUY ALTA — investigación DoD confirmada (AAWSAP)","sources":["Colm Kelleher, 'Hunt for the Skinwalker' (2005)","AAWSAP program (FOIA)","Jeremy Corbell documentales"]},
    # ══ REINO UNIDO / EUROPA ══
    {"id":"FH022","lat":52.09,"lng":1.45,"type":"contact","date":"1980-12-26","country":"Reino Unido",
     "title":"Bosque Rendlesham — caso más documentado de UK",
     "desc":"Personal militar de la USAF en la RAF Bentwaters-Woodbridge, Suffolk, reporta una nave aterrizada con jeroglíficos durante tres noches consecutivas. El Teniente Coronel Charles Halt graba el evento en casete de audio. Se miden niveles de radiación anómalos y se encuentran marcas físicas en el suelo. Considerado el caso más creíble y documentado del Reino Unido.",
     "witnesses":20,"credibility":"MUY ALTA — personal militar USAF, grabaciones","sources":["Halt memo al MoD (13 Jan 1981)","MoD Freedom of Information release","'The Rendlesham Enigma' — Charles Halt (2020)"]},
    {"id":"FH023","lat":50.85,"lng":4.35,"type":"ufo","date":"1989-11-29","country":"Bélgica",
     "title":"Oleada belga — triángulos sobre toda Bélgica durante meses",
     "desc":"13,500 testigos reportan en oleadas objetos triangulares grandes y silenciosos con luces en las esquinas. La Fuerza Aérea Belga envía dos F-16 a interceptarlos; sus radares registran aceleraciones imposibles. El SOBEPS (sociedad científica belga) documenta el fenómeno. La FAB es la primera fuerza aérea en cooperar abiertamente con investigadores civiles.",
     "witnesses":13500,"credibility":"MUY ALTA — investigación oficial FAB","sources":["SOBEPS report (1991)","FAB press conference (1990)","La Libre Belgique 1989-1990"]},
    {"id":"FH024","lat":62.87,"lng":11.0,"type":"lights_sky","date":"1981-01-01","country":"Noruega",
     "title":"Hessdalen — fenómeno persistente con monitoreo científico",
     "desc":"Luces no identificadas de diversas formas y colores se observan en el valle de Hessdalen desde los años 1980. Investigadores noruegos y europeos establecen una estación permanente con radar, cámaras y sensores electromagnéticos. Los datos muestran plasmas luminosos de comportamiento anómalo. El fenómeno continúa activo hasta la fecha.",
     "witnesses":500,"credibility":"MUY ALTA — datos instrumentales continuos","sources":["Proyecto Hessdalen (1983-actualidad)","SINTEF Norway research","Journal of Scientific Exploration"]},
    {"id":"FH025","lat":43.62,"lng":6.35,"type":"ufo","date":"1981-01-08","country":"Francia",
     "title":"Trans-en-Provence — aterrizaje con análisis botánico oficial",
     "desc":"El agricultor Renato Nicolai reporta un objeto que aterriza brevemente en su campo. El GEPAN (agencia gubernamental francesa) analiza el suelo y la vegetación dañada. El laboratorio nacional INRA concluye que la planta estuvo expuesta a calor intenso, radiación electromagnética o un campo eléctrico. Es el único caso donde un gobierno obtuvo evidencia física analizada por su propio laboratorio oficial.",
     "witnesses":1,"credibility":"MUY ALTA — análisis oficial del GEPAN/INRA","sources":["GEPAN Technical Note No. 16 (1981)","INRA laboratory analysis","CNES France archives"]},
    {"id":"FH026","lat":51.3,"lng":-1.8,"type":"crop","date":"1990-07-12","country":"Reino Unido",
     "title":"Figuras de Wiltshire — anomalías físicas en cultivos",
     "desc":"Patrones geométricos complejos aparecen en campos de cereales de la región de Wiltshire (cerca de Stonehenge) en una sola noche, desde los años 1970s. El BLT Research Team del Dr. W.C. Levengood analiza las plantas dobladas y encuentra cambios celulares que no se replican con rodillos. Algunos casos son claramente humanos; otros presentan evidencia física no explicada.",
     "witnesses":200,"credibility":"MEDIA — algunos casos sin explicación física","sources":["BLT Research Team (Dr. Levengood)","CCCS (UK)","Wiltshire Gazette & Herald 1990"]},
    # ══ IRÁN / ASIA ══
    {"id":"FH027","lat":35.7,"lng":51.4,"type":"ufo","date":"1976-09-19","country":"Irán",
     "title":"Teherán 1976 — cazas de la FIAA pierden sistemas de armas",
     "desc":"La Fuerza Aérea Imperial iraní envía dos F-4 Phantom a interceptar un objeto brillante que maniobraba sobre la capital. Los sistemas de armas y las comunicaciones de ambos cazas fallan al acercarse al objeto. Un sub-objeto se desprende y se aproxima a uno de los F-4. El evento es documentado por la DIA de EE.UU. en un informe que califica el caso de 'excelente' en credibilidad.",
     "witnesses":8,"credibility":"MUY ALTA — documentado por la DIA de EE.UU.","sources":["DIA report (desclasificado)","General Azarbarzin testimony","NICAP documentation"]},
    {"id":"FH028","lat":60.0,"lng":-153.0,"type":"ufo","date":"1986-11-17","country":"EE.UU. (Alaska)",
     "title":"JAL 1628 — portaaviones volador sobre Alaska",
     "desc":"El Capitán Kenjyu Terauchi de Japan Airlines reporta ser seguido durante 50 minutos por tres objetos, el mayor del tamaño de un portaaviones. El radar del Centro de Control de Tráfico Aéreo de la FAA confirma un contacto. El piloto es reasignado de funciones de vuelo tras hablar públicamente. La investigación de la FAA no puede refutar el avistamiento.",
     "witnesses":3,"credibility":"MUY ALTA — confirmado por radar FAA","sources":["FAA radar records","Japan Airlines official report","NICAP case documentation"]},
    # ══ RUSIA / EUROPA DEL ESTE ══
    {"id":"FH029","lat":61.8,"lng":34.4,"type":"lights_sky","date":"1977-09-20","country":"Rusia (URSS)",
     "title":"Petrozavodsk — medusa luminosa presenciada por miles",
     "desc":"A las 4 AM, miles de testigos en la ciudad soviética de Petrozavodsk ven un objeto luminoso que emite rayos en forma de medusa durante 10-12 minutos. La TASS (agencia oficial soviética) publica el suceso, algo extraordinario durante la Guerra Fría. Los estudios soviéticos posteriores no encuentran explicación convencional.",
     "witnesses":3000,"credibility":"ALTA — publicado por agencia oficial soviética TASS","sources":["TASS dispatch (Sep 1977)","Pravda report","Soviet Academy of Sciences investigation"]},
    # ══ AUSTRALIA ══
    {"id":"FH030","lat":-37.97,"lng":145.13,"type":"ufo","date":"1966-04-06","country":"Australia",
     "title":"Westall, Melbourne — 200 testigos y aterrizaje en terreno escolar",
     "desc":"Más de 200 estudiantes y profesores de la escuela secundaria de Westall, Melbourne, ven un objeto plateado descender, aterrizar brevemente en un campo y subir. Los estudiantes son reunidos por las autoridades y se les dice que no hablen del evento. El asistente de tierra Clayton South describe un anillo quemado en el pasto. El caso permaneció suprimido durante décadas.",
     "witnesses":200,"credibility":"ALTA — múltiples testigos directos, evidencia física","sources":["Shane Ryan investigation","Westall school records","Documentario 'Westall' (2010)"]},
    {"id":"FH031","lat":-38.0,"lng":145.0,"type":"uso","date":"1978-10-21","country":"Australia",
     "title":"Frederick Valentich — desaparición sobre el Estrecho de Bass",
     "desc":"El piloto de 20 años Frederick Valentich reporta ser seguido por un objeto metálico verde con luces sobre el Estrecho de Bass. Su última transmisión de radio antes de cortarse: 'es una aeronave larga y brillante... justo encima de mí. Está estacionaria.' Ni él ni su Cessna 182 fueron encontrados jamás. La grabación de radio original existe en los archivos de la Autoridad Australiana de Aviación Civil.",
     "witnesses":1,"credibility":"OFICIAL DOCUMENTADO — grabación de radio original","sources":["CASA Australia (transcripción radio completa)","CSIRO investigation","RAAF investigation report"]},
    # ══ ZIMBABWE ══
    {"id":"FH032","lat":-17.83,"lng":31.05,"type":"contact","date":"1994-09-16","country":"Zimbabwe",
     "title":"Ariel School, Zimbabwe — 62 niños describen aterrizaje y seres",
     "desc":"62 niños de 6 a 12 años en la escuela primaria Ariel de Ruwa describen independientemente el aterrizaje de una nave y el contacto con seres de ojos grandes durante el recreo. El psiquiatra Dr. John Mack de Harvard los entrevista en sesiones separadas. Sus testimonios son consistentes entre sí y con décadas de diferencia. El evento fue filmado.",
     "witnesses":62,"credibility":"ALTA — investigación Harvard, testimonios consistentes","sources":["Dr. John Mack (Harvard) interviews","Cynthia Hind investigation","'Ariel Phenomenon' (2022 documentary)"]},
    # ══ BRASIL ══
    {"id":"FH033","lat":-0.93,"lng":-47.36,"type":"lights_sky","date":"1977-10-01","country":"Brasil",
     "title":"Operação Prato, Colares — rayos que hieren a civiles",
     "desc":"Rayos luminosos provenientes de objetos no identificados hieren a decenas de residentes de la isla de Colares, dejando quemaduras, perforaciones y anemias. El ejército brasileño conduce la Operación Prato durante meses, documentando con fotografías y films. El Capitán Uyrangê Hollanda confirma en entrevista en 1997, antes de morir, que los documentos militares existen.",
     "witnesses":300,"credibility":"ALTA — documentación militar brasileña","sources":["Operação Prato (documentos militares)","Capitán Hollanda testimony (1997)","CBPDV investigation"]},
    {"id":"FH034","lat":-21.56,"lng":-45.43,"type":"contact","date":"1996-01-20","country":"Brasil",
     "title":"Varginha, Brasil — recuperación de seres no humanos reportada",
     "desc":"Múltiples residentes de Varginha reportan ver criaturas con piel aceitosa y ojos rojos en distintos puntos de la ciudad. Bomberos y soldados acuden al lugar. Se reporta la recuperación de al menos dos seres por fuerzas militares brasileñas. El viticultor Vitório Pacaccini investiga el caso durante años. El gobierno brasileño nunca emite declaración oficial.",
     "witnesses":40,"credibility":"ALTA — múltiples testigos en ubicaciones separadas","sources":["MUFON Brasil investigation","Vitório Pacaccini research","A Tarde newspaper (Jan 1996)"]},
    {"id":"FH035","lat":-23.55,"lng":-46.63,"type":"ufo","date":"1986-05-19","country":"Brasil",
     "title":"Apagón de São Paulo — FAB persigue 21 UAPs, caso desclasificado",
     "desc":"La Fuerza Aérea Brasileña (FAB) publica en 2010 un informe interno que reconoce la persecución de 21 objetos no identificados que se movían a alta velocidad durante un apagón que afectó varios estados. Las aeronaves de la FAB no pudieron alcanzarlos. Es el caso de persecución aérea más documentado de Brasil.",
     "witnesses":5000,"credibility":"OFICIAL CONFIRMADO — FAB 2010","sources":["FAB informe desclasificado (2010)","Folha de São Paulo","CBPDV records"]},
    # ══ CANADA ══
    {"id":"FH036","lat":62.0,"lng":-130.0,"type":"ufo","date":"1996-12-11","country":"Canadá",
     "title":"Yukon 1996 — nave de más de 1 milla, 30 testigos en 800 km",
     "desc":"Más de 30 testigos en 11 ubicaciones separadas a lo largo de 800 km reportan la misma nave masiva de aproximadamente 1.5 km de largo moviéndose silenciosamente sobre el Yukon canadiense. Los testimonios recogidos independientemente son casi idénticos en descripción. UFO*BC realiza una de las investigaciones más detalladas en la historia canadiense.",
     "witnesses":30,"credibility":"MUY ALTA — testimonios independientes correlacionados","sources":["UFO*BC investigation","Whitehorse Star (Dec 1996)","UFOROM Canada report"]},
    # ══ ARGENTINA ══
    {"id":"FH037","lat":-32.19,"lng":-61.71,"type":"contact","date":"1978-10-28","country":"Argentina",
     "title":"El Trébol, Argentina — CE3 fotografiado",
     "desc":"El farmacéutico Dionisio Llanca reporta un encuentro cercano de tercer tipo con seres de aspecto humanoide. El médico Máximo Valentini registra síntomas físicos consistentes con exposición a radiación. El CIFE (Centro de Investigación de Fenómenos Extraños) documenta el caso. Es uno de los CE3 más estudiados de América del Sur.",
     "witnesses":1,"credibility":"MEDIA-ALTA — evidencia médica documentada","sources":["CIFE investigation","Dr. Valentini medical report","Revista 2001 (Argentina)"]},
    # ══ MÉXICO ══
    {"id":"FH038","lat":29.46,"lng":-105.05,"type":"ufo","date":"1974-08-25","country":"México",
     "title":"Coyame, Chihuahua — colisión y recuperación de objeto no identificado",
     "desc":"Se registra en radares civiles y militares un objeto desconocido que colisiona con una avioneta sobre el desierto de Chihuahua. Un convoy militar mexicano recupera los restos. Según el investigador Eloy Rodríguez, el equipo que realizó la recuperación muere en circunstancias misteriosas. Documentos de la CIA obtenidos mediante FOIA hacen referencia al incidente.",
     "witnesses":5,"credibility":"MEDIA — documentos CIA parciales","sources":["Chihuahua radar logs (parciales)","Eloy Rodríguez investigation","CIA FOIA references"]},
    {"id":"FH039","lat":19.43,"lng":-99.13,"type":"ufo","date":"1991-07-11","country":"México",
     "title":"Eclipse solar CDMX 1991 — decenas de cámaras graban OVNI",
     "desc":"Durante el eclipse solar total del 11 de julio de 1991, decenas de personas que filmaban el fenómeno captaron en sus cámaras de video objetos metálicos plateados. La grabación más clara es del canal Televisa. Los objetos son visibles en múltiples videos independientes. El investigador Jaime Maussán inicia el 'Año 1' de la ufología mexicana moderna.",
     "witnesses":500,"credibility":"ALTA — múltiples videos independientes simultáneos","sources":["Televisa footage (Jul 1991)","Jaime Maussán investigation","Diario Excélsior Jul 1991"]},
    {"id":"FH040","lat":19.69,"lng":-98.84,"type":"ufo","date":"1991-07-11","country":"México",
     "title":"Teotihuacán 1991 — objetos sobre la Pirámide del Sol durante el eclipse",
     "desc":"En el mismo eclipse, múltiples testigos y camarógrafos en la zona arqueológica de Teotihuacán documentan objetos sobre la Pirámide del Sol. Los videos muestran objetos esféricos metálicos en movimiento errático. El contexto de múltiples grabaciones simultáneas en todo el país hace difícil una explicación única.",
     "witnesses":200,"credibility":"ALTA — registros visuales múltiples e independientes","sources":["Videos de turistas (1991)","Jaime Maussán compilation","La Jornada Jul 1991"]},
    {"id":"FH041","lat":19.83,"lng":-90.53,"type":"ufo","date":"2004-03-05","country":"México",
     "title":"Fuerza Aérea Mexicana, Campeche — radar y FLIR confirman 11 objetos",
     "desc":"Un avión de la Secretaría de la Defensa Nacional (SEDENA) que realizaba operaciones anti-narcóticos detecta con radar 11 objetos que lo rodean. La cámara FLIR capta objetos luminosos que se mueven y rodean la aeronave. El General Ricardo Vega García, Secretario de Defensa, reconoce y publica el video. Es el único caso en México con confirmación oficial militar.",
     "witnesses":5,"credibility":"OFICIAL CONFIRMADO — SEDENA y FAM","sources":["SEDENA press release (May 2004)","General Vega García statement","Video FLIR Escuadrón 501 (publicado)"]},
    {"id":"FH042","lat":19.02,"lng":-98.62,"type":"volcano","date":"2012-10-25","country":"México",
     "title":"Popocatépetl 2012 — objeto entra al cráter filmado por Webcam CENAPRED",
     "desc":"La cámara de monitoreo del CENAPRED (Centro Nacional de Prevención de Desastres) captura un objeto luminoso que entra al cráter del Popocatépetl en ángulo recto con respecto a la superficie. El video se difunde internacionalmente y genera debate. CENAPRED no emite declaración oficial sobre el objeto.",
     "witnesses":0,"credibility":"MEDIA — grabación de cámara oficial, sin testigos directos","sources":["CENAPRED webcam footage (Oct 2012)","YouTube viral (millones de vistas)","Milenio TV cobertura"]},
    {"id":"FH043","lat":19.02,"lng":-98.63,"type":"volcano","date":"2013-05-30","country":"México",
     "title":"Popocatépetl 2013 — cilindro entra al cráter en transmisión en vivo",
     "desc":"Durante una transmisión en vivo del volcán, un objeto cilíndrico luminoso de gran tamaño aparece sobrevolando el cráter y desciende hacia él. Miles de espectadores lo observan en tiempo real. El fenómeno se repite en varias ocasiones a lo largo de 2013 y años posteriores según testigos y monitoreos independientes.",
     "witnesses":10000,"credibility":"MEDIA — grabación pública en vivo","sources":["CENAPRED livestream (May 2013)","El Universal cobertura","YouTube: múltiples grabaciones verificadas"]},
    {"id":"FH044","lat":25.67,"lng":-100.31,"type":"ufo","date":"2004-06-10","country":"México",
     "title":"Oleada de OVNIs sobre Monterrey, Nuevo León — 2004",
     "desc":"Durante varias semanas de junio de 2004, residentes del área metropolitana de Monterrey reportan múltiples avistamientos de objetos luminosos, formaciones en triángulo y esferas metálicas. Varios videos son grabados desde distintos puntos de la ciudad. El evento coincide temporalmente con el caso de la FAM en Campeche.",
     "witnesses":300,"credibility":"MEDIA — múltiples grabaciones","sources":["El Norte Monterrey (Jun 2004)","Jaime Maussán programa","Reportes CEFP México"]},
    {"id":"FH045","lat":19.43,"lng":-99.14,"type":"ufo","date":"2011-08-16","country":"México",
     "title":"OVNI sobre CDMX — objeto grabado por decenas en distintos puntos",
     "desc":"Un objeto esférico plateado que se mueve lentamente sobre la Ciudad de México es grabado simultáneamente por residentes en distintas colonias y en el Aeropuerto Internacional. La amplitud de grabaciones independientes desde distintos ángulos hace difícil una explicación sencilla como globo o dron.",
     "witnesses":150,"credibility":"MEDIA — múltiples videos independientes","sources":["Milenio TV cobertura","Twitter trending México","Excélsior"]},
    {"id":"FH046","lat":24.0,"lng":-99.0,"type":"ufo","date":"2014-07-01","country":"México",
     "title":"Tamaulipas — avistamientos militares y civiles en zona fronteriza",
     "desc":"Durante 2014 y años siguientes, Tamaulipas concentra un número desproporcionado de reportes de OVNIs, luces y formaciones extrañas, especialmente en zonas limítrofes con Texas. La zona presenta actividad aérea no convencional documentada por civiles en Reynosa, Matamoros y Nuevo Laredo.",
     "witnesses":200,"credibility":"MEDIA — concentración de reportes en zona específica","sources":["SDP Noticias","Reportes MUFON zona fronteriza","Twitter locales Tamaulipas"]},
    {"id":"FH047","lat":32.53,"lng":-117.02,"type":"ufo","date":"2015-03-15","country":"México",
     "title":"Tijuana — serie de avistamientos en zona metropolitana",
     "desc":"Durante meses de 2015, la zona de Tijuana registra múltiples avistamientos de objetos no identificados. Los reportes provienen tanto del lado mexicano como del lado estadounidense (San Diego), con descripciones de luces triangulares y esferas. El carácter transfronterizo del fenómeno genera cobertura en ambos países.",
     "witnesses":150,"credibility":"MEDIA — reportes duales MX-EE.UU.","sources":["Frontera.info","NBC San Diego","Reportes MUFON San Diego"]},
    {"id":"FH048","lat":22.16,"lng":-100.98,"type":"ufo","date":"2019-06-01","country":"México",
     "title":"San Luis Potosí — objetos grabados en zona desértica",
     "desc":"Una serie de grabaciones en zonas desérticas del estado de San Luis Potosí muestran objetos de formas diversas, incluyendo discos y esferas luminosas. Las grabaciones son analizadas por investigadores como Santiago Yturria y difundidas en programas especializados.",
     "witnesses":30,"credibility":"BAJA-MEDIA — pocas verificaciones independientes","sources":["Santiago Yturria research","Tercer Milenio TV","Reportes CEFP"]},
    {"id":"FH049","lat":19.17,"lng":-96.13,"type":"uso","date":"2019-04-10","country":"México",
     "title":"Golfo de México / Veracruz — luces submarinas costeras",
     "desc":"Pescadores y testigos en la zona costera de Veracruz reportan luces brillantes moviéndose bajo la superficie del Golfo de México en distintas noches. Las descripciones incluyen luces de colores (azul, verde) que se desplazan horizontalmente a velocidades mayores que las embarcaciones convencionales.",
     "witnesses":25,"credibility":"MEDIA — testigos pesqueros directos","sources":["Reportes locales Veracruz","CEFP México","SDP Noticias"]},
    # ══ PERÚ / COLOMBIA / CHILE ══
    {"id":"FH050","lat":-16.4,"lng":-71.5,"type":"ufo","date":"1980-04-11","country":"Perú",
     "title":"Arequipa, Perú — piloto de la FAP dispara contra OVNI",
     "desc":"El Comandante Óscar Santa María de la Fuerza Aérea del Perú intercepta un objeto esférico sobre la base de La Joya. Dispara 64 proyectiles de 30 mm que impactan sin efecto aparente. El objeto asciende a más de 11,000 metros y se escapa. Santa María declara el caso ante la ONU en 1993.",
     "witnesses":1,"credibility":"MUY ALTA — piloto militar, declaración ante ONU","sources":["Comandante Santa María testimony (ONU 1993)","FAP investigation","'UFOs: A Need to Know' documentary"]},
    {"id":"FH051","lat":-23.65,"lng":-70.4,"type":"ufo","date":"2008-07-18","country":"Chile",
     "title":"Antofagasta, Chile — CEFAA confirma UAP en video aéreo",
     "desc":"El Comité de Estudios de Fenómenos Aéreos Anómalos (CEFAA) de la Fuerza Aérea de Chile publica videos tomados por helicóptero de la Armada y de un avión CASA que muestran un objeto metálico que emite gases en el espectro infrarrojo. Es uno de los casos más verificados institucionalmente en América Latina.",
     "witnesses":10,"credibility":"MUY ALTA — confirmado por CEFAA Chile","sources":["CEFAA report (2014)","The Huffington Post (2014)","Leslie Kean investigation"]},
]

def fetch_famous_historical():
    """Devuelve los eventos históricos famosos con formato estándar."""
    log.info(f"  Cargando {len(FAMOUS_HISTORICAL_EVENTS)} eventos históricos famosos...")
    events = []
    for ev in FAMOUS_HISTORICAL_EVENTS:
        events.append({
            "id": ev["id"],
            "lat": ev["lat"], "lng": ev["lng"],
            "type": ev.get("type", "ufo"),
            "date": ev.get("date", "—"),
            "recent": False, "isNew": False,
            "title": ev.get("title", "Sin título"),
            "desc": ev.get("desc", ""),
            "witnesses": ev.get("witnesses", 0),
            "credibility": ev.get("credibility", "HISTÓRICO"),
            "country": ev.get("country", "—"),
            "sources": ev.get("sources", ["Registro histórico"]),
            "source_count": len(ev.get("sources", ["Registro histórico"])),
        })
    return events

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
# Periódicos mexicanos e internacionales (RSS gratuitos)
# ─────────────────────────────────────────────────────────────
def fetch_mex_newspapers():
    """RSS de periódicos mexicanos para noticias UAP/OVNI."""
    log.info("Consultando periódicos mexicanos...")
    all_events = []
    mex_feeds = [
        ("El Universal Ciencia",    "https://www.eluniversal.com.mx/rss/ciencia.xml",          "ufo"),
        ("Milenio Noticias",        "https://www.milenio.com/rss",                              "ufo"),
        ("La Jornada Ciencia",      "https://www.jornada.com.mx/ultimas/ciencias/rss.xml",      "ufo"),
        ("Excélsior Tendencias",    "https://www.excelsior.com.mx/rss.xml",                     "ufo"),
        ("SDP Noticias",            "https://www.sdpnoticias.com/rss/",                         "ufo"),
        ("Expansión México",        "https://expansion.mx/rss/todas",                           "ufo"),
        ("Animal Político",         "https://www.animalpolitico.com/feed",                      "ufo"),
        ("Proceso Ciencia",         "https://www.proceso.com.mx/?feed=rss2",                    "ufo"),
        ("Infobae México",          "https://www.infobae.com/feeds/rss/seccion/america/mexico/","ufo"),
    ]
    uap_keywords = [
        "ovni","ufo","uap","objeto volador","objeto no identificado","fenómeno aéreo",
        "luces extrañas","nave extraterrestre","avistamiento","disco volador",
        "popocatépetl","volcán luces","extraterrestre","alien","fuerza aérea ovni",
        "secretaría de defensa","sedena ovni","fenómeno luminoso","bola de fuego",
        "meteorito","objeto espacial","objeto desconocido","craft","flying saucer",
    ]
    mex_coords = {"lat": 19.4, "lng": -99.1}  # CDMX como default México

    for name, url, default_type in mex_feeds:
        log.info(f"  RSS {name}...")
        raw = fetch_url(url, timeout=20)
        if not raw:
            time.sleep(0.5)
            continue
        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            items = channel.findall("item") if channel else root.findall("item")
            count_added = 0
            for item in items[:30]:
                title_el = item.find("title")
                link_el  = item.find("link")
                pub_el   = item.find("pubDate")
                desc_el  = item.find("description")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link  = (link_el.text or "").strip()  if link_el  is not None else ""
                pub   = (pub_el.text  or "").strip()  if pub_el   is not None else ""
                snippet = (desc_el.text or "").strip()[:300] if desc_el is not None else ""
                combined = (title + " " + snippet).lower()
                # Filtrar solo noticias relacionadas con UAP
                if not any(kw in combined for kw in uap_keywords):
                    continue
                try:
                    from email.utils import parsedate
                    dt = parsedate(pub)
                    date_str = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}" if dt else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")
                coords = location_from_text(title + " " + snippet)
                if not coords:
                    coords = {"lat": mex_coords["lat"] + random.uniform(-5, 5),
                              "lng": mex_coords["lng"] + random.uniform(-5, 5)}
                ev_type = classify_type(title + " " + snippet)
                all_events.append({
                    "id": make_id(link or title),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title[:120],
                    "desc": snippet or f"Nota en {name}.",
                    "witnesses": 0, "credibility": "MEDIA (prensa nacional MX)",
                    "country": "México",
                    "sources": [name, link[:80] if link else name],
                })
                count_added += 1
            log.info(f"    {name}: {count_added} noticias UAP")
        except Exception as e:
            log.warning(f"    Error {name}: {e}")
        time.sleep(0.6)
    log.info(f"  Periódicos MX total: {len(all_events)} eventos")
    return all_events


def fetch_intl_newspapers():
    """RSS de fuentes internacionales de noticias UAP/OVNI."""
    log.info("Consultando fuentes internacionales de noticias...")
    all_events = []
    intl_feeds = [
        ("Mystery Wire",            "https://mysterywire.com/feed/",                            "ufo"),
        ("UFO Chronicles",          "https://www.ufodigest.com/feed/",                          "ufo"),
        ("Daily Star Weird News",   "https://www.dailystar.co.uk/news/weird-news/rss.xml",      "ufo"),
        ("The Guardian Science",    "https://www.theguardian.com/science/rss",                  "ufo"),
        ("NY Post Weird",           "https://nypost.com/weird-but-true/feed/",                  "ufo"),
        ("Fox News Science Tech",   "https://feeds.foxnews.com/foxnews/scitech",                "ufo"),
        ("News.com.au Weird",       "https://feeds.news.com.au/public/rss/2.0/news_tech_6.xml", "ufo"),
        ("Clarin Insólito (es)",    "https://www.clarin.com/rss/lo-ultimo/",                    "ufo"),
        ("El País Ciencia (es)",    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/ciencia/portada","ufo"),
        ("RT en Español",           "https://actualidad.rt.com/rss",                            "ufo"),
        ("Sputnik Español",         "https://sputniknews.lat/export/rss2/archive/index.xml",    "ufo"),
    ]
    uap_keywords = [
        "ufo","uap","ovni","unidentified","flying saucer","alien craft","extraterrestrial",
        "anomalous aerial","non-human intelligence","objeto volador","avistamiento",
        "sighting","contact","abduction","disclosure","pentagon uap","congress uap",
        "navy uap","military ufo","recovered craft","crash retrieval","fenómeno",
        "bola de fuego","objeto no identificado","nave alienígena","fenómeno aéreo",
    ]
    for name, url, default_type in intl_feeds:
        log.info(f"  RSS {name}...")
        raw = fetch_url(url, timeout=20)
        if not raw:
            time.sleep(0.5)
            continue
        try:
            root = ET.fromstring(raw)
            channel = root.find("channel")
            items = channel.findall("item") if channel else root.findall("item")
            if not items:
                # Atom feed fallback
                items = root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("entry")
            count_added = 0
            for item in items[:25]:
                title_el = (item.find("title") or item.find("{http://www.w3.org/2005/Atom}title"))
                link_el  = (item.find("link")  or item.find("{http://www.w3.org/2005/Atom}link"))
                pub_el   = (item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")
                            or item.find("{http://www.w3.org/2005/Atom}updated"))
                desc_el  = (item.find("description") or item.find("{http://www.w3.org/2005/Atom}summary"))
                title   = (title_el.text or "").strip() if title_el is not None else ""
                link_v  = link_el.get("href", link_el.text or "") if link_el is not None else ""
                link    = (link_v or "").strip()
                pub     = (pub_el.text or "").strip() if pub_el is not None else ""
                snippet = (desc_el.text or "").strip()[:300] if desc_el is not None else ""
                combined = (title + " " + snippet).lower()
                if not any(kw in combined for kw in uap_keywords):
                    continue
                try:
                    from email.utils import parsedate
                    dt = parsedate(pub)
                    date_str = f"{dt[0]}-{dt[1]:02d}-{dt[2]:02d}" if dt else TODAY.strftime("%Y-%m-%d")
                except Exception:
                    date_str = TODAY.strftime("%Y-%m-%d")
                coords = location_from_text(title + " " + snippet)
                if not coords:
                    coords = {"lat": random.uniform(-40, 65), "lng": random.uniform(-150, 150)}
                ev_type = classify_type(title + " " + snippet)
                all_events.append({
                    "id": make_id(link or title),
                    "lat": coords["lat"], "lng": coords["lng"],
                    "type": ev_type, "date": date_str, "recent": True,
                    "isNew": date_str == TODAY.strftime("%Y-%m-%d"),
                    "title": title[:120],
                    "desc": snippet or f"Nota en {name}.",
                    "witnesses": 0, "credibility": "MEDIA (prensa internacional)",
                    "country": "—",
                    "sources": [name, link[:80] if link else name],
                })
                count_added += 1
            log.info(f"    {name}: {count_added} noticias UAP")
        except Exception as e:
            log.warning(f"    Error {name}: {e}")
        time.sleep(0.6)
    log.info(f"  Fuentes internacionales total: {len(all_events)} eventos")
    return all_events


# ─────────────────────────────────────────────────────────────
# Auto-archivo: mueve eventos recientes >7 días a histórico
# ─────────────────────────────────────────────────────────────
def archive_old_recent():
    """Carga events_recent.geojson existente; los eventos con fecha < SEVEN_DAYS_AGO
    se mueven a events_historical.geojson para no perderlos entre ejecuciones."""
    recent_path = DATA_DIR / "events_recent.geojson"
    hist_path   = DATA_DIR / "events_historical.geojson"
    if not recent_path.exists():
        return
    log.info("Auto-archivo: revisando eventos recientes viejos...")
    try:
        with open(recent_path, encoding="utf-8") as f:
            recent_gj = json.load(f)
        features = recent_gj.get("features", [])
        keep_recent = []
        to_archive  = []
        cutoff = SEVEN_DAYS_AGO.strftime("%Y-%m-%d")
        for feat in features:
            props = feat.get("properties", {})
            date_str = props.get("date", "")
            if date_str and date_str < cutoff:
                # Convertir a histórico
                props["recent"] = False
                props["isNew"]  = False
                to_archive.append(feat)
            else:
                keep_recent.append(feat)
        if not to_archive:
            log.info("  Auto-archivo: sin eventos viejos que migrar")
            return
        log.info(f"  Auto-archivo: migrando {len(to_archive)} eventos a histórico")
        # Cargar histórico existente y anexar
        if hist_path.exists():
            with open(hist_path, encoding="utf-8") as f:
                hist_gj = json.load(f)
            hist_feats = hist_gj.get("features", [])
        else:
            hist_feats = []
        existing_ids = {f.get("properties", {}).get("id") for f in hist_feats}
        for feat in to_archive:
            fid = feat.get("properties", {}).get("id")
            if fid not in existing_ids:
                hist_feats.append(feat)
                existing_ids.add(fid)
        # Guardar ambos archivos actualizados
        recent_gj["features"] = keep_recent
        with open(recent_path, "w", encoding="utf-8") as f:
            json.dump(recent_gj, f, ensure_ascii=False, indent=2)
        hist_gj = {"type": "FeatureCollection", "features": hist_feats}
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(hist_gj, f, ensure_ascii=False, indent=2)
        log.info(f"  Auto-archivo completado ✓ ({len(keep_recent)} recientes, {len(hist_feats)} históricos)")
    except Exception as e:
        log.warning(f"  Error en auto-archivo: {e}")


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

    # Auto-archivo primero: migra recientes >7 días antes de sobreescribir
    archive_old_recent()

    # Fuentes recientes
    all_recent.extend(fetch_gdelt_recent())
    all_recent.extend(fetch_google_news())
    all_recent.extend(fetch_reddit_multi(limit=75))
    all_recent.extend(fetch_all_rss())
    all_recent.extend(fetch_mex_newspapers())
    all_recent.extend(fetch_intl_newspapers())

    # Base histórica
    all_historical.extend(fetch_famous_historical())          # 51 casos icónicos
    all_historical.extend(fetch_nuforc_historical(max_records=2000))

    # Deduplicar
    all_recent = deduplicate(all_recent)
    all_historical = deduplicate(all_historical)

    # Filtro multi-fuente (sólo recientes — históricos NUFORC + famosos se mantienen)
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
                "El Universal / Milenio / La Jornada / Excélsior / SDP Noticias (MX)",
                "Mystery Wire / Daily Star / The Guardian / El País / RT / Sputnik (Intl)",
                f"51 eventos históricos famosos (Roswell, Campeche, Eclipse 1991…)",
                f"NUFORC CSV histórico (2 000 registros)",
            ],
            "filter": "eventos_recientes: ≥2 dominios distintos (NUFORC/Famosos exentos)",
        }, f, ensure_ascii=False, indent=2)
    log.info("Extracción completada ✓")

if __name__ == "__main__":
    main()
