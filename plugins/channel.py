import re
import json
import logging
import asyncio
import aiohttp
import inspect
from datetime import datetime
from bs4 import BeautifulSoup
from collections import defaultdict
from plugins.Dreamxfutures.Imdbposter import get_movie_detailsx, fetch_image, get_movie_details
from database.users_chats_db import db
from pyrogram import Client, filters, enums
from info import CHANNELS, MOVIE_UPDATE_CHANNEL, LINK_PREVIEW, ABOVE_PREVIEW, BAD_WORDS, LANDSCAPE_POSTER, TMDB_POSTER
from Script import script
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from utils import temp
from pymongo.errors import PyMongoError, DuplicateKeyError
from pyrogram.errors import MessageIdInvalid, MessageNotModified, FloodWait
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_BASE_IGNORE_WORDS = {
    "rarbg", "dub", "sub", "sample", "mkv", "mp4", "avi", "aac", "ac3", "eac3", "ddp", "ddp5", "atmos", "dts",
    "combined", "esub", "msub", "proper", "repack", "unrated", "extended", "imax", "remux", "10bit", "10-bit",
    "x264", "x265", "h264", "h265", "hevc", "avc", "dovi", "hdr", "hdr10",
    "web", "dl", "bonus", "special",
    "action", "adventure", "animation", "biography", "comedy", "crime",
    "documentary", "drama", "fantasy", "film-noir", "history",
    "horror", "music", "musical", "mystery", "romance", "sci-fi", "sport",
    "thriller", "war", "western", "hdcam", "hdtc", "camrip", "cam", "ts", "tc", "hdts",
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

BONUS_RANGE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Bonus|Special)[\s._-]*E(?:p(?:isode)?)?0*(\d{1,3})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?)?0*(\d{1,3})\b', re.IGNORECASE)
BONUS_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Bonus|Special)[\s._-]*E(?:p(?:isode)?)?0*(\d{1,3})\b', re.IGNORECASE)
RANGE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Part)?[\s._-]*E(?:p(?:isode)?)?0*(\d{1,3})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?)?0*(\d{1,3})', re.IGNORECASE)
SINGLE_REGEX = re.compile(r'\bS(\d{1,2})[\s._-]*(?:Part)?[\s._-]*E(?:p(?:isode)?)?0*(\d{1,3})\b', re.IGNORECASE)
NAMED_REGEX = re.compile(r'Season\s*0*(\d{1,2})[\s\-,:]*(?:Part)?[\s\-,:]*Ep(?:isode)?\s*0*(\d{1,3})\b', re.IGNORECASE)
X_REGEX = re.compile(r'(?<!\d)\b0*([1-9]\d?)\s*[xX]\s*0*([1-9]\d?)\b(?!\d)', re.IGNORECASE)
DAY_REGEX = re.compile(r'\b(?:S(?:eason)?\s*0*(\d{1,2})[\s._-]*)?(?:Day\s*0*(\d{1,3})|D0*([1-9]\d{0,2}))\b', re.IGNORECASE)
NO_S_REGEX = re.compile(r'\b(?:Season|S)\s*0*(\d{1,2})[\s._-]+E(?:p(?:isode)?)?0*(\d{1,3})\b', re.IGNORECASE)
EP_ONLY_RANGE = re.compile(r'\b(?:EP|Episode)0*(\d{1,3})\s*-\s*0*(\d{1,3})\b', re.IGNORECASE)
EP_ONLY_SINGLE = re.compile(r'\b(?:EP|Episode)\.?\s*0*(\d{1,3})\b', re.IGNORECASE)

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


def is_good_title_match(query: str, found_title: str) -> bool:
    if not query or not found_title:
        return False

    q_raw = YEAR_PATTERN.sub('', query).strip()
    f_raw = YEAR_PATTERN.sub('', found_title).strip()

    def clean_words(s: str):
        s = re.sub(r'\(?\b(?:full\s*movie|full\s*series|full\s*film|hd|rip|dubbed)\b\)?', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^(the|a|an)\s+', '', s, flags=re.IGNORECASE)
        s = re.sub(r"['’]", "", s)
        s = normalize(s).lower()
        return [w for w in s.split() if w]

    q_words = clean_words(q_raw)
    f_words = clean_words(f_raw)

    if not q_words or not f_words:
        return False

    if q_words == f_words:
        return True

    if len(q_words) == 1:
        return q_words == f_words

    if all(qw in f_words for qw in q_words):
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
            source_list.append(version_str)

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
    t = re.sub(r'\b(19|20)\d{2}\b', '', name)
    return normalize(t).lower()


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


async def fetch_imdb_safely(base_name: str, is_series: bool, year: Optional[str] = None) -> dict:
    sig = inspect.signature(get_movie_details)
    kwargs = {}
    if "is_series" in sig.parameters:
        kwargs["is_series"] = is_series
    elif "media_type" in sig.parameters:
        kwargs["media_type"] = "tv" if is_series else "movie"

    queries = []
    if is_series:
        if year:
            queries.append(f"{base_name} {year}")
        queries.append(f"{base_name} Series")
        queries.append(f"{base_name} TV")
        queries.append(base_name)
    else:
        if year:
            queries.append(f"{base_name} {year}")
        queries.append(base_name)

    best_fallback = {}
    for q in queries:
        try:
            res = await get_movie_details(q, **kwargs) if kwargs else await get_movie_details(q)
            if res and isinstance(res, dict):
                title = res.get("title")
                if title and is_good_title_match(base_name, title):
                    return res
                if not best_fallback and res:
                    best_fallback = res
        except Exception as e:
            logger.warning(f"Error fetching IMDb details for '{q}': {e}")

    return best_fallback


async def fetch_tmdb_safely(tmdb_query: str, base_name: str, is_series: bool) -> dict:
    if not TMDB_POSTER:
        return {}

    sig = inspect.signature(get_movie_detailsx)
    kwargs = {}
    if "is_series" in sig.parameters:
        kwargs["is_series"] = is_series
    elif "media_type" in sig.parameters:
        kwargs["media_type"] = "tv" if is_series else "movie"

    if tmdb_query:
        if str(tmdb_query).startswith("tt") or str(tmdb_query).isdigit():
            try:
                res = await get_movie_detailsx(tmdb_query, **kwargs) if kwargs else await get_movie_detailsx(tmdb_query)
                if res and not res.get("error"):
                    return res
            except Exception:
                pass

    queries = []
    if is_series:
        queries.append(f"{base_name} Series")
        queries.append(base_name)
    else:
        queries.append(tmdb_query or base_name)

    best_fallback = {}
    for q in queries:
        try:
            res = await get_movie_detailsx(q, **kwargs) if kwargs else await get_movie_detailsx(q)
            if res and not res.get("error"):
                title = res.get("title") or res.get("name")
                if title and is_good_title_match(base_name, title):
                    return res
                if not best_fallback:
                    best_fallback = res
        except Exception:
            pass

    return best_fallback


async def get_blogger_data(base_name: str, year: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    try:
        blog_url = "https://tmdbimdbhdhub4u.blogspot.com"
        if hasattr(db, 'db'):
            setting = await db.db.settings.find_one({"_id": "blogger_base_url"})
            if setting and setting.get("url"):
                blog_url = setting["url"].rstrip("/")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        timeout = aiohttp.ClientTimeout(total=10)

        def clean_core(s):
            if not s:
                return ""
            s = re.sub(r'[\(\)\[\]#\-:_.]', ' ', s)
            s = re.sub(r'\b(?:Season\s*\d+|S\d{1,2}|Complete|Part\s*\d+)\b', ' ', s, flags=re.IGNORECASE)
            s = re.sub(r'\b(19|20)\d{2}\b', ' ', s)
            return re.sub(r'[^a-zA-Z0-9]', '', s).lower().strip()

        target_core = clean_core(base_name)
        if not target_core:
            return None, None

        # Main keywords extract karo (e.g. 'doraemon', 'castle', 'undersea')
        words = [w.lower() for w in re.split(r'[\s\-:_.()]+', base_name) if len(w) >= 3 and not w.isdigit()]
        simple_search = "+".join(words[:2]) if words else target_core

        candidate_urls = []

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            # Step A: Direct Feed Fetch (Recent 50 Posts)
            feed_url = f"{blog_url}/feeds/posts/default?alt=json&max-results=50"
            try:
                async with session.get(feed_url) as f_resp:
                    if f_resp.status == 200:
                        f_text = await f_resp.text()
                        f_data = json.loads(f_text)
                        for entry in f_data.get("feed", {}).get("entry", []):
                            p_title = entry.get("title", {}).get("$t", "")
                            p_core = clean_core(p_title)
                            
                            # Token match check taaki New/No-New confuse na kare
                            p_words = [w.lower() for w in re.split(r'[\s\-:_.()]+', p_title) if len(w) >= 3 and not w.isdigit()]
                            match_count = sum(1 for w in words if w in p_words or w in p_core)
                            
                            if (p_core in target_core) or (target_core in p_core) or (match_count >= 2):
                                for l in entry.get("link", []):
                                    if l.get("rel") == "alternate":
                                        candidate_urls.append(l.get("href"))
                                        break
            except Exception as fe:
                logger.warning(f"Error fetching Blogger feed: {fe}")

            # Step B: Direct Blogger search page parse agar feed me match na ho
            if not candidate_urls and simple_search:
                search_page_url = f"{blog_url}/search?q={simple_search}"
                try:
                    async with session.get(search_page_url) as s_resp:
                        if s_resp.status == 200:
                            s_html = await s_resp.text()
                            s_soup = BeautifulSoup(s_html, "html.parser")
                            for a_elem in s_soup.find_all("a", href=True):
                                h = a_elem["href"].split("?")[0]
                                title_attr = (a_elem.get("title") or a_elem.get_text() or "").strip()
                                if h.startswith(blog_url) and h.endswith(".html"):
                                    if target_core in clean_core(h) or (title_attr and target_core in clean_core(title_attr)):
                                        if h not in candidate_urls:
                                            candidate_urls.append(h)
                except Exception as se:
                    logger.warning(f"Error fetching Blogger search page: {se}")

            if not candidate_urls:
                logger.warning(f"Blogger me koi post nahi mili target: '{base_name}' ke liye")
                return None, None

            # Step C: Post Open karke Poster + Hyperlink Extract Karo
            for post_url in candidate_urls:
                try:
                    async with session.get(post_url) as p_resp:
                        if p_resp.status != 200:
                            continue
                        post_html = await p_resp.text()
                        post_soup = BeautifulSoup(post_html, "html.parser")

                        img_url = None
                        target_url = None

                        # Check 1: Image ke upar wrap hua hyperlink <a href="IMDB_TMDB"><img src="POSTER"></a>
                        for a_tag in post_soup.find_all("a", href=True):
                            href = a_tag["href"].strip()
                            inner_img = a_tag.find("img")
                            if inner_img:
                                src = inner_img.get("src") or inner_img.get("data-src")
                                if src and not any(x in src.lower() for x in ["icon", "avatar", "blank.gif"]):
                                    img_url = src.strip()
                                    if re.search(r'imdb\.com/title/(tt\d+)', href, re.IGNORECASE) or re.search(r'themoviedb\.org/(?:movie|tv)/\d+', href, re.IGNORECASE):
                                        target_url = href
                                        break

                        # Check 2: Standalone <img> agar <a> ke bahar ho
                        if not img_url:
                            for im in post_soup.find_all("img"):
                                src = im.get("src") or im.get("data-src")
                                if src and not any(x in src.lower() for x in ["icon", "avatar", "blank.gif"]):
                                    img_url = src.strip()
                                    break

                        # Check 3: Post body me kahin bhi target movie URL dhoondo
                        if not target_url:
                            for a_tag in post_soup.find_all("a", href=True):
                                href = a_tag["href"].strip()
                                if re.search(r'imdb\.com/title/(tt\d+)', href, re.IGNORECASE) or re.search(r'themoviedb\.org/(?:movie|tv)/\d+', href, re.IGNORECASE):
                                    target_url = href
                                    break

                        # Google CDN original high-res formatting
                        if img_url:
                            img_url = re.sub(r'/s\d+(-c)?/', '/s1600/', img_url)
                            img_url = re.sub(r'/w\d+-h\d+(-c)?/', '/s1600/', img_url)
                            img_url = re.sub(r'=s\d+(-c)?', '=s1600', img_url)
                            img_url = re.sub(r'=w\d+-h\d+(-c)?', '=s1600', img_url)

                            logger.info(f"Blogger Post Matched! URL: '{post_url}' | Poster: {bool(img_url)} | Target URL: {target_url}")
                            return img_url, target_url
                except Exception as err:
                    logger.warning(f"Error parsing post {post_url}: {err}")

    except Exception as e:
        logger.error(f"Error fetching Blogger data: {e}")
    return None, None


def extract_season_episode(filename: str) -> Tuple[Optional[int], Optional[str]]:
    filename = AUDIO_CHANNELS_PATTERN.sub(" ", filename)

    if m := BONUS_RANGE_REGEX.search(filename):
        return int(m.group(1)), f"Bonus {int(m.group(2))}-{int(m.group(3))}"

    if m := BONUS_REGEX.search(filename):
        return int(m.group(1)), f"Bonus {int(m.group(2))}"

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

    if m := EP_ONLY_RANGE.search(filename):
        return 1, f"{int(m.group(1))}-{int(m.group(2))}"

    if m := EP_ONLY_SINGLE.search(filename):
        ep_val = int(m.group(1))
        if ep_val not in (264, 265):
            return 1, str(ep_val)

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
            r"\bS\d{1,2}[\s._-]*(?:Bonus|Special)[\s._-]*E(?:p(?:isode)?)?0*\d{1,3}\b",
            r"\b(?:Bonus|Special)[\s._-]*Ep(?:isode)?\.?\s*\d{1,3}\b",
            r"\bS\d{1,2}E\d{1,3}\b",
            r"\bS\d{1,2}\b",
            r"\bE\d{1,3}\b",
            r"\b\d{1,2}x\d{1,3}\b",
            r"\bSeason\s*\d{1,2}\b",
            r"\bEp(?:isode)?\.?\s*\d{1,3}\b",
            r"\bEpisode\s*\d{1,3}\b",
            r"\bPart\s*\d{1,2}\b",
            r"\bDay\s*\d{1,3}\b",
            r"\bBonus\b",
            r"\bSpecial\b",
            r"\b[vV]\d+\b",
            r"\b(?:version|ver)\.?\s*\d+\b",
            r"\b(?:dd|ddp|ac3|eac3|aac)?\s*[257]\s*[._]\s*[01]\b",
            r"\b(?:dd|ddp)\s*[257]\b"
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
    movie_doc = await db.movie_updates.find_one({"_id": base_name})
    if not movie_doc:
        movie_doc = await db.movie_updates.find_one({"clean_title": clean_title})
        if movie_doc:
            base_name = movie_doc["_id"]

    is_series = media_info["tag"] == "#SERIES"

    is_mismatched = False
    if movie_doc:
        stored_title = movie_doc.get("title", "")
        if stored_title and not is_good_title_match(base_name, stored_title):
            logger.warning(f"Title mismatch detected: '{stored_title}' for '{base_name}'. Re-fetching!")
            is_mismatched = True

        # Agar purana message Blogger se nahi tha, dobara Blogger check karein
        if not movie_doc.get("from_blogger"):
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
        # STEP 1: SABSE PEHLE BLOGGER CHECK KARO
        blogger_poster_url, blogger_info_url = await get_blogger_data(base_name, media_info.get("year"))

        blogger_is_imdb = False
        blogger_is_tmdb = False
        blogger_imdb_id = None
        blogger_tmdb_id = None

        if blogger_info_url:
            m_imdb = re.search(r'tt\d+', blogger_info_url)
            m_tmdb = re.search(r'themoviedb\.org/(?:movie|tv)/(\d+)', blogger_info_url)
            if m_imdb:
                blogger_is_imdb = True
                blogger_imdb_id = m_imdb.group(0)
            elif m_tmdb:
                blogger_is_tmdb = True
                blogger_tmdb_id = m_tmdb.group(1)

        imdb_details = {}
        tmdb_details = {}

        # STRICT SOURCE PRIORITY
        if blogger_is_imdb and blogger_imdb_id:
            try:
                imdb_details = await get_movie_details(blogger_imdb_id) or {}
            except Exception:
                pass
            official_search_title = imdb_details.get("title", base_name)
            imdb_id = blogger_imdb_id

        elif blogger_is_tmdb and blogger_tmdb_id:
            tmdb_details = await fetch_tmdb_safely(blogger_tmdb_id, base_name, is_series) or {}
            # Anime/Foreign films ke liye localized (English) title prefer karein
            official_search_title = (
                tmdb_details.get("localized_title")
                or tmdb_details.get("title")
                or tmdb_details.get("name")
                or base_name
            )
            imdb_id = tmdb_details.get("imdb_id")

        else:
            imdb_details = await fetch_imdb_safely(
                base_name,
                is_series=is_series,
                year=media_info.get("year")
            ) or {}

            official_search_title = imdb_details.get("title", base_name)
            imdb_id = imdb_details.get("imdb_id")

            tmdb_query = imdb_id if (imdb_id and imdb_id.startswith("tt")) else official_search_title
            tmdb_details = await fetch_tmdb_safely(tmdb_query, base_name, is_series)

        if not tmdb_details or tmdb_details.get("error"):
            error_tmdb = True

        poster_url = ""
        is_backdrop = False

        if blogger_poster_url:
            poster_url = blogger_poster_url
            is_backdrop = True
        elif (
            LANDSCAPE_POSTER
            and TMDB_POSTER
            and tmdb_details.get("backdrop_url")
            and not error_tmdb
        ):
            poster_url = tmdb_details.get("backdrop_url")
            is_backdrop = True
        elif tmdb_details.get("poster_url") and not error_tmdb:
            poster_url = tmdb_details.get("poster_url")
            is_backdrop = False
        else:
            poster_url = (
                imdb_details.get("poster_url")
                or imdb_details.get("backdrop_url", "")
            )
            is_backdrop = bool(imdb_details.get("backdrop_url"))

        # EXACT RATING HANDLING
        rating = "x/10"
        if blogger_is_tmdb and tmdb_details.get("rating"):
            rating = str(tmdb_details.get("rating")).strip()
        elif blogger_is_imdb and imdb_details.get("rating"):
            rating = str(imdb_details.get("rating")).strip()
        else:
            imdb_rate = imdb_details.get("rating")
            tmdb_rate = tmdb_details.get("rating")
            if tmdb_rate and str(tmdb_rate).strip().upper() not in ("N/A", "NONE", "0", "0.0", "-", ""):
                rating = str(tmdb_rate).strip()
            elif imdb_rate and str(imdb_rate).strip().upper() not in ("N/A", "NONE", "0", "0.0", "-", ""):
                rating = str(imdb_rate).strip()

        # EXACT TARGET URL HANDLING
        imdb_url = ""
        if blogger_info_url:
            imdb_url = blogger_info_url.strip()
        else:
            final_imdb_id = imdb_id or (tmdb_details.get("imdb_id") if isinstance(tmdb_details, dict) else None)
            if final_imdb_id and str(final_imdb_id).startswith("tt"):
                imdb_url = f"https://www.imdb.com/title/{final_imdb_id}/"
            elif is_series and tmdb_details.get("id"):
                imdb_url = f"https://www.themoviedb.org/tv/{tmdb_details.get('id')}"
            elif tmdb_details.get("id"):
                imdb_url = f"https://www.themoviedb.org/movie/{tmdb_details.get('id')}"

        genre_list = []
        raw_genres = None

        if blogger_is_tmdb:
            raw_genres = tmdb_details.get("genres")
        elif blogger_is_imdb:
            raw_genres = imdb_details.get("genres")
        else:
            raw_genres = tmdb_details.get("genres") or imdb_details.get("genres")

        if isinstance(raw_genres, list):
            for g in raw_genres:
                if isinstance(g, dict) and g.get("name"):
                    genre_list.append(str(g["name"]).strip().title())
                elif isinstance(g, str):
                    genre_list.append(g.strip().title())
        elif isinstance(raw_genres, str) and raw_genres != "N/A":
            genre_list = [g.strip().title() for g in raw_genres.split(",") if g.strip()]

        genres = ", ".join(genre_list) if genre_list else "N/A
