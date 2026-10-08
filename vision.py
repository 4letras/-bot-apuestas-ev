"""
Módulo de visión por IA y extracción de texto para tickets y capturas de apuestas.
"""
import io
import json
import logging
import os
import re
from typing import Optional, Dict, Any
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def format_event_name(raw: str) -> str:
    """
    Formatea el nombre de un partido/evento de forma estética:
    - 'inglaterra croacia' -> 'Inglaterra - Croacia'
    - 'croacia vs españa' -> 'Croacia - España'
    - 'real madrid barcelona' -> 'Real Madrid - Barcelona'
    - 'lakers warriors' -> 'Lakers - Warriors'
    """
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r"^(?:evento|partido)[\s:=]+", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"^\((.+)\)$", r"\1", s).strip()

    # Si ya tiene separador explícito (vs, contra, -, /, @)
    sep_match = re.search(r"\s+(?:vs\.?|contra|/|@)\s+|\s*-\s*", s, re.IGNORECASE)
    if sep_match:
        parts = re.split(r"\s+(?:vs\.?|contra|/|@)\s+|\s*-\s*", s, flags=re.IGNORECASE)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return f"{parts[0].strip().title()} - {parts[1].strip().title()}"

    words = s.split()
    if len(words) == 2:
        return f"{words[0].title()} - {words[1].title()}"

    compound_prefixes = {
        "real", "atletico", "atlético", "manchester", "athletic", "bayern", "inter",
        "ac", "celta", "rayo", "borussia", "aston", "paris", "sporting", "river",
        "boca", "deportivo", "red", "tottenham", "crystal", "west"
    }
    if len(words) == 3:
        if words[0].lower() in compound_prefixes:
            return f"{words[0].title()} {words[1].title()} - {words[2].title()}"
        elif words[1].lower() in compound_prefixes:
            return f"{words[0].title()} - {words[1].title()} {words[2].title()}"

    if len(words) == 4:
        if words[0].lower() in compound_prefixes and words[2].lower() in compound_prefixes:
            return f"{words[0].title()} {words[1].title()} - {words[2].title()} {words[3].title()}"
        elif words[0].lower() in compound_prefixes:
            return f"{words[0].title()} {words[1].title()} - {words[2].title()} {words[3].title()}"
        else:
            return f"{words[0].title()} {words[1].title()} - {words[2].title()} {words[3].title()}"

    return s.title()

def parse_text_info(text: str) -> Dict[str, Any]:
    """
    Extrae parámetros a partir de un texto libre o pie de foto (caption).
    Soporta cualquier combinación y orden, por ejemplo:
    - '3,3 8% betfair'
    - 'betfair 8% 3,3'
    - 'inglaterra croacia'
    - '3,3 8% betfair inglaterra croacia'
    
    Reglas:
    - Cualquier número con '%' es SIEMPRE el margen.
    - El número decimal mayor que 1.0 es la cuota normal.
    - La casa de apuestas se detecta por coincidencia de nombre o palabras restantes.
    - El evento se detecta y formatea con 'Equipo1 - Equipo2'.
    """
    data = {}
    if not text:
        return data
    
    t = text.strip()

    # 1. Extraer MARGEN (prioridad absoluta al número con %)
    pct_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*%", t)
    if pct_match:
        data["margen"] = pct_match.group(0).replace(" ", "").strip()
        t = (t[:pct_match.start()] + " " + t[pct_match.end():]).strip()
    else:
        m_match = re.search(r"(?:margen|margin|mg)\b[\s:=]+([0-9]+(?:[.,][0-9]+)?%?)", t, re.IGNORECASE)
        if m_match:
            data["margen"] = m_match.group(1).strip()
            t = (t[:m_match.start()] + " " + t[m_match.end():]).strip()

    # 2. Extraer CASA (por prefijo 'casa:' o por nombres conocidos)
    casa_match = re.search(r"(?:casa|bookie)[\s:=]+([a-zA-Z0-9\s+]+?)(?=(?:\s*\||\s*[\n,]|\s*(?:evento|suceso|cuota|margen|$)))", t, re.IGNORECASE)
    if casa_match:
        data["casa"] = casa_match.group(1).strip()
        t = (t[:casa_match.start()] + " " + t[casa_match.end():]).strip()
    else:
        known_casas = [
            "bet365", "winamax", "codere", "bwin", "sportium", "marathonbet", "marathon",
            "luckia", "betfair", "kirolbet", "retabet", "pokerstars", "yaass casino", "yaass",
            "jokerbet", "interwetten", "daznbet", "paston", "casumo", "william hill",
            "888sport", "888", "betway", "tonybet", "olybet", "leovegas", "paf", "gran madrid",
            "jumbo", "suertia", "marca apuestas", "marcapuestas"
        ]
        for k in known_casas:
            pattern = rf"\b{re.escape(k)}\b"
            if re.search(pattern, t, re.IGNORECASE):
                data["casa"] = "William Hill" if k == "william hill" else (k.upper() if k in ["888", "888sport", "daznbet", "paf"] else k.capitalize())
                t = re.sub(pattern, " ", t, flags=re.IGNORECASE).strip()
                break

    # 3. Extraer CUOTA NORMAL (con prefijo o número decimal libre)
    c_match = re.search(r"(?:cuota\s*normal|cuota\s*sin\s*aumento|cuota\s*max|cuota|c\.normal|cn)\b[\s:=]+([0-9]+(?:[.,][0-9]+)?)", t, re.IGNORECASE)
    if c_match:
        try:
            data["cuota_normal"] = float(c_match.group(1).replace(",", "."))
            t = (t[:c_match.start()] + " " + t[c_match.end():]).strip()
        except Exception:
            pass
    else:
        odd_match = re.search(r"\b([1-9][0-9]*(?:[.,][0-9]+)?)\b", t)
        if odd_match:
            try:
                val = float(odd_match.group(1).replace(",", "."))
                if val > 1.0:
                    data["cuota_normal"] = val
                    t = (t[:odd_match.start()] + " " + t[odd_match.end():]).strip()
            except Exception:
                pass

    # 4. Extraer EVENTO (si tiene prefijo 'evento:' o 'partido:' o formato de equipos)
    ev_match = re.search(r"(?:evento|partido)[\s:=]+(.+?)(?=(?:\s*\||\s*[\n,]|\s*(?:suceso|cuota|margen|casa|$)))", t, re.IGNORECASE)
    if ev_match:
        data["evento"] = format_event_name(ev_match.group(1))
        t = (t[:ev_match.start()] + " " + t[ev_match.end():]).strip()
    elif " vs " in t.lower() or " - " in t or " contra " in t.lower():
        data["evento"] = format_event_name(t)
        t = ""
    elif len(t.split()) >= 2 and not any(k in t.lower() for k in ["marca", "gol", "tiro", "corner", "tarjeta", "over", "under", "gana", "ambos"]):
        # 2 o más palabras que son equipos (ej: 'inglaterra croacia')
        data["evento"] = format_event_name(t)
        t = ""

    # 5. Extraer SUCESO (si tiene prefijo)
    suc_match = re.search(r"(?:suceso|mercado|pronostico|apuesta)[\s:=]+(.+?)(?=(?:\s*\||\s*[\n,]|\s*(?:evento|cuota|margen|casa|$)))", t, re.IGNORECASE)
    if suc_match:
        data["suceso"] = suc_match.group(1).strip()
        t = (t[:suc_match.start()] + " " + t[suc_match.end():]).strip()

    # 6. Si todavía no se asignó casa y queda texto limpio corto (1 o 2 palabras)
    clean_rem = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]", "", t).strip()
    if "casa" not in data and clean_rem and len(clean_rem.split()) <= 2:
        if "evento" in data:
            data["casa"] = clean_rem.title()
        elif len(clean_rem.split()) == 2:
            data["evento"] = format_event_name(clean_rem)
        else:
            data["casa"] = clean_rem.title()

    return data

def extract_bet_from_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Utiliza Gemini Vision para extraer los datos de la captura de la apuesta aumentada.
    Si no hay API key o falla, devuelve un diccionario vacío.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.info("No se ha configurado GEMINI_API_KEY. Se solicitarán datos manualmente.")
        return {}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        
        prompt = (
            "Eres un analista experto en apuestas deportivas y cuotas aumentadas.\n"
            "Analiza detenidamente esta captura de pantalla de una casa de apuestas y extrae los datos en formato JSON.\n"
            "Campos a extraer:\n"
            "- 'casa': Nombre de la casa de apuestas (ej: 'Bet365', 'Winamax', 'Codere', 'Bwin', etc.) si se puede deducir del logo, interfaz, colores o texto. Si no, null.\n"
            "- 'evento': El partido o evento deportivo (ej: 'Croacia - España', 'Real Madrid vs Barcelona'). Si aparece entre paréntesis o en el texto, extráelo. Si no aparece, null.\n"
            "- 'suceso': La selección o mercado concreto de la apuesta (ej: 'España marca En los primeros 15 minutos'). DEBE EXTRAERSE SIEMPRE QUE SEA VISIBLE.\n"
            "- 'cuota_aumentada': La cuota aumentada o cuota actual ofrecida (número decimal, ej: 4.00). DEBE EXTRAERSE SIEMPRE QUE HAYA UN BOTÓN O CUOTA VISIBLE.\n"
            "- 'cuota_normal': La cuota original sin aumento si aparece indicada (ej: antes 3.00 -> 3.00). Si no aparece, null.\n"
            "\n"
            "Devuelve ÚNICAMENTE un objeto JSON con esas claves, sin markdown ni texto adicional."
        )

        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.8-flash",
            "gemini-3.5-flash"
        ]

        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        ),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )

                text_resp = response.text.strip()
                text_resp = re.sub(r"^```json\s*", "", text_resp)
                text_resp = re.sub(r"\s*```$", "", text_resp)
                
                parsed = json.loads(text_resp)
                if parsed.get("evento"):
                    parsed["evento"] = format_event_name(parsed["evento"])

                logger.info(f"Éxito extrayendo imagen con {model_name}: {parsed}")
                return parsed
            except Exception as model_err:
                logger.warning(f"Fallo con {model_name}: {model_err}. Probando siguiente modelo...")
                continue

        logger.warning("Todos los modelos de Gemini fallaron al procesar la imagen.")
        return {}

    except Exception as e:
        logger.warning(f"Error general procesando imagen con Gemini: {e}")
        return {}
