import re
import logging
import asyncio
import aiohttp
import inspect
from urllib.parse import quote_plus
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
from plugins.Dreamxfutures.Imdbposter import get_movie_detailsx, fetch_image, get_movie_details
from database.users_chats_db import db
from pyrogram import Client, filters, enums
from info import CHANNELS, MOVIE_UPDATE_CHANNEL, LINK_PREVIEW, ABOVE_PREVIEW, BAD_WORDS, LANDSCAPE_POSTER, TMDB_POSTER
from Script import script
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
from pymongo.errors import PyMongoError, DuplicateKeyError
from pyrogram.errors import MessageIdInvalid, MessageNotModified, FloodWait
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ----------------- HDHUB4U PERMANENT GATEWAYS (OFFICIAL & ACTIVE MIRRORS) -----------------
HDHUB_PERMANENT_GATEWAYS = [
    "https://new1.hdhub4u.free",
    "https://hdhub4u.bi",
    "https://hdhub4u.ms",
    "https://hdhub4u.tv",
    "https://hdhub4u.ag",
    "https://hdhub4u.download"
]
DEFAULT_HDHUB_DOMAIN = "https://new1.hdhub4u.free"

_CACHED_HDHUB_DOMAIN = None
_DOMAIN_CACHE_EXPIRY = 0

_BASE_IGNORE_WORDS = {
    "rarbg", "dub", "sub", "sample", "mkv", "mp4", "avi", "aac", "ac3", "eac3", "ddp", "ddp5", "atmos", "dts",
    "combined", "esub", "msub", "proper", "repack", "unrated", "extended", "imax", "remux", "10bit", "10-bit",
    "x264", "x265", "h264", "h265", "hevc", "avc", "dovi", "hdr", "hdr10",
    "web", "dl", "bonus", "special", "ott", "ott-dl", "ottplay", "full", "movie",
    "hdcam", "hdtc", "camrip", "cam", "ts", "tc", "hdts",
    "telesync", "dvdscr", "dvdrip", "predvd", "webrip", "web-dl", "tvrip",
    "hdtv", "web dl", "webdl", "bluray", "brrip", "bdrip", "360p", "480p",
    "720p", "1080p", "2160p", "4k", "1440p", "540p", "240p", "140p",
    "hdrip", "hq-hdrip", "hq-hdtc", "hq-cam", "hq-ts", "hq-predvd",
    "dual", "multi", "audio",
    "v1", "v2", "v3", "v4", "v5", "v6", "version", "ver", "cleaned", "clean",
    "nf", "netflix", "sonyliv", "sony", "sliv", "amzn", "prime",
    "primevideo", "hotstar", "zee5", "jio", "jhs", "aha", "hbo", "paramount",
    "apple", "atv", "atvp", "appletv", "hoichoi", "sunnxt", "viki", "cr", "crunchyroll", "hulu",
    "disney", "dnp", "lionsgate", "lionsgateplay", "peacock", "max", "alt",
    "altbalaji", "altt", "shemaroo", "shemaroome", "chaupal", "stage",
    "planetmarathi", "manorama", "manoramamax", "tubi",
    "5.1", "7.1", "2.0", "5.1ch", "7.1ch", "dd5.1", "ddp5.1", "dd", "ddp"
}

IGNORE_WORDS = _BASE_IGNORE_WORDS | set(BAD_WORDS if isinstance(BAD_WORDS, (list, tuple, set)) else [])

CAPTION_LANGUAGES = {
    "hin": "Hindi", "hindi": "Hindi",
    "tam": "Tamil", "tamil": "Tamil",
    "kan": "Kannada", "kannada": "Kannada",
    "tel": "Telugu", "telugu": "Telugu",
    "mal": "Malayalam", "malayalam": "Malayalam",
    "eng": "English", "english": "English",
    "pun": "Punjabi", "punjabi": "Punjabi",
    "ben": "Bengali", "bengali": "Bengali",
    "mar": "Marathi", "marathi": "Marathi",
    "guj": "Gujarati", "gujarati": "Gujarati",
    "urd": "Urdu", "urdu": "Urdu",
    "kor": "Korean", "korean": "Korean",
    "jpn": "Japanese", "japanese": "Japanese",
    "bho": "Bhojpuri", "bhojpuri": "Bhojpuri",
    "ori": "Odia", "odia": "Odia", "oriya": "Odia",
    "asm": "Assamese", "assamese": "Assamese",
    "spa": "Spanish", "spanish": "Spanish",
    "fre": "French", "french": "French", "fra": "French",
    "ger": "German", "german": "German", "deu": "German",
    "ita": "Italian", "italian": "Italian",
    "rus": "Russian", "russian": "Russian",
    "chi": "Chinese", "chinese": "Chinese", "zho": "Chinese",
    "tha": "Thai", "thai": "Thai",
    "ind": "Indonesian", "indonesian": "Indonesian",
    "dual": "Dual Audio", "multi": "Multi Audio",
    "hq dub": "HQ Dub", "hq-dub": "HQ Dub",
    "hq audio": "HQ Audio", "hq-audio": "HQ Audio",
    "line audio": "Line Audio", "hq line": "HQ Line", "hq-line": "HQ Line",
    "mic audio": "Mic Audio", "clean audio": "Clean Audio"
}

OTT_PLATFORMS = {
    "nf": "Netflix", "netflix": "Netflix",
    "sonyliv": "SonyLiv", "sony": "SonyLiv", "sliv": "SonyLiv",
    "amzn": "Amazon Prime Video", "prime": "Amazon Prime Video", "primevideo": "Amazon Prime Video",
    "hotstar": "Disney+ Hotstar", "disney": "Disney+", "dnp": "Disney+",
    "zee5": "Zee5",
    "jio": "JioHotstar", "jhs": "JioHotstar",
    "aha": "Aha", "hbo": "HBO Max", "max": "Max",
    "paramount": "Paramount+",
    "apple": "Apple TV+", "atv": "Apple TV+", "atvp": "Apple TV+", "appletv": "Apple TV+",
    "hoichoi": "Hoichoi", "sunnxt": "Sun NXT", "viki": "Viki",
    "cr": "Crunchyroll", "crunchyroll": "Crunchyroll",
    "hulu": "Hulu",
    "peacock": "Peacock",
    "lionsgate": "Lionsgate Play", "lionsgateplay": "Lionsgate Play",
    "altbalaji": "ALTT", "alt": "ALTT", "altt": "ALTT",
    "shemaroo": "ShemarooMe", "shemaroome": "ShemarooMe",
    "chaupal": "Chaupal",
    "stage": "Stage",
    "planetmarathi": "Planet Marathi",
    "manorama": "ManoramaMAX", "manoramamax": "ManoramaMAX",
    "tubi": "Tubi"
}

STANDARD_FORMATS = {
    "hdtc": "HDTC", "hd-tc": "HDTC", "hq-hdtc": "HQ-HDTC",
    "hdcam": "HDCam", "hd-cam": "HDCam", "hq-hdcam": "HQ-HDCam",
    "cam": "CAM", "camrip": "CamRip", "hq-cam": "HQ-CAM",
    "ts": "TS", "hdts": "HDTS", "hq-ts": "HQ-TS", "tc": "TC",
    "telesync": "TeleSync", "predvd": "PreDVD", "hq-predvd": "HQ-PreDVD",
    "dvdrip": "DVDRip", "dvdscr": "DVDScr",
    "webrip": "WEBRip", "web-dl": "WEB-DL", "webdl": "WEB-DL", "web dl": "WEB-DL",
    "bluray": "BluRay", "brrip": "BRRip", "bdrip": "BDRip",
    "remux": "Remux", "imax": "IMAX",
    "hdrip": "HDRip", "hq-hdrip": "HQ-HDRip",
    "hdtv": "HDTV", "tvrip": "TVRip",
    "hevc": "HEVC", "10bit": "10-Bit", "10-bit": "10-Bit",
    "hdr": "HDR", "hdr10": "HDR10", "hdr10+": "HDR10+",
    "dv": "Dolby Vision", "dovi": "Dolby Vision"
}

RES_ORDER = {
    "140p": 140, "240p": 240, "360p": 360, "480p": 480,
    "540p": 540, "720p": 720, "1080p": 1080, "1440p": 1440,
    "2160p": 2160, "4k": 2160
}

CLEAN_PATTERN = re.compile(r'@[^ \n\r\t\.,:;!?()\[\]{}<>\\/"\'=_%]+|\bwww\.[^\s\]\)]+|\([\@^]+\)|\[[\@^]+\]')
NORMALIZE_PATTERN = re.compile(r"[._]+|[()\[\]{}:;'–!,.?_]")
RESOLUTION_PATTERN = re.compile(r"\b(?:2160p|4K|1440p|1080p|720p|540p|480p|360p|240p|140p)\b", re.IGNORECASE)
SOURCE_PATTERN = re.compile(
    r"\b(?:HDCam|HD-Cam|HQ-HDCam|HDTC|HD-TC|HQ-HDTC|CamRip|CAM|HQ-CAM|TS|HDTS|HQ-TS|TC|TeleSync|DVDScr|DVDRip|PreDVD|HQ-PreDVD|"
    r"WEBRip|WEB-DL|TVRip|HDTV|WEB DL|WebDl|BluRay|BRRip|BDRip|Remux|IMAX|"
    r"HEVC|10Bit|10-Bit|HDRip|HQ-HDRip|HDR10\+|HDR10|HDR|DV|DoVi)\b",
    re.IGNORECASE
)
VERSION_STANDALONE = re.compile(r"\b(?:[vV]\d+|ver\.?\s*\d+|version\s*\d+)\b", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?![A-Za-z0-9])")
AUDIO_CHANNELS_PATTERN = re.compile(
    r'\b(?:DD|DDP|AC3|EAC3|AAC|TRUEHD|ATMOS|DOLBY)?[\s._-]*[257][\s._-][01](?:[\s._-]*CH)?\b',
    re.IGNORECASE
)

BONUS_RANGE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Bonus|Special)[\s._-]*(?:E(?:p(?:isode)?)?[\s._-]*)?0*(\d{1,3})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?[\s._-]*)?0*(\d{1,3})\b', re.IGNORECASE)
BONUS_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Bonus|Special)[\s._-]*(?:E(?:p(?:isode)?)?[\s._-]*)?0*(\d{1,3})\b', re.IGNORECASE)
RANGE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Part)?[\s._-]*E(?:p(?:isode)?)?[\s._-]*0*(\d{1,3})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?[\s._-]*)?0*(\d{1,3})', re.IGNORECASE)
SINGLE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Part)?[\s._-]*E(?:p(?:isode)?)?[\s._-]*0*(\d{1,3})\b', re.IGNORECASE)
NAMED_REGEX = re.compile(r'Season\s*0*(\d{1,2})[\s\-,:._]*(?:Part)?[\s\-,:._]*Ep(?:isode)?[\s._-]*0*(\d{1,3})\b', re.IGNORECASE)
X_REGEX = re.compile(r'(?<!\d)\b0*([1-9]\d?)\s*[xX]\s*0*([1-9]\d?)\b(?!\d)', re.IGNORECASE)
DAY_REGEX = re.compile(r'\b(?:S(?:eason)?\s*0*(\d{1,2})[\s._-]*)?(?:Day\s*0*(\d{1,3})|D0*([1-9]\d{0,2}))\b', re.IGNORECASE)
NO_S_REGEX = re.compile(r'\b(?:Season|S)\s*0*(\d{1,2})[\s._-]+E(?:p(?:isode)?)?[\s._-]*0*(\d{1,3})\b', re.IGNORECASE)
EP_ONLY_RANGE = re.compile(r'\b(?:EP|Episode)[\s._-]*0*(\d{1,3})\s*-\s*0*(\d{1,3})\b', re.IGNORECASE)
EP_ONLY_SINGLE = re.compile(r'\b(?:EP|Episode)\.?[\s._-]*0*(\d{1,3})\b', re.IGNORECASE)

MEDIA_FILTER = filters.document | filters.video | filters.audio

locks = defaultdict(asyncio.Lock)
pending_updates = {}
sending_updates = set()


def clean_mentions_links(text: str) -> str:
    return CLEAN_PATTERN.sub("", text or "").strip()


def normalize(s: str) -> str:
    s = NORMALIZE_PATTERN.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def remove_ignored_words(text: str) -> str:
    ignore_words_lower = {w.lower() for w in IGNORE_WORDS}
    return " ".join(
        word for word in text.split()
        if word.lower() not in ignore_words_lower
    )


def extract_sequel_num(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    m = re.search(r'\b(?:part|chapter|volume|vol)?\s*([2-9]|ii|iii|iv|v|vi|vii|viii|ix|x)\b', t, re.IGNORECASE)
    if m:
        val = m.group(1).lower()
        roman_map = {'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
        return roman_map.get(val, val)
    return None


def extract_year_from_text(text: str) -> Optional[int]:
    matches = YEAR_PATTERN.findall(text)
    if matches:
        return int(matches[-1])
    return None


def is_good_title_match(query: str, found_title: str, query_year: Optional[int] = None) -> bool:
    if not query or not found_title:
        return False

    if re.search(r'\b(?:review|trailer|teaser|interview|reaction)\b', found_title, re.IGNORECASE):
        return False

    if not query_year:
        query_year = extract_year_from_text(query)

    found_year = extract_year_from_text(found_title)
    if query_year and found_year:
        if abs(query_year - found_year) > 1:
            return False

    q_seq = extract_sequel_num(query)
    f_seq = extract_sequel_num(found_title)
    if q_seq != f_seq:
        return False

    q_raw = YEAR_PATTERN.sub('', query).strip()
    f_raw = YEAR_PATTERN.sub('', found_title).strip()

    def clean_words(s: str):
        s = re.sub(r'\(?\b(?:full\s*movie|full\s*series|full\s*film|hd|rip|dubbed|hindi|punjabi|dual\s*audio)\b\)?', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^(the|a|an)\s+', '', s, flags=re.IGNORECASE)
        s = re.sub(r"['’]", "", s)
        s = normalize(s).lower()
        return [w for w in s.split() if w]

    q_words = clean_words(q_raw)
    f_words = clean_words(f_raw)

    if not q_words or not f_words:
        return False

    if ('ott' in f_words) != ('ott' in q_words):
        return False

    if q_words == f_words:
        return True

    q_joined = " ".join(q_words)
    f_joined = " ".join(f_words)
    if q_joined in f_joined or f_joined in q_joined:
        return True

    for sep in [':', '-', '–', '—', '|']:
        if sep in f_raw:
            main_part = f_raw.split(sep)[0].strip()
            main_words = clean_words(main_part)
            if q_words == main_words:
                return True

    return False


def get_qualities(text: str) -> str:
    if not text:
        return "N/A"

    v_match = VERSION_STANDALONE.search(text)
    version_str = None
    if v_match:
        raw_v = v_match.group(0).upper()
        raw_v = re.sub(r'^(?:VER\.?|VERSION)\s*', 'V', raw_v)
        if not raw_v.startswith("V"):
            raw_v = f"V{raw_v}"
        version_str = raw_v

    resolutions = []
    for r in RESOLUTION_PATTERN.findall(text):
        norm_r = r.lower() if r.lower() != "4k" else "4K"
        if norm_r not in resolutions:
            resolutions.append(norm_r)

    sources = []
    for s in SOURCE_PATTERN.findall(text):
        s_norm = re.sub(r"[._]+", "-", s).strip().lower()
        formatted = STANDARD_FORMATS.get(s_norm, s.upper())
        if formatted not in sources:
            sources.append(formatted)

    if version_str:
        attached = False
        for idx, s in enumerate(sources):
            if any(k in s.upper() for k in ["HDTC", "CAM", "TS", "PREDVD", "WEBRIP", "WEB-DL", "RIP", "BLURAY"]):
                sources[idx] = f"{s} {version_str}"
                attached = True
                break
        if not attached:
            sources.append(version_str)

    all_items = resolutions + sources
    return ", ".join(all_items) if all_items else "N/A"


def format_movie_qualities(quality_list: list) -> str:
    if not quality_list:
        return "N/A"

    resolutions = set()
    sources = set()
    versions = set()

    for item in quality_list:
        if not item or item == "N/A":
            continue

        v_matches = VERSION_STANDALONE.findall(item)
        for vm in v_matches:
            v_num = re.sub(r"\D", "", vm)
            if v_num:
                versions.add(int(v_num))

        for r in RESOLUTION_PATTERN.findall(item):
            norm_r = r.lower() if r.lower() != "4k" else "4K"
            resolutions.add(norm_r)

        for s in SOURCE_PATTERN.findall(item):
            s_norm = re.sub(r"[._]+", "-", s).strip().lower()
            formatted = STANDARD_FORMATS.get(s_norm, s.upper())
            sources.add(formatted)

    if "HQ-HDTC" in sources and "HDTC" in sources:
        sources.remove("HDTC")
    if "HQ-CAM" in sources:
        sources.discard("CAM")
        sources.discard("HDCam")
    if "HDCam" in sources and "CAM" in sources:
        sources.remove("CAM")
    if "HQ-TS" in sources:
        sources.discard("TS")
        sources.discard("HDTS")
    if "HDTS" in sources and "TS" in sources:
        sources.remove("TS")
    if "HQ-PreDVD" in sources and "PreDVD" in sources:
        sources.remove("PreDVD")
    if "HDR10+" in sources:
        sources.discard("HDR10")
        sources.discard("HDR")
    elif "HDR10" in sources:
        sources.discard("HDR")

    sorted_res = sorted(resolutions, key=lambda x: RES_ORDER.get(x.lower(), 9999))
    version_str = f"V{max(versions)}" if versions else ""

    source_list = []
    for s in sorted(sources):
        if s and s not in source_list:
            source_list.append(s)

    if version_str:
        attached = False
        for idx, s in enumerate(source_list):
            if any(k in s.upper() for k in ["HDTC", "CAM", "TS", "PREDVD", "WEBRIP", "WEB-DL", "RIP", "BLURAY"]):
                source_list[idx] = f"{s} {version_str}"
                attached = True
                break
        if not attached:
            sources.append(version_str)

    final_parts = sorted_res + source_list
    return ", ".join(final_parts) if final_parts else "N/A"


def extract_ott_platform(text: str) -> str:
    text = text.lower()
    platforms = {
        plat
        for key, plat in OTT_PLATFORMS.items()
        if re.search(rf"\b{re.escape(key)}\b", text)
    }
    return " | ".join(sorted(platforms)) if platforms else "N/A"


def get_clean_title(name: str) -> str:
    y = extract_year_from_text(name)
    s_match = re.search(r'\b(?:season|s)\s*0*(\d+)\b', name, re.IGNORECASE)
    t = re.sub(r'\b(19|20)\d{2}\b', '', name)
    t = re.sub(r'\b(?:season|s)\s*0*(\d+)\b', '', t, flags=re.IGNORECASE)
    clean_t = normalize(t).lower()
    if s_match:
        clean_t = f"{clean_t} s{int(s_match.group(1))}"
    if y:
        clean_t = f"{clean_t} {y}"
    return clean_t.strip()


def format_runtime(runtime_val, is_series: bool = False) -> str:
    if not runtime_val or str(runtime_val).strip().upper() in ("N/A", "NONE", "0", "-", ""):
        return "N/A"

    if isinstance(runtime_val, (list, tuple)):
        if not runtime_val:
            return "N/A"
        runtime_val = runtime_val[0]

    runtime_str = str(runtime_val).strip()
    runtime_str = re.sub(r'[\s/]*(?:ep|episode)\b', '', runtime_str, flags=re.IGNORECASE).strip()

    total_mins = 0
    try:
        try:
            total_mins = int(float(runtime_str))
        except ValueError:
            colon_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", runtime_str)
            if colon_match:
                hours = int(colon_match.group(1))
                mins = int(colon_match.group(2))
                total_mins = (hours * 60) + mins
            else:
                hours_match = re.search(r"(\d+)\s*(?:h|hr|hour)s?", runtime_str, re.IGNORECASE)
                mins_match = re.search(r"(\d+)\s*(?:m|min|minute)s?", runtime_str, re.IGNORECASE)

                if hours_match or mins_match:
                    hours = int(hours_match.group(1)) if hours_match else 0
                    mins = int(mins_match.group(1)) if mins_match else 0
                    total_mins = (hours * 60) + mins
                else:
                    numbers = re.findall(r"\d+", runtime_str)
                    if numbers:
                        total_mins = int(numbers[0])
    except Exception:
        return "N/A"

    if total_mins <= 0:
        return "N/A"

    if total_mins >= 60:
        hours = total_mins // 60
        mins = total_mins % 60
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
    else:
        return f"{total_mins}m"


def parse_clean_rating(val) -> Optional[str]:
    if not val:
        return None
    val_str = str(val).strip()
    if val_str.lower() in ("x", "n/a", "na", "x/10", "none", "0", "0.0", "-"):
        return None
    try:
        cleaned = re.sub(r'[^\d.]', ' ', val_str.split('/')[0]).strip()
        parts = cleaned.split()
        if parts:
            num = float(parts[0])
            if 1.0 <= num <= 10.0:
                return f"{num:.1f}"
    except Exception:
        pass
    return None


def clean_and_format_genres(genre_sources: list) -> str:
    """Combines genre lists from all sources, cleans them and removes junk/incomplete tokens."""
    cleaned = []
    seen = set()

    for item in genre_sources:
        if not item or str(item).strip().upper() in ("N/A", "NONE", ""):
            continue
        if isinstance(item, str):
            parts = re.split(r'[,|/•&]+', item)
        elif isinstance(item, (list, tuple)):
            parts = []
            for g in item:
                if isinstance(g, dict):
                    parts.append(g.get("name") or g.get("genre") or "")
                else:
                    parts.append(str(g))
        else:
            continue

        for p in parts:
            p_clean = re.sub(r'\b(?:info|trailer|dropdown|menu|select|category)\b', '', p, flags=re.IGNORECASE).strip().title()
            p_clean = p_clean.strip(" .-_/\\")
            if len(p_clean) >= 2 and p_clean.lower() not in seen and p_clean.lower() not in ["n/a", "none"]:
                seen.add(p_clean.lower())
                cleaned.append(p_clean)

    return ", ".join(cleaned) if cleaned else "N/A"


# ----------------- BLOGGER DATA FETCHER (POSTER, RATING, GENRES, IMDB) -----------------
async def get_blogger_data(base_name: str, year: Optional[str] = None) -> dict:
    res = {"poster_url": None, "rating": None, "genres": None, "imdb_url": None}
    try:
        blog_url = "https://tmdbimdbhdhub4u.blogspot.com"
        if hasattr(db, 'db'):
            setting = await db.db.settings.find_one({"_id": "blogger_base_url"})
            if setting and setting.get("url"):
                blog_url = setting["url"].rstrip("/")

        target_year = int(year) if year and str(year).isdigit() else extract_year_from_text(base_name)
        clean_series = re.sub(r'\s+Season\s*\d+', '', base_name, flags=re.IGNORECASE).strip()
        clean_target = re.sub(r'\b(19|20)\d{2}\b', '', clean_series).strip()
        target_s_match = re.search(r'\b(?:season|s)\s*0*(\d+)\b', base_name, re.IGNORECASE)
        target_season = int(target_s_match.group(1)) if target_s_match else None

        search_term = f"{clean_target} {target_year}" if target_year else clean_target
        feed_urls = [
            f"{blog_url}/feeds/posts/default?q={quote_plus(search_term)}&alt=json&max-results=25",
            f"{blog_url}/feeds/posts/default?alt=json&max-results=150"
        ]

        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for feed_url in feed_urls:
                try:
                    async with session.get(feed_url) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                except Exception:
                    continue

                entries = data.get("feed", {}).get("entry", [])
                if not entries:
                    continue

                for entry in entries:
                    post_title = entry.get("title", {}).get("$t", "").strip()
                    cand_lower = post_title.lower()

                    if ('ott' in cand_lower) != ('ott' in base_name.lower()):
                        continue

                    cand_year = extract_year_from_text(post_title)
                    if target_year and cand_year and abs(target_year - cand_year) > 1:
                        continue

                    matched = False
                    if is_good_title_match(base_name, post_title, query_year=target_year) or is_good_title_match(clean_target, post_title, query_year=target_year):
                        matched = True
                    elif clean_target.lower() in cand_lower:
                        cand_s_match = re.search(r'\b(?:season|s)\s*0*(\d+)\b', post_title, re.IGNORECASE)
                        if target_season and cand_s_match:
                            if int(cand_s_match.group(1)) == target_season:
                                matched = True
                        elif not cand_s_match:
                            matched = True

                    if matched:
                        content_html = entry.get("content", {}).get("$t", "") or entry.get("summary", {}).get("$t", "")
                        soup = BeautifulSoup(content_html, "html.parser")

                        img_tag = soup.find("img")
                        img_url = img_tag.get("src") or img_tag.get("data-src") if img_tag else None

                        if not img_url:
                            for a in soup.find_all("a", href=True):
                                href = a["href"]
                                if any(href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "googleusercontent.com" in href:
                                    img_url = href
                                    break

                        if not img_url and "media$thumbnail" in entry:
                            img_url = entry["media$thumbnail"].get("url")

                        if img_url:
                            img_url = re.sub(r'/s\d+(-c)?/', '/s1600/', img_url)
                            img_url = re.sub(r'/w\d+-h\d+.*?/', '/s1600/', img_url)
                            img_url = re.sub(r'=w\d+-h\d+.*$', '=s1600', img_url)
                            img_url = re.sub(r'=s\d+.*$', '=s1600', img_url)
                            res["poster_url"] = img_url

                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if "imdb.com/title/tt" in href or "themoviedb.org" in href:
                                res["imdb_url"] = href
                                break

                        full_text = soup.get_text()
                        r_match = re.search(r'(?:IMDb|Rating|Score)?[:\s]*([0-9](?:\.[0-9])?)\s*(?:\/\s*10)?', full_text, re.IGNORECASE)
                        if r_match:
                            val = parse_clean_rating(r_match.group(1))
                            if val:
                                res["rating"] = val

                        genre_tags = soup.select(".genre-tag, .meta-pill.genre")
                        if genre_tags:
                            res["genres"] = ", ".join([g.get_text().strip() for g in genre_tags if g.get_text().strip()])
                        else:
                            g_match = re.search(r'\b(?:Genre|Genres)\s*[:\-–]\s*([^\n\r]+)', full_text, re.IGNORECASE)
                            if g_match:
                                raw_g = g_match.group(1).strip()
                                raw_g = re.split(r'\b(?:Release|Rating|Language|Link|Cast|Director)\b', raw_g, flags=re.IGNORECASE)[0]
                                parts = [p.strip().title() for p in re.split(r'[,|/•&]', raw_g) if len(p.strip()) >= 2]
                                if parts:
                                    res["genres"] = ", ".join(parts)

                        return res
    except Exception as e:
        logger.error(f"Error fetching Blogger data: {e}")
    return res


# ----------------- DIRECT OFFICIAL LIVE IMDB ENGINE -----------------
async def fetch_imdb_live_data(title: str, year: Optional[int] = None, direct_tt: Optional[str] = None) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    timeout = aiohttp.ClientTimeout(total=7)
    imdb_id = direct_tt if (direct_tt and direct_tt.startswith("tt")) else None

    if not imdb_id:
        clean_q = re.sub(r'\b(19|20)\d{2}\b', '', title).strip()
        clean_q = re.sub(r'\b(?:season|s)\s*\d+\b', '', clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r'\(?\b(?:full\s*movie|punjabi|hindi|dual\s*audio)\b\)?', '', clean_q, flags=re.IGNORECASE).strip()
        search_query = f"{clean_q} {year}" if year else clean_q
        search_url = f"https://v3.sg.media-imdb.com/suggestion/x/{quote_plus(search_query.lower())}.json"

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(search_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("d", []):
                            cand_id = item.get("id", "")
                            if not cand_id.startswith("tt"):
                                continue
                            cand_title = item.get("l", "")
                            cand_year = item.get("y")
                            if year and cand_year and abs(int(year) - int(cand_year)) > 1:
                                continue
                            if is_good_title_match(clean_q, cand_title, query_year=year):
                                imdb_id = cand_id
                                break
        except Exception as e:
            logger.debug(f"IMDb suggestion error: {e}")

    if not imdb_id:
        return {}

    page_url = f"https://www.imdb.com/title/{imdb_id}/"
    res = {"imdb_id": imdb_id, "imdb_url": page_url, "rating": "N/A", "genres": "N/A"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(page_url, headers=headers) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")

                    rate_tag = (
                        soup.select_one('[data-testid="hero-rating-bar__aggregate-rating__score"] span')
                        or soup.select_one('.ratingValue span')
                        or soup.select_one('[itemprop="ratingValue"]')
                    )
                    if rate_tag:
                        val = parse_clean_rating(rate_tag.get_text())
                        if val:
                            res["rating"] = val

                    genre_tags = soup.select('[data-testid="genres"] a, .ipc-chip__text')
                    found_genres = []
                    for g in genre_tags:
                        gt = g.get_text().strip().title()
                        if 2 <= len(gt) <= 25 and gt not in found_genres and not any(bad in gt.lower() for bad in ["back to top", "view", "edit", "ratings", "reviews"]):
                            found_genres.append(gt)
                    if found_genres:
                        res["genres"] = ", ".join(found_genres)
    except Exception as e:
        logger.debug(f"Error fetching live IMDb page: {e}")

    return res


# ----------------- STRICT NO-4K DOMAIN GUARD -----------------
def is_valid_hdhub_domain(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    if "4k" in u:
        return False
    if "hdhub4u" in u:
        return True
    return False


async def resolve_live_hdhub_domain() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1"
    }
    timeout = aiohttp.ClientTimeout(total=8)

    current_stored = None
    try:
        if hasattr(db, 'db'):
            setting = await db.db.settings.find_one({"_id": "hdhub_base_url"})
            if setting and setting.get("url") and is_valid_hdhub_domain(setting["url"]):
                current_stored = setting["url"].rstrip("/")
    except Exception:
        pass

    candidates = [current_stored] if current_stored else []
    for gw in HDHUB_PERMANENT_GATEWAYS:
        if gw not in candidates and is_valid_hdhub_domain(gw):
            candidates.append(gw)

    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
        for candidate in candidates:
            if not candidate:
                continue
            try:
                async with session.get(candidate, headers=headers, allow_redirects=True) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    final_url = str(resp.url).rstrip("/")

                soup = BeautifulSoup(html, "html.parser")
                view_button = (
                    soup.find("a", string=re.compile(r"view\s*full\s*site", re.I))
                    or soup.select_one("a.btn, a[href*='hdhub4u']")
                )
                if view_button and view_button.get("href"):
                    target_url = view_button["href"].strip()
                    m = re.match(r'(https?://[^/]+)', target_url)
                    if m:
                        live_domain = m.group(1).rstrip("/")
                        if is_valid_hdhub_domain(live_domain):
                            if hasattr(db, 'db') and live_domain != current_stored:
                                await db.db.settings.update_one(
                                    {"_id": "hdhub_base_url"},
                                    {"$set": {"url": live_domain}},
                                    upsert=True
                                )
                                logger.info(f"🎯 [HDHub4u Domain Resolved]: {live_domain}")
                            return live_domain

                match = re.match(r'(https?://[^/]+)', final_url)
                if match:
                    live_domain = match.group(1).rstrip("/")
                    if is_valid_hdhub_domain(live_domain):
                        return live_domain
            except Exception as e:
                logger.debug(f"Gateway check failed for {candidate}: {e}")
                continue

    return current_stored or DEFAULT_HDHUB_DOMAIN


async def get_hdhub_base_url(force_refresh: bool = False) -> str:
    global _CACHED_HDHUB_DOMAIN, _DOMAIN_CACHE_EXPIRY
    current_time = asyncio.get_event_loop().time()

    if not force_refresh and _CACHED_HDHUB_DOMAIN and is_valid_hdhub_domain(_CACHED_HDHUB_DOMAIN) and current_time < _DOMAIN_CACHE_EXPIRY:
        return _CACHED_HDHUB_DOMAIN

    detected_domain = await resolve_live_hdhub_domain()
    _CACHED_HDHUB_DOMAIN = detected_domain
    _DOMAIN_CACHE_EXPIRY = current_time + 43200
    return _CACHED_HDHUB_DOMAIN


async def fetch_imdb_safely(base_name: str, is_series: bool, year: Optional[str] = None) -> dict:
    sig = inspect.signature(get_movie_details)
    kwargs = {}
    if "is_series" in sig.parameters:
        kwargs["is_series"] = is_series
    elif "media_type" in sig.parameters:
        kwargs["media_type"] = "tv" if is_series else "movie"

    target_year = int(year) if year and str(year).isdigit() else extract_year_from_text(base_name)

    if str(base_name).strip().lower().startswith("tt"):
        try:
            res = await get_movie_details(str(base_name).strip(), id=True, **kwargs)
            if res and isinstance(res, dict):
                return res
        except Exception as e:
            logger.warning(f"Error fetching direct IMDb ID: {e}")

    search_name = re.sub(r'\s+Season\s*\d+', '', base_name, flags=re.IGNORECASE).strip() if is_series else base_name
    clean_search = re.sub(r'\b(19|20)\d{2}\b', '', search_name).strip()
    clean_search = re.sub(r'\(?\b(?:full\s*movie|hindi|punjabi|dubbed)\b\)?', '', clean_search, flags=re.IGNORECASE).strip()

    queries = []
    if target_year:
        queries.append(f"{clean_search} {target_year}")
    if is_series:
        queries.append(f"{search_name} Series")
        queries.append(search_name)
    else:
        queries.append(search_name)
        queries.append(clean_search)

    for q in queries:
        try:
            res = await get_movie_details(q, **kwargs) if kwargs else await get_movie_details(q)
            if res and isinstance(res, dict):
                title = res.get("title")
                res_year = res.get("year")
                if res_year and str(res_year).isdigit() and target_year:
                    if abs(int(res_year) - target_year) > 1:
                        continue
                if title and is_good_title_match(clean_search, title, query_year=target_year):
                    return res
        except Exception as e:
            logger.warning(f"Error fetching IMDb details for '{q}': {e}")

    return {}


async def fetch_tmdb_safely(tmdb_query: str, base_name: str, is_series: bool, year: Optional[str] = None) -> dict:
    if not TMDB_POSTER:
        return {}

    sig = inspect.signature(get_movie_detailsx)
    kwargs = {}
    if "is_series" in sig.parameters:
        kwargs["is_series"] = is_series
    elif "media_type" in sig.parameters:
        kwargs["media_type"] = "tv" if is_series else "movie"

    target_year = int(year) if year and str(year).isdigit() else extract_year_from_text(base_name)

    if tmdb_query and (str(tmdb_query).startswith("tt") or str(tmdb_query).isdigit()):
        try:
            res = await get_movie_detailsx(str(tmdb_query), **kwargs) if kwargs else await get_movie_detailsx(str(tmdb_query))
            if res and not res.get("error"):
                return res
        except Exception:
            pass

    clean_series = re.sub(r'\s+Season\s*\d+', '', base_name, flags=re.IGNORECASE).strip()
    clean_target = re.sub(r'\b(19|20)\d{2}\b', '', clean_series if is_series else base_name).strip()
    clean_target = re.sub(r'\(?\b(?:full\s*movie|hindi|punjabi|dubbed)\b\)?', '', clean_target, flags=re.IGNORECASE).strip()

    queries = []
    if target_year:
        queries.append(f"{clean_target} {target_year}")
    if is_series:
        if tmdb_query and tmdb_query != base_name:
            queries.append(tmdb_query)
        queries.append(clean_series)
        queries.append(f"{clean_series} Series")
    else:
        queries.append(tmdb_query or base_name)
        queries.append(clean_target)

    for q in queries:
        try:
            res = await get_movie_detailsx(q, **kwargs) if kwargs else await get_movie_detailsx(q)
            if res and not res.get("error"):
                title = res.get("title") or res.get("name")
                res_year = res.get("year")
                if res_year and str(res_year).isdigit() and target_year:
                    if abs(int(res_year) - target_year) > 1:
                        continue
                if title and is_good_title_match(clean_target, title, query_year=target_year):
                    return res
        except Exception:
            pass

    return {}


@Client.on_message(filters.command("setdomain"))
async def set_domain_handler(bot, message):
    if len(message.command) < 2:
        current_url = await get_hdhub_base_url()
        return await message.reply_text(
            f"🌐 **Current HDHub4u URL:** <code>{current_url}</code>\n\n"
            f"💡 **Gateways:** <code>{', '.join(HDHUB_PERMANENT_GATEWAYS)}</code>\n\n"
            f"💡 **Usage:** <code>/setdomain https://new-domain.com</code>"
        )
    new_url = message.command[1].strip().split("?")[0].rstrip("/")
    if not is_valid_hdhub_domain(new_url):
        return await message.reply_text("❌ Sirf pure HDHub4u domain allow hai (4K domains are blocked)!")

    try:
        await db.db.settings.update_one(
            {"_id": "hdhub_base_url"},
            {"$set": {"url": new_url}},
            upsert=True
        )
        await message.reply_text(f"✅ **HDHub4u base URL successfully updated to:**\n<code>{new_url}</code>")
    except Exception as e:
        await message.reply_text(f"❌ Failed to update domain: {e}")


# ----------------- HDHUB4U EXCLUSIVE SCRAPER (SMART CLEAN TITLE) -----------------
async def get_hdhub4u_data(base_name: str, target_year: Optional[int] = None) -> Tuple[str, str, str, bool]:
    genres = "N/A"
    rating = "N/A"
    info_url = ""
    is_series = False

    clean_search_query = re.sub(r'\b(?:season|s)\s*\d+\b', '', base_name, flags=re.IGNORECASE)
    clean_search_query = re.sub(r'\b(?:19|20)\d{2}\b', '', clean_search_query).strip()
    clean_search_query = re.sub(r'\(?\b(?:full\s*movie|hindi|punjabi|dubbed|dual\s*audio)\b\)?', '', clean_search_query, flags=re.IGNORECASE).strip()
    clean_query = normalize(clean_search_query).strip()

    search_words = [w for w in clean_query.split() if len(w) >= 2][:3]
    effective_query = "+".join(search_words) if search_words else clean_query.replace(" ", "+")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1"
    }

    html = ""
    movie_page_url = None
    matched_title = ""

    test_domains = ["https://new1.hdhub4u.free", "https://hdhub4u.bi"]
    base_cached = await get_hdhub_base_url()
    if base_cached and is_valid_hdhub_domain(base_cached) and base_cached not in test_domains:
        test_domains.insert(0, base_cached)
    for gw in HDHUB_PERMANENT_GATEWAYS:
        if gw not in test_domains and is_valid_hdhub_domain(gw):
            test_domains.append(gw)

    cookie_jar = aiohttp.CookieJar(unsafe=True)
    timeout = aiohttp.ClientTimeout(total=9)

    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
        for domain in test_domains:
            try:
                headers["Referer"] = domain
                async with session.get(domain, headers=headers, allow_redirects=True) as home_resp:
                    if home_resp.status != 200:
                        continue
                    home_html = await home_resp.text()

                    landing_soup = BeautifulSoup(home_html, "html.parser")
                    btn = (
                        landing_soup.find("a", string=re.compile(r"view\s*full\s*site", re.I))
                        or landing_soup.select_one("a.btn, a[href*='hdhub4u']")
                    )
                    if btn and btn.get("href"):
                        target_href = btn["href"].strip()
                        m = re.match(r'(https?://[^/]+)', target_href)
                        if m and is_valid_hdhub_domain(m.group(1)):
                            domain = m.group(1).rstrip("/")

                search_url = f"{domain}/?s={effective_query}"
                headers["Referer"] = domain

                async with session.get(search_url, headers=headers, allow_redirects=True) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        if hasattr(db, 'db') and is_valid_hdhub_domain(domain):
                            await db.db.settings.update_one({"_id": "hdhub_base_url"}, {"$set": {"url": domain}}, upsert=True)
                        break
            except Exception as e:
                logger.debug(f"Search failed on {domain}: {e}")
                continue

    if not html:
        return "N/A", "N/A", "", False

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["header", "nav", "footer", "aside", "script", "style", "form"]):
        tag.decompose()

    candidate_items = []
    for art in soup.select("article, .post-item, .recent-movies li, .entry-title, .thumb, h2 a, h3 a"):
        a_tag = art if art.name == "a" else art.find("a", href=True)
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href or href == "#" or any(x in href for x in ["/category/", "/tag/", "/author/", "/page/"]):
            continue
        title_text = f"{a_tag.get('title', '')} {a_tag.get_text()}".strip()
        if not re.search(r'\b(?:review|trailer|teaser|reaction)\b', title_text, re.IGNORECASE):
            candidate_items.append((title_text, href))

    target_sequel = extract_sequel_num(base_name) or extract_sequel_num(clean_query)
    target_s_match = re.search(r'\b(?:season|s)\s*0*(\d+)\b', base_name, re.IGNORECASE)
    target_season = int(target_s_match.group(1)) if target_s_match else None

    for title_text, href in candidate_items:
        clean_cand_title = re.sub(r'\(?\b(?:full\s*movie|hindi\s*dubbed|punjabi|dual\s*audio)\b\)?', '', title_text, flags=re.IGNORECASE).strip()

        cand_year = extract_year_from_text(title_text)
        if target_year and cand_year and abs(target_year - cand_year) > 1:
            continue

        cand_sequel = extract_sequel_num(clean_cand_title)
        if target_sequel != cand_sequel:
            continue

        if target_season is not None:
            cand_s_match = re.search(r'\b(?:season|s)\s*0*(\d+)\b', title_text, re.IGNORECASE)
            if cand_s_match and int(cand_s_match.group(1)) != target_season:
                continue

        if is_good_title_match(clean_query, clean_cand_title, query_year=target_year) or is_good_title_match(base_name, clean_cand_title, query_year=target_year):
            movie_page_url = href
            matched_title = title_text
            break

    if not movie_page_url:
        return "N/A", "N/A", "", False

    if re.search(r'\b(?:Season\s*\d+|S\d{1,2}|Series|Episodes?|Complete)\b', matched_title, re.IGNORECASE):
        is_series = True

    try:
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
            async with session.get(movie_page_url, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    return "N/A", "N/A", "", is_series
                movie_html = await resp.text()

        movie_soup = BeautifulSoup(movie_html, "html.parser")
        search_area = movie_soup.select_one(".entry-content, .post-content, article, .k-post-content") or movie_soup.body or movie_soup

        for a_tag in search_area.find_all("a", href=True):
            href = a_tag["href"].strip()
            m_imdb = re.search(r'(?:imdb\.com/(?:title/)?|title/)(tt\d+)', href, re.IGNORECASE)
            if m_imdb:
                info_url = f"https://www.imdb.com/title/{m_imdb.group(1)}/"
                break
            m_tmdb = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', href, re.IGNORECASE)
            if m_tmdb:
                info_url = f"https://www.themoviedb.org/{m_tmdb.group(1)}/{m_tmdb.group(2)}"
                break

        full_page_text = search_area.get_text()

        r_match = re.search(r'(?:IMDb|IMDB|Rating|Ratings|Score)\s*(?:Rating|Ratings)?\s*[:\-•.\s]*\s*([0-9](?:\.[0-9])?)\s*(?:/\s*10)?', full_page_text, re.IGNORECASE)
        if r_match:
            val = parse_clean_rating(r_match.group(1))
            if val:
                rating = val

        g_match = re.search(r'\b(?:Genre|Genres)\s*[:\-–]\s*([^\n\r]+)', full_page_text, re.IGNORECASE)
        if g_match:
            raw_g = g_match.group(1).strip()
            raw_g = re.split(r'\b(?:Release|IMDb|Rating|Language|Audio|Stars|Cast|Director|Quality|Size|Source|Format|Storyline|Screenshots?)\b', raw_g, flags=re.IGNORECASE)[0]
            parts = re.split(r'[,|/•&]', raw_g)
            clean_g = [p.strip().title() for p in parts if len(p.strip()) >= 2 and not any(bad in p.lower() for bad in ["dropdown", "download", "select", "click", "n/a"])]
            if clean_g:
                genres = ", ".join(clean_g)

    except Exception as e:
        logger.error(f"Error scraping details from HDHub4u: {e}")

    return genres, rating, info_url, is_series


def extract_season_episode(filename: str) -> Tuple[Optional[int], Optional[str]]:
    filename = AUDIO_CHANNELS_PATTERN.sub(" ", filename)

    if m := BONUS_RANGE_REGEX.search(filename):
        return int(m.group(1)), f"{int(m.group(2))}-{int(m.group(3))}"

    if m := BONUS_REGEX.search(filename):
        return int(m.group(1)), str(int(m.group(2)))

    if m := RANGE_REGEX.search(filename):
        return int(m.group(1)), f"{int(m.group(2))}-{int(m.group(3))}"

    if m := SINGLE_REGEX.search(filename):
        return int(m.group(1)), str(int(m.group(2)))

    if m := NAMED_REGEX.search(filename):
        return int(m.group(1)), str(int(m.group(2)))

    if m := X_REGEX.search(filename):
        s_val = int(m.group(1))
        ep_val = int(m.group(2))
        if ep_val not in (264, 265, 720, 1080, 480) and s_val not in (264, 265, 720, 1080):
            return s_val, str(ep_val)

    if m := DAY_REGEX.search(filename):
        season = int(m.group(1)) if m.group(1) else 1
        ep_val = m.group(2) or m.group(3)
        if ep_val:
            return season, str(int(ep_val))

    if m := NO_S_REGEX.search(filename):
        return int(m.group(1)), str(int(m.group(2)))

    s_match = re.search(r'\b(?:Season|S)\s*0*(\d{1,2})\b', filename, re.IGNORECASE)
    detected_season = int(s_match.group(1)) if s_match else 1

    if m := EP_ONLY_RANGE.search(filename):
        return detected_season, f"{int(m.group(1))}-{int(m.group(2))}"

    if m := EP_ONLY_SINGLE.search(filename):
        ep_val = int(m.group(1))
        if ep_val not in (264, 265):
            return detected_season, str(ep_val)

    return None, None


def schedule_update(bot, base_name, delay=8):
    if handle := pending_updates.get(base_name):
        if not handle.cancelled():
            handle.cancel()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    async def wrapper():
        try:
            await update_movie_message(bot, base_name)
        finally:
            pending_updates.pop(base_name, None)

    pending_updates[base_name] = loop.call_later(
        delay,
        lambda: asyncio.create_task(wrapper())
    )


def extract_media_info(filename: str, caption: str):
    filename_clean = clean_mentions_links(filename)
    filename = normalize(filename_clean.title())
    caption_clean = clean_mentions_links(caption).lower() if caption else ""
    unified = f"{caption_clean} {filename.lower()}".strip()

    season = None
    episode = None
    year = None
    tag = "#MOVIE"

    processed_raw = filename
    base_raw = filename

    quality = (
        get_qualities(caption)
        or get_qualities(filename)
        or "N/A"
    )

    ott_platform = extract_ott_platform(
        f"{filename} {caption_clean}"
    )

    lang_keys = {
        k
        for k in CAPTION_LANGUAGES
        if re.search(rf"\b{re.escape(k)}\b", unified)
    }

    language = (
        ", ".join(
            sorted(
                {
                    CAPTION_LANGUAGES[k]
                    for k in lang_keys
                }
            )
        )
        if lang_keys
        else "N/A"
    )

    season, episode = extract_season_episode(filename)

    if season is not None:
        tag = "#SERIES"

        clean_fn = AUDIO_CHANNELS_PATTERN.sub(" ", filename)
        m = (
            BONUS_RANGE_REGEX.search(clean_fn)
            or BONUS_REGEX.search(clean_fn)
            or RANGE_REGEX.search(clean_fn)
            or SINGLE_REGEX.search(clean_fn)
            or NAMED_REGEX.search(clean_fn)
            or X_REGEX.search(clean_fn)
            or DAY_REGEX.search(clean_fn)
            or NO_S_REGEX.search(clean_fn)
            or EP_ONLY_RANGE.search(clean_fn)
            or EP_ONLY_SINGLE.search(clean_fn)
        )

        if m:
            match_str = m.group(0)
            start_idx = clean_fn.lower().find(match_str.lower())
            end_idx = start_idx + len(match_str)

            processed_raw = filename[:end_idx]
            base_raw = filename[:start_idx]

            year_match = YEAR_PATTERN.search(
                filename.lower()[end_idx:]
            )

            if year_match:
                y = year_match.group(0)
                yi = filename.lower().find(y, end_idx)

                if yi != -1:
                    processed_raw = filename[:yi + 4]
                    base_raw += f" {y}"

    else:
        year_match = YEAR_PATTERN.search(unified)

        if year_match:
            year = year_match.group(0)
            year_idx = filename.lower().find(year.lower())

            if year_idx != -1:
                processed_raw = filename[:year_idx + 4]
                base_raw = processed_raw

        else:
            qual_match = SOURCE_PATTERN.search(unified) or RESOLUTION_PATTERN.search(unified)

            if qual_match:
                qual_str = qual_match.group(0)
                qual_idx = filename.lower().find(
                    qual_str.lower()
                )

                if qual_idx != -1:
                    processed_raw = filename[:qual_idx]
                    base_raw = processed_raw

    base_raw = AUDIO_CHANNELS_PATTERN.sub(" ", base_raw)

    base_name = normalize(
        remove_ignored_words(
            normalize(base_raw)
        )
    )

    if year and year not in base_name:
        base_name += f" {year}"

    if base_name.endswith(")"):
        base_name = re.sub(
            r"\s+\(\d{4}\)$",
            "",
            base_name
        )

        if year:
            base_name += f" {year}"

    def _strip_season_episode_tokens(name: str) -> str:
        if not name:
            return name

        year_match = re.search(
            r"\(?\b(19|20)\d{2}\b\)?\s*$",
            name
        )

        year_part = ""

        if year_match:
            year_part = year_match.group(0)
            name = name[:year_match.start()].strip()

        patterns = [
            r"\bS\d{1,2}[\s._-]*(?:Bonus|Special)[\s._-]*(?:E(?:p(?:isode)?)?[\s._-]*)?0*\d{1,3}\b",
            r"\b(?:Bonus|Special)[\s._-]*(?:E(?:p(?:isode)?)?[\s._-]*)?0*\d{1,3}\b",
            r"\bS\d{1,2}[\s._-]*E(?:p(?:isode)?)?[\s._-]*0*\d{1,3}\b",
            r"\bS\d{1,2}\b",
            r"\bE\d{1,3}\b",
            r"\b\d{1,2}x\d{1,3}\b",
            r"\bSeason\s*\d{1,2}\b",
            r"\bEp(?:isode)?[\s._-]*0*\d{1,3}\b",
            r"\bEpisode\s*\d{1,3}\b",
            r"\bPart\s*\d{1,2}\b",
            r"\bDay\s*\d{1,3}\b",
            r"\bBonus\b",
            r"\bSpecial\b",
            r"\b[vV]\d+\b",
            r"\b(?:version|ver)\.?\s*\d+\b",
            r"\b(?:dd|ddp|ac3|eac3|aac)?\s*[257]\s*[._]\s*[01]\b",
            r"\b(?:dd|ddp)\s*[257]\b",
            r"\bott\b"
        ]

        for p in patterns:
            name = re.sub(p, " ", name, flags=re.IGNORECASE)

        name = re.sub(r"[_\.\-]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()

        if year_part:
            y = re.search(r"(19|20)\d{2}", year_part)
            if y:
                name = f"{name} {y.group(0)}"

        return name.strip()

    base_name = _strip_season_episode_tokens(base_name)
    base_name = re.sub(r'(\b(?:19|20)\d{2}\b)(?:\s+\1)+', r'\1', base_name).strip()

    if season is not None:
        base_name = f"{base_name} Season {season}"

    if not base_name:
        base_name = (
            normalize(
                remove_ignored_words(
                    normalize(processed_raw)
                )
            )
            or filename
        )

    return {
        "processed": normalize(processed_raw),
        "base_name": base_name,
        "tag": tag,
        "season": season,
        "episode": episode,
        "year": year,
        "quality": quality,
        "ott_platform": ott_platform,
        "language": language
    }


@Client.on_message(filters.chat(CHANNELS) & MEDIA_FILTER)
async def media_handler(bot, message):
    media = next(
        (
            getattr(message, ft)
            for ft in ("document", "video", "audio")
            if getattr(message, ft, None)
        ),
        None
    )

    if not media:
        return

    duration_secs = getattr(media, "duration", None)

    if not duration_secs and message.video:
        duration_secs = message.video.duration

    if not duration_secs and message.audio:
        duration_secs = message.audio.duration

    file_runtime_mins = (
        round(duration_secs / 60)
        if duration_secs
        else None
    )

    media.file_type = next(
        ft
        for ft in ("document", "video", "audio")
        if getattr(message, ft, None)
    )

    media.caption = message.caption or ""

    success, info = await save_file(media)

    if not success:
        return

    try:
        if await db.movie_update_status(bot.me.id):
            await process_and_send_update(
                bot,
                media.file_name or message.caption or "Unknown",
                media.caption,
                file_runtime_mins
            )
    except Exception:
        logger.exception("Error processing media")


async def process_and_send_update(
    bot,
    filename,
    caption,
    file_runtime_mins=None
):
    try:
        media_info = extract_media_info(
            filename,
            caption
        )

        base_name = media_info["base_name"]
        processed = media_info["processed"]

        if not hasattr(db, "movie_updates"):
            db.movie_updates = db.db.movie_updates

        clean_title = get_clean_title(base_name)
        existing_doc = await db.movie_updates.find_one({
            "$or": [
                {"_id": base_name},
                {"clean_title": clean_title}
            ]
        })
        if existing_doc:
            base_name = existing_doc["_id"]

        lock = locks[base_name]

        async with lock:
            await _process_with_lock(
                bot,
                filename,
                caption,
                media_info,
                base_name,
                processed,
                file_runtime_mins
            )

    except PyMongoError as e:
        logger.error(f"Database error in process_and_send_update: {e}")

    except Exception as e:
        logger.exception(f"Processing failed in process_and_send_update: {e}")


async def _process_with_lock(
    bot,
    filename,
    caption,
    media_info,
    base_name,
    processed,
    file_runtime_mins=None
):
    if not hasattr(db, "movie_updates"):
        db.movie_updates = db.db.movie_updates

    clean_title = get_clean_title(base_name)
    movie_doc = await db.movie_updates.find_one(
        {"_id": base_name}
    )
    if not movie_doc:
        movie_doc = await db.movie_updates.find_one({"clean_title": clean_title})
        if movie_doc:
            base_name = movie_doc["_id"]

    is_series = media_info["tag"] == "#SERIES"
    target_year = int(media_info["year"]) if media_info.get("year") else extract_year_from_text(base_name)

    is_mismatched = False
    if movie_doc:
        stored_title = movie_doc.get("title", "")
        stored_year = movie_doc.get("year")
        if stored_title and not is_good_title_match(base_name, stored_title, query_year=target_year):
            logger.warning(f"Title/Year mismatch: '{stored_title}' ({stored_year}) vs '{base_name}' ({target_year}). Re-fetching!")
            is_mismatched = True
        elif target_year and stored_year and str(stored_year).isdigit():
            if abs(target_year - int(stored_year)) > 1:
                logger.warning(f"Old movie year conflict detected: {stored_year} vs {target_year}. Re-fetching!")
                is_mismatched = True

    error_tmdb = False

    final_file_runtime = (
        f"{file_runtime_mins}"
        if file_runtime_mins
        else "N/A"
    )

    file_data = {
        "filename": filename,
        "processed": processed,
        "quality": media_info["quality"],
        "language": media_info["language"],
        "ott_platform": media_info["ott_platform"],
        "timestamp": datetime.now(),
        "tag": media_info["tag"],
        "season": media_info["season"],
        "episode": media_info["episode"],
        "runtime": final_file_runtime
    }

    if not movie_doc or is_mismatched:
        blogger_data = await get_blogger_data(base_name, media_info.get("year"))

        hdhub_genres, hdhub_rating, hdhub_info_url, hdhub_is_series = await get_hdhub4u_data(base_name, target_year=target_year)

        if not is_series and hdhub_is_series:
            is_series = True
            media_info["tag"] = "#SERIES"
            file_data["tag"] = "#SERIES"

        tt_match = re.search(r'tt\d+', hdhub_info_url) if hdhub_info_url else None
        hdhub_imdb_id = tt_match.group(0) if tt_match else None

        tmdb_url_match = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', hdhub_info_url) if hdhub_info_url else None
        hdhub_tmdb_id = tmdb_url_match.group(2) if tmdb_url_match else None
        hdhub_tmdb_type = tmdb_url_match.group(1) if tmdb_url_match else None

        live_imdb = await fetch_imdb_live_data(base_name, target_year, direct_tt=hdhub_imdb_id)

        imdb_details = {}
        tmdb_details = {}

        if hdhub_imdb_id or live_imdb.get("imdb_id"):
            lookup_id = live_imdb.get("imdb_id") or hdhub_imdb_id
            imdb_details = await fetch_imdb_safely(lookup_id, is_series=is_series, year=media_info.get("year"))
            if not is_good_title_match(base_name, imdb_details.get("title", ""), query_year=target_year):
                imdb_details = {}

        if hdhub_tmdb_id and not imdb_details:
            tmdb_details = await fetch_tmdb_safely(hdhub_tmdb_id, base_name, is_series=(hdhub_tmdb_type == "tv" or is_series), year=media_info.get("year"))
            if tmdb_details and tmdb_details.get("imdb_id"):
                imdb_details = await fetch_imdb_safely(tmdb_details["imdb_id"], is_series=is_series, year=media_info.get("year"))

        if not imdb_details:
            imdb_details = await fetch_imdb_safely(base_name, is_series=is_series, year=media_info.get("year")) or {}

        final_lookup = live_imdb.get("imdb_id") or imdb_details.get("imdb_id") or base_name
        if not tmdb_details or tmdb_details.get("error"):
            tmdb_details = await fetch_tmdb_safely(final_lookup, base_name, is_series=is_series, year=media_info.get("year")) or {}

        if not tmdb_details or tmdb_details.get("error"):
            error_tmdb = True

        official_search_title = imdb_details.get("title") or tmdb_details.get("title") or tmdb_details.get("name") or base_name

        poster_url = ""
        is_backdrop = False

        if blogger_data.get("poster_url"):
            poster_url = blogger_data["poster_url"]
            is_backdrop = True
        elif (
            LANDSCAPE_POSTER
            and TMDB_POSTER
            and tmdb_details.get("backdrop_url")
            and not error_tmdb
        ):
            poster_url = tmdb_details.get("backdrop_url")
            is_backdrop = True
        elif (
            tmdb_details.get("poster_url")
            and not error_tmdb
        ):
            poster_url = tmdb_details.get("poster_url")
        else:
            poster_url = (
                imdb_details.get("poster_url")
                or imdb_details.get("backdrop_url", "")
            )

        # ----------------- 100% PROPER RATING SYNC -----------------
        rating = (
            parse_clean_rating(blogger_data.get("rating"))
            or parse_clean_rating(hdhub_rating)
            or parse_clean_rating(live_imdb.get("rating"))
            or parse_clean_rating(imdb_details.get("rating"))
            or parse_clean_rating(tmdb_details.get("rating"))
            or "x/10"
        )

        # ----------------- 100% ACCURATE & FULL GENRES MERGE -----------------
        # Step 1: Blogger Check
        if blogger_data.get("genres"):
            genres = blogger_data["genres"]
        # Step 2: HDHub4u Page Genres (Primary Accuracy e.g. Crime, Thriller)[span_4](start_span)[span_4](end_span)
        elif hdhub_genres and hdhub_genres != "N/A":
            genres = hdhub_genres
        # Step 3: Combine IMDb Live + Official IMDb + TMDb (No Incomplete Genres)
        else:
            merged_genre_sources = [
                live_imdb.get("genres"),
                imdb_details.get("genres"),
                tmdb_details.get("genres")
            ]
            genres = clean_and_format_genres(merged_genre_sources)

        # ----------------- PROPER IMDB / TMDB LINK -----------------
        imdb_url = (
            blogger_data.get("imdb_url")
            or live_imdb.get("imdb_url")
            or (f"https://www.imdb.com/title/{hdhub_imdb_id}/" if hdhub_imdb_id else None)
            or (f"https://www.imdb.com/title/{imdb_details.get('imdb_id')}/" if imdb_details.get("imdb_id") else None)
            or (f"https://www.imdb.com/title/{tmdb_details.get('imdb_id')}/" if (isinstance(tmdb_details, dict) and tmdb_details.get("imdb_id")) else None)
            or (f"https://www.themoviedb.org/tv/{tmdb_details.get('id')}" if is_series and tmdb_details.get("id") else None)
            or (f"https://www.themoviedb.org/movie/{tmdb_details.get('id')}" if tmdb_details.get("id") else "")
        )

        imdb_r = imdb_details.get("runtime")
        tmdb_r = (
            tmdb_details.get("episode_run_time")
            if is_series and tmdb_details.get("episode_run_time")
            else tmdb_details.get("runtime")
        )

        if isinstance(imdb_r, (list, tuple)) and imdb_r:
            imdb_r = imdb_r[0]
        if isinstance(tmdb_r, (list, tuple)) and tmdb_r:
            tmdb_r = tmdb_r[0]

        if is_series:
            if tmdb_r and str(tmdb_r).strip().upper() not in ("N/A", "NONE", "0", ""):
                runtime = str(tmdb_r).strip()
            elif final_file_runtime != "N/A":
                runtime = final_file_runtime
            elif imdb_r and str(imdb_r).strip().upper() not in ("N/A", "NONE", "0", ""):
                runtime = str(imdb_r).strip()
            else:
                runtime = "N/A"
        else:
            if imdb_r and str(imdb_r).strip().upper() not in ("N/A", "NONE", "0", ""):
                runtime = str(imdb_r).strip()
            elif tmdb_r and str(tmdb_r).strip().upper() not in ("N/A", "NONE", "0", ""):
                runtime = str(tmdb_r).strip()
            else:
                runtime = final_file_runtime if final_file_runtime != "N/A" else "N/A"

        certificates = (
            tmdb_details.get("certificates")
            if tmdb_details.get("certificates")
            and tmdb_details.get("certificates") != "N/A"
            else imdb_details.get("certificates", "N/A")
        )

        movie_year = (
            media_info.get("year")
            or (str(target_year) if target_year else None)
            or imdb_details.get("year")
            or tmdb_details.get("year")
        )

        if is_mismatched:
            update_data = {
                "title": official_search_title,
                "clean_title": clean_title,
                "poster_url": poster_url,
                "genres": genres,
                "rating": rating,
                "runtime": runtime,
                "certificates": certificates,
                "imdb_url": imdb_url,
                "year": movie_year,
                "tag": media_info["tag"],
                "ott_platform": media_info["ott_platform"],
                "error_tmdb": error_tmdb,
                "is_backdrop": is_backdrop
            }
            await db.movie_updates.update_one(
                {"_id": base_name},
                {
                    "$set": update_data,
                    "$push": {"files": file_data}
                }
            )
            schedule_update(bot, base_name)
            return

        new_doc = {
            "_id": base_name,
            "clean_title": clean_title,
            "title": official_search_title,
            "files": [file_data],
            "poster_url": poster_url,
            "genres": genres,
            "rating": rating,
            "runtime": runtime,
            "certificates": certificates,
            "imdb_url": imdb_url,
            "year": movie_year,
            "tag": media_info["tag"],
            "ott_platform": media_info["ott_platform"],
            "message_id": None,
            "is_photo": False,
            "error_tmdb": error_tmdb,
            "is_backdrop": is_backdrop
        }

        try:
            await db.movie_updates.insert_one(new_doc)
        except DuplicateKeyError:
            movie_doc = await db.movie_updates.find_one({"_id": base_name})
            if not movie_doc:
                return

            if any(f.get("filename") == filename for f in movie_doc.get("files", [])):
                return

            await db.movie_updates.update_one(
                {"_id": base_name},
                {"$push": {"files": file_data}}
            )
            schedule_update(bot, base_name)
            return

        await send_movie_update(bot, base_name)

    else:
        existing_files = movie_doc.get("files", [])
        if any(f.get("filename") == filename for f in existing_files):
            logger.info(f"Duplicate file skipped: {filename}")
            return

        update_fields = {"$push": {"files": file_data}}

        current_db_runtime = movie_doc.get("runtime")
        if (not current_db_runtime or str(current_db_runtime).strip().upper() in ("N/A", "NONE", "0", "")) and final_file_runtime != "N/A":
            update_fields.setdefault("$set", {})["runtime"] = final_file_runtime

        current_db_rating = movie_doc.get("rating")
        current_db_imdb_url = movie_doc.get("imdb_url")
        current_db_genres = movie_doc.get("genres")

        blogger_data = await get_blogger_data(base_name, media_info.get("year"))
        hdhub_genres, hdhub_rating, hdhub_info_url, _ = await get_hdhub4u_data(base_name, target_year=target_year)
        direct_tt_match = re.search(r'tt\d+', str(current_db_imdb_url or hdhub_info_url or blogger_data.get("imdb_url")))
        live_refresh = await fetch_imdb_live_data(base_name, target_year, direct_tt=direct_tt_match.group(0) if direct_tt_match else None)

        fresh_rating = parse_clean_rating(blogger_data.get("rating")) or parse_clean_rating(hdhub_rating) or parse_clean_rating(live_refresh.get("rating"))
        if fresh_rating and fresh_rating != parse_clean_rating(current_db_rating):
            update_fields.setdefault("$set", {})["rating"] = fresh_rating

        if blogger_data.get("genres"):
            update_fields.setdefault("$set", {})["genres"] = blogger_data["genres"]
        elif hdhub_genres and hdhub_genres != "N/A":
            update_fields.setdefault("$set", {})["genres"] = hdhub_genres
        elif live_refresh.get("genres") and live_refresh["genres"] != "N/A":
            update_fields.setdefault("$set", {})["genres"] = live_refresh["genres"]

        if not current_db_imdb_url:
            fresh_url = blogger_data.get("imdb_url") or live_refresh.get("imdb_url") or hdhub_info_url
            if fresh_url:
                update_fields.setdefault("$set", {})["imdb_url"] = fresh_url

        await db.movie_updates.update_one(
            {"_id": base_name},
            update_fields
        )

        schedule_update(bot, base_name)


async def send_movie_update(bot, base_name):
    if base_name in sending_updates:
        logger.warning(f"Duplicate send prevented: {base_name}")
        return None

    sending_updates.add(base_name)

    try:
        max_retries = 3

        for attempt in range(max_retries):
            try:
                movie_doc = await db.movie_updates.find_one({"_id": base_name})
                if not movie_doc:
                    return None

                existing_message_id = movie_doc.get("message_id")
                if existing_message_id:
                    logger.info(f"Movie already posted, updating instead: {base_name}")
                    await update_movie_message(bot, base_name)
                    return None

                text = generate_movie_message(movie_doc, base_name)

                all_tags = {
                    f.get("tag")
                    for f in movie_doc.get("files", [])
                    if f.get("tag")
                }

                primary_tag = "#SERIES" if "#SERIES" in all_tags else "#MOVIE"
                btn_style = enums.ButtonStyle.SUCCESS if primary_tag == "#SERIES" else enums.ButtonStyle.DANGER

                match = re.search(r'(.+?)\s+Season\s+(\d+)', base_name, re.IGNORECASE)
                if match:
                    series_name = match.group(1).strip()
                    season_num = int(match.group(2))
                    button_query = f"{series_name}-S{season_num:02d}"
                else:
                    button_query = base_name

                buttons = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "ɢᴇᴛ ғɪʟᴇs",
                            url=(
                                f"https://t.me/{temp.U_NAME}"
                                f"?start=getfile-"
                                f"{button_query.replace(' ', '-')}"
                            ),
                            style=btn_style
                        )
                    ]]
                )

                size = (
                    (2560, 1440)
                    if (
                        LANDSCAPE_POSTER
                        and TMDB_POSTER
                        and movie_doc.get("is_backdrop")
                        and not movie_doc.get("error_tmdb")
                    )
                    else (853, 1280)
                )

                poster_url = movie_doc.get("poster_url")
                is_photo = False
                msg = None

                if poster_url and not LINK_PREVIEW:
                    try:
                        resized_poster = await fetch_image(poster_url, size)
                        photo_to_send = resized_poster or poster_url
                        msg = await bot.send_photo(
                            chat_id=MOVIE_UPDATE_CHANNEL,
                            photo=photo_to_send,
                            caption=text,
                            reply_markup=buttons,
                            parse_mode=enums.ParseMode.HTML
                        )
                        is_photo = True
                    except Exception as err:
                        logger.warning(f"send_photo failed ({err}), falling back to direct URL")
                        try:
                            msg = await bot.send_photo(
                                chat_id=MOVIE_UPDATE_CHANNEL,
                                photo=poster_url,
                                caption=text,
                                reply_markup=buttons,
                                parse_mode=enums.ParseMode.HTML
                            )
                            is_photo = True
                        except Exception:
                            msg = await bot.send_message(
                                chat_id=MOVIE_UPDATE_CHANNEL,
                                text=text,
                                reply_markup=buttons,
                                parse_mode=enums.ParseMode.HTML
                            )
                            is_photo = False
                else:
                    send_params = {
                        "chat_id": MOVIE_UPDATE_CHANNEL,
                        "text": text,
                        "reply_markup": buttons,
                        "parse_mode": enums.ParseMode.HTML
                    }
                    if poster_url and LINK_PREVIEW:
                        send_params["invert_media"] = True

                    msg = await bot.send_message(**send_params)
                    is_photo = False

                await db.movie_updates.update_one(
                    {"_id": base_name, "message_id": None},
                    {"$set": {"message_id": msg.id, "is_photo": is_photo}}
                )

                logger.info(f"Movie update posted successfully: {base_name} -> {msg.id}")
                return msg

            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
            except Exception as e:
                logger.error(f"Failed to send movie update: {e}")
                break

        return None

    finally:
        sending_updates.discard(base_name)


async def update_movie_message(bot, base_name):
    try:
        movie_doc = await db.movie_updates.find_one({"_id": base_name})
        if not movie_doc:
            return

        text = generate_movie_message(movie_doc, base_name)

        all_tags = {
            f.get("tag")
            for f in movie_doc.get("files", [])
            if f.get("tag")
        }

        primary_tag = "#SERIES" if "#SERIES" in all_tags else "#MOVIE"
        btn_style = enums.ButtonStyle.SUCCESS if primary_tag == "#SERIES" else enums.ButtonStyle.DANGER

        match = re.search(r'(.+?)\s+Season\s+(\d+)', base_name, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            season_num = int(match.group(2))
            button_query = f"{series_name}-S{season_num:02d}"
        else:
            button_query = base_name

        buttons = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "ɢᴇᴛ ғɪʟᴇs",
                    url=(
                        f"https://t.me/{temp.U_NAME}"
                        f"?start=getfile-"
                        f"{button_query.replace(' ', '-')}"
                    ),
                    style=btn_style
                )
            ]]
        )

        message_id = movie_doc.get("message_id")
        is_photo = movie_doc.get("is_photo", False)

        if not message_id:
            await send_movie_update(bot, base_name)
            return

        try:
            if is_photo:
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=message_id,
                    caption=text,
                    reply_markup=buttons,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                await bot.edit_message_text(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=message_id,
                    text=text,
                    reply_markup=buttons,
                    parse_mode=enums.ParseMode.HTML,
                    invert_media=True,
                    disable_web_page_preview=not LINK_PREVIEW
                )

            logger.info(f"Movie update edited successfully: {base_name}")

        except (MessageNotModified, MessageIdInvalid):
            pass
        except Exception as e:
            logger.error(f"Error updating movie message: {e}")

    except Exception as e:
        logger.error(f"Failed to update movie message for {base_name}: {e}")


def generate_movie_message(movie_doc, base_name):
    all_raw_qualities = []
    all_languages = set()
    all_ott_platforms = set()
    all_tags = set()
    episodes_by_season = defaultdict(set)

    for file in movie_doc.get("files", []):
        if file.get("quality") and file.get("quality") != "N/A":
            all_raw_qualities.append(file.get("quality"))

        lang_val = file.get("language")
        if lang_val and lang_val != "N/A":
            for lang in lang_val.split(","):
                clean_l = lang.strip()
                if clean_l and clean_l != "N/A":
                    norm_l = CAPTION_LANGUAGES.get(clean_l.lower(), clean_l.title())
                    all_languages.add(norm_l)

        ott_val = file.get("ott_platform")
        if ott_val and ott_val != "N/A":
            for plat in ott_val.split("|"):
                clean_p = plat.strip()
                if clean_p and clean_p != "N/A":
                    norm_p = OTT_PLATFORMS.get(clean_p.lower(), clean_p)
                    all_ott_platforms.add(norm_p)

        if file.get("tag"):
            all_tags.add(file.get("tag"))

        if file.get("season") is not None and file.get("episode"):
            season = file.get("season")
            episode = str(file.get("episode"))
            episodes_by_season[season].add(episode)

    if "Disney+ Hotstar" in all_ott_platforms and "Disney+" in all_ott_platforms:
        all_ott_platforms.remove("Disney+")
    if "JioHotstar" in all_ott_platforms:
        all_ott_platforms.discard("Disney+ Hotstar")
        all_ott_platforms.discard("Disney+")
    if "HBO Max" in all_ott_platforms and "Max" in all_ott_platforms:
        all_ott_platforms.remove("Max")

    primary_tag = "#SERIES" if "#SERIES" in all_tags else "#MOVIE"
    is_series = (primary_tag == "#SERIES")

    epi_block = ""

    if episodes_by_season:
        episode_lines = []

        for season, episodes in sorted(
            episodes_by_season.items(),
            key=lambda x: int(x[0])
        ):
            regular_eps = set()

            for ep in episodes:
                ep_str = str(ep).strip()
                if not ep_str or ep_str.lower() in ("episodes", "episode"):
                    continue

                if ep_str.lower().startswith("bonus") or ep_str.lower().startswith("special"):
                    ep_str = re.sub(r'(?i)(?:bonus|special)\s*', '', ep_str).strip()

                if "-" in ep_str:
                    try:
                        p1, p2 = ep_str.split("-")
                        regular_eps.update(range(int(p1), int(p2) + 1))
                    except ValueError:
                        pass
                elif ep_str.isdigit():
                    regular_eps.add(int(ep_str))

            def collapse_range(num_set):
                sorted_nums = sorted(num_set)
                if not sorted_nums:
                    return []
                collapsed = []
                start = end = sorted_nums[0]
                for num in sorted_nums[1:]:
                    if num == end + 1:
                        end = num
                    else:
                        collapsed.append(str(start) if start == end else f"{start}-{end}")
                        start = end = num
                collapsed.append(str(start) if start == end else f"{start}-{end}")
                return collapsed

            line_parts = []
            reg_list = collapse_range(regular_eps)
            if reg_list:
                line_parts.append(", ".join(reg_list))

            if line_parts:
                episode_lines.append(f"S{int(season)}: {', '.join(line_parts)}")

        epi_str = "\n".join(episode_lines)
        if epi_str:
            epi_block = f"\n📺 ᴇᴘɪsᴏᴅᴇs : <b>{epi_str}</b>"

    genres = movie_doc.get("genres", "N/A")
    quality_str = format_movie_qualities(all_raw_qualities)
    language_str = ", ".join(sorted(all_languages)) if all_languages else "N/A"
    ott_str = " | ".join(sorted(all_ott_platforms)) if all_ott_platforms else "N/A"

    raw_rating = str(movie_doc.get("rating", "x/10")).strip()
    imdb_url = movie_doc.get("imdb_url", "")

    if raw_rating.lower() in ("x/10", "x", "n/a", "-", "none", "", "0", "0.0", "null"):
        rating_display = "<small>x/10</small>"
    else:
        clean_rating = raw_rating.replace("/10", "").strip()
        rating_display = f"<small>{clean_rating}/10</small>"

    if imdb_url:
        rating_text = f'<a href="{imdb_url}">{rating_display}</a>'
    else:
        rating_text = rating_display

    raw_runtime = movie_doc.get("runtime", "N/A")
    runtime = format_runtime(raw_runtime, is_series=is_series)
    certificates = movie_doc.get("certificates", "N/A")

    stored_title = movie_doc.get("title", base_name)
    stored_title = re.sub(r'[:,]?\s*(?:Episode|Ep)\s*\d+.*', '', stored_title, flags=re.IGNORECASE).strip()
    stored_title = re.sub(r'["\']', '', stored_title).strip()

    display_title = re.sub(r'\s+Season\s*\d+', '', stored_title, flags=re.IGNORECASE).strip()
    display_title = re.sub(r'\s+S\d+', '', display_title, flags=re.IGNORECASE).strip()
    display_title = display_title.strip(" :,-\"'")

    movie_year = movie_doc.get("year")

    if movie_year and str(movie_year) not in str(display_title) and primary_tag != "#SERIES":
        filename_display = f"{display_title} {movie_year}"
    else:
        filename_display = display_title

    raw_text = script.MOVIE_UPDATE_NOTIFY_TXT.format(
        poster_url=movie_doc.get("poster_url", ""),
        imdb_url=imdb_url,
        filename=filename_display,
        tag=primary_tag,
        genres=genres,
        ott=ott_str,
        runtime=runtime,
        certificates=certificates,
        quality=quality_str,
        language=language_str,
        episodes=epi_block,
        rating=rating_text,
        search_link=temp.B_LINK
    )

    return "\n".join(
        line.strip()
        for line in raw_text.splitlines()
    )


# ----------------- BACKGROUND RATING & GENRES AUTO-SYNC -----------------
async def update_all_movie_ratings(bot: Client):
    try:
        if not hasattr(db, "movie_updates"):
            db.movie_updates = db.db.movie_updates

        cursor = db.movie_updates.find({})
        async for doc in cursor:
            base_name = doc["_id"]
            current_rating = doc.get("rating")
            current_genres = doc.get("genres")
            imdb_url = doc.get("imdb_url", "")
            target_year = extract_year_from_text(base_name)

            blogger_data = await get_blogger_data(base_name, str(target_year) if target_year else None)
            hdhub_genres, hdhub_rating, hdhub_url, _ = await get_hdhub4u_data(base_name, target_year=target_year)

            tt_match = re.search(r'tt\d+', f"{imdb_url} {hdhub_url} {blogger_data.get('imdb_url', '')}")
            live_res = await fetch_imdb_live_data(base_name, year=target_year, direct_tt=tt_match.group(0) if tt_match else None)

            new_rating = parse_clean_rating(blogger_data.get("rating")) or parse_clean_rating(hdhub_rating) or parse_clean_rating(live_res.get("rating"))

            update_payload = {}
            if new_rating and new_rating != parse_clean_rating(current_rating):
                update_payload["rating"] = new_rating

            if blogger_data.get("genres"):
                update_payload["genres"] = blogger_data["genres"]
            elif hdhub_genres and hdhub_genres != "N/A" and (not current_genres or current_genres == "N/A" or "Biography" in current_genres):
                update_payload["genres"] = hdhub_genres
            elif live_res.get("genres") and live_res["genres"] != "N/A" and (not current_genres or current_genres == "N/A"):
                update_payload["genres"] = live_res["genres"]

            if update_payload:
                logger.info(f"⚡ Live Metadata updated for {base_name}: {update_payload}")
                await db.movie_updates.update_one(
                    {"_id": base_name},
                    {"$set": update_payload}
                )
                await update_movie_message(bot, base_name)
                await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"Error in background rating updater: {e}")
