import re
import logging
import asyncio
import aiohttp
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

_BASE_IGNORE_WORDS = {
    "rarbg", "dub", "sub", "sample", "mkv", "mp4", "avi", "aac", "ac3", "eac3", "ddp", "ddp5", "atmos", "dts",
    "combined", "esub", "msub", "proper", "repack", "unrated", "extended", "imax", "remux", "10bit",
    "x264", "x265", "h264", "h265", "hevc", "avc", "dovi", "hdr", "hdr10",
    "action", "adventure", "animation", "biography", "comedy", "crime",
    "documentary", "drama", "fantasy", "film-noir", "history",
    "horror", "music", "musical", "mystery", "romance", "sci-fi", "sport",
    "thriller", "war", "western", "hdcam", "hdtc", "camrip", "cam", "ts", "tc", "hdts",
    "telesync", "dvdscr", "dvdrip", "predvd", "webrip", "web-dl", "tvrip",
    "hdtv", "web dl", "webdl", "bluray", "brrip", "bdrip", "360p", "480p",
    "720p", "1080p", "2160p", "4k", "1440p", "540p", "240p", "140p",
    "hdrip", "hq-hdrip", "hq-hdtc",
    "hin", "hindi", "tam", "tamil", "kan", "kannada", "tel", "telugu",
    "mal", "malayalam", "eng", "english", "pun", "punjabi", "ben", "bengali",
    "mar", "marathi", "guj", "gujarati", "urd", "urdu", "kor", "korean", "jpn",
    "japanese", "bho", "bhojpuri", "ori", "odia", "oriya", "asm", "assamese",
    "spa", "spanish", "fre", "french", "fra", "ger", "german", "deu", "ita", "italian",
    "rus", "russian", "chi", "chinese", "zho", "tha", "thai", "ind", "indonesian",
    "dual", "multi", "audio",
    "nf", "netflix", "sonyliv", "sony", "sliv", "amzn", "prime",
    "primevideo", "hotstar", "zee5", "jio", "jhs", "aha", "hbo", "paramount",
    "apple", "atv", "atvp", "appletv", "hoichoi", "sunnxt", "viki", "cr", "crunchyroll", "hulu",
    "disney", "dnp", "lionsgate", "lionsgateplay", "peacock", "max", "alt",
    "altbalaji", "altt", "shemaroo", "shemaroome", "chaupal", "stage",
    "planetmarathi", "manorama", "manoramamax", "tubi"
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
    "hq audio": "HQ Audio", "hq-audio": "HQ Audio"
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

STANDARD_GENRES = {
    "Action", "Adventure", "Animation", "Biography", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "Film-Noir", "History", "Horror", "Music",
    "Musical", "Mystery", "Romance", "Sci-Fi", "Sport", "Thriller", "War", "Western", "Anime",
    "Reality", "Reality-TV", "Game Show", "Talk-Show", "Reality TV", "Reality Show"
}

GENRE_MAPPING = {
    "Science Fiction": "Sci-Fi",
    "Action & Adventure": "Action",
    "Sci-Fi & Fantasy": "Sci-Fi",
    "Reality-TV": "Reality TV"
}

CLEAN_PATTERN = re.compile(r'@[^ \n\r\t\.,:;!?()\[\]{}<>\\/"\'=_%]+|\bwww\.[^\s\]\)]+|\([\@^]+\)|\[[\@^]+\]')
NORMALIZE_PATTERN = re.compile(r"[._]+|[()\[\]{}:;'–!,.?_]")
QUALITY_PATTERN = re.compile(
    r"\b(?:HDCam|HD-Cam|HDTC|HD-TC|HQ-HDTC|CamRip|CAM|TS|HDTS|TC|TeleSync|DVDScr|DVDRip|PreDVD|"
    r"WEBRip|WEB-DL|TVRip|HDTV|WEB DL|WebDl|BluRay|BRRip|BDRip|Remux|IMAX|"
    r"360p|480p|720p|1080p|2160p|4K|1440p|540p|240p|140p|HEVC|10Bit|HDRip|HQ-HDRip|HDR10\+|HDR10|HDR|DV|DoVi)\b",
    re.IGNORECASE
)
YEAR_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?![A-Za-z0-9])")
RANGE_REGEX = re.compile(
    r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,3})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?)?0*(\d{1,3})',
    re.IGNORECASE
)
SINGLE_REGEX = re.compile(
    r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,3})',
    re.IGNORECASE
)
NAMED_REGEX = re.compile(
    r'Season\s*0*(\d{1,2})[\s\-,:]*Ep(?:isode)?\s*0*(\d{1,3})',
    re.IGNORECASE
)
EP_ONLY_RANGE = re.compile(
    r'\b(?:EP|Episode)0*(\d{1,3})\s*-\s*0*(\d{1,3})\b',
    re.IGNORECASE
)

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


def get_qualities(text: str) -> str:
    qualities = QUALITY_PATTERN.findall(text)
    return ", ".join(qualities) if qualities else "N/A"


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


def format_runtime(runtime_val):
    if not runtime_val or runtime_val == "N/A":
        return "N/A"

    if isinstance(runtime_val, (list, tuple)):
        if not runtime_val:
            return "N/A"
        runtime_val = runtime_val[0]

    runtime_str = str(runtime_val).strip()
    numbers = re.findall(r"\d+", runtime_str)

    if not numbers:
        return runtime_str

    try:
        if (
            len(numbers) >= 2
            and (
                "hr" in runtime_str.lower()
                or "hour" in runtime_str.lower()
                or re.search(r"\bh\b", runtime_str.lower())
            )
        ):
            total_mins = int(numbers[0]) * 60 + int(numbers[1])
        else:
            total_mins = int(numbers[0])
    except ValueError:
        return runtime_str

    if total_mins >= 60:
        hours = total_mins // 60
        mins = total_mins % 60
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"

    return f"{total_mins}m"


# --- DYNAMIC DOMAIN FUNCTIONS (NO HARDCODED LINK) ---
async def get_hdhub_base_url() -> Optional[str]:
    try:
        if not hasattr(db, 'db'):
            return None
        setting = await db.db.settings.find_one({"_id": "hdhub_base_url"})
        if setting and setting.get("url"):
            return setting["url"]
    except Exception:
        pass
    return None


@Client.on_message(filters.command("setdomain"))
async def set_domain_handler(bot, message):
    if len(message.command) < 2:
        current_url = await get_hdhub_base_url()
        current_text = f"<code>{current_url}</code>" if current_url else "<i>Not Set Yet!</i>"
        return await message.reply_text(
            f"🌐 **Current HDHub4u URL:** {current_text}\n\n"
            f"💡 **Usage:** <code>/setdomain https://new-domain.com/</code>"
        )
    new_url = message.command[1].strip()
    try:
        await db.db.settings.update_one(
            {"_id": "hdhub_base_url"},
            {"$set": {"url": new_url}},
            upsert=True
        )
        await message.reply_text(f"✅ **HDHub4u base URL successfully updated to:**\n<code>{new_url}</code>")
    except Exception as e:
        await message.reply_text(f"❌ Failed to update domain: {e}")


async def get_hdhub4u_genres(base_name: str) -> str:
    try:
        base_url = await get_hdhub_base_url()
        if not base_url:
            return "N/A"

        clean_query = re.sub(r"\b(19|20)\d{2}\b", "", base_name).strip()
        search_url = f"{base_url.rstrip('/')}/?s={clean_query.replace(' ', '+')}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers=headers, timeout=8) as resp:
                if resp.status != 200:
                    return "N/A"
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        result_item = soup.select_one(
            ".archive-posts h2 a, .post-item a, article a, .entry-title a"
        )

        if not result_item or not result_item.get("href"):
            return "N/A"

        movie_page_url = result_item["href"]

        async with aiohttp.ClientSession() as session:
            async with session.get(movie_page_url, headers=headers, timeout=8) as resp:
                if resp.status != 200:
                    return "N/A"
                movie_html = await resp.text()

        movie_soup = BeautifulSoup(movie_html, "html.parser")
        genres = []

        for p in movie_soup.find_all(["p", "div", "span"]):
            text = p.text.strip()

            if text.lower().startswith("genre") or "genres:" in text.lower():
                parts = text.split(":")

                if len(parts) > 1:
                    genres = [
                        g.strip()
                        for g in parts[1].split(",")
                        if g.strip()
                    ]
                    break

        if not genres:
            cat_links = movie_soup.select(
                ".cat-links a, .genres a, .entry-category a"
            )
            genres = [
                c.text.strip()
                for c in cat_links
                if c.text.strip()
            ]

        if genres:
            return ", ".join(genres)

    except Exception as e:
        logger.error(f"Error scraping HDHub4u genres: {e}")

    return "N/A"


def extract_season_episode(filename: str) -> Tuple[Optional[int], Optional[str]]:
    if m := EP_ONLY_RANGE.search(filename):
        return 1, f"{int(m.group(1))}-{int(m.group(2))}"

    for pattern in (RANGE_REGEX, SINGLE_REGEX, NAMED_REGEX):
        if m := pattern.search(filename):
            season = int(m.group(1))

            if pattern == RANGE_REGEX:
                episode = f"{int(m.group(2))}-{int(m.group(3))}"
            else:
                episode = str(int(m.group(2)))

            return season, episode

    return None, None


def schedule_update(bot, base_name, delay=5):
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
    filename = normalize(clean_mentions_links(filename).title())
    caption_clean = clean_mentions_links(caption).lower() if caption else ""
    unified = f"{caption_clean} {filename.lower()}".strip()

    season = None
    episode = None
    year = None
    tag = "#MOVIE"

    processed_raw = filename
    base_raw = filename

    quality = (
        get_qualities(caption_clean)
        or get_qualities(filename.lower())
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

        m = (
            RANGE_REGEX.search(filename)
            or SINGLE_REGEX.search(filename)
            or NAMED_REGEX.search(filename)
            or EP_ONLY_RANGE.search(filename)
        )

        if m:
            match_str = m.group(0)
            start_idx = filename.lower().find(match_str.lower())
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
            qual_match = QUALITY_PATTERN.search(unified)

            if qual_match:
                qual_str = qual_match.group(0)
                qual_idx = filename.lower().find(
                    qual_str.lower()
                )

                if qual_idx != -1:
                    processed_raw = filename[:qual_idx]
                    base_raw = processed_raw

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
            r"\bS\d{1,2}E\d{1,3}\b",
            r"\bS\d{1,2}\b",
            r"\bE\d{1,3}\b",
            r"\b\d{1,2}x\d{1,3}\b",
            r"\bSeason\s*\d{1,2}\b",
            r"\bEp(?:isode)?\.?\s*\d{1,3}\b",
            r"\bEpisode\s*\d{1,3}\b",
            r"\bPart\s*\d{1,2}\b"
        ]

        for p in patterns:
            name = re.sub(
                p,
                " ",
                name,
                flags=re.IGNORECASE
            )

        name = re.sub(
            r"[_\.\-]+",
            " ",
            name
        )

        name = re.sub(
            r"\s+",
            " ",
            name
        ).strip()

        if year_part:
            y = re.search(
                r"(19|20)\d{2}",
                year_part
            )

            if y:
                name = f"{name} {y.group(0)}"

        return name.strip()

    base_name = _strip_season_episode_tokens(base_name)

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
                media.file_name,
                media.caption,
                file_runtime_mins
            )
    except Exception:
        logger.exception(
            "Error processing media"
        )


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
        logger.error(
            f"Database error in process_and_send_update: {e}"
        )

    except Exception as e:
        logger.exception(
            f"Processing failed in process_and_send_update: {e}"
        )


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

    if not movie_doc:
        tmdb_details = {}

        if TMDB_POSTER:
            tmdb_details = await get_movie_detailsx(
                base_name
            ) or {}

            if (
                not tmdb_details
                or tmdb_details.get("error")
            ):
                error_tmdb = True

        imdb_details = await get_movie_details(
            base_name
        ) or {}

        poster_url = ""
        is_backdrop = False

        if (
            LANDSCAPE_POSTER
            and TMDB_POSTER
            and tmdb_details.get("backdrop_url")
            and not error_tmdb
        ):
            poster_url = tmdb_details.get(
                "backdrop_url"
            )
            is_backdrop = True

        elif (
            tmdb_details.get("poster_url")
            and not error_tmdb
        ):
            poster_url = tmdb_details.get(
                "poster_url"
            )

        else:
            poster_url = (
                imdb_details.get("poster_url")
                or imdb_details.get("backdrop_url", "")
            )

        rating = (
            imdb_details.get("rating")
            if imdb_details.get("rating")
            and imdb_details.get("rating") != "N/A"
            else tmdb_details.get("rating", "N/A")
        )

        imdb_url = (
            imdb_details.get("url")
            if imdb_details.get("url")
            else tmdb_details.get("tmdb_url", "")
        )

        runtime = (
            final_file_runtime
            if final_file_runtime != "N/A"
            else (
                tmdb_details.get("runtime")
                if tmdb_details.get("runtime")
                and tmdb_details.get("runtime") != "N/A"
                else imdb_details.get("runtime", "N/A")
            )
        )

        certificates = (
            tmdb_details.get("certificates")
            if tmdb_details.get("certificates")
            and tmdb_details.get("certificates") != "N/A"
            else imdb_details.get(
                "certificates",
                "N/A"
            )
        )

        raw_genres = (
            tmdb_details.get("genres")
            or imdb_details.get("genres", "N/A")
        )

        genre_names = []

        if (
            isinstance(raw_genres, str)
            and raw_genres != "N/A"
        ):
            genre_names = [
                g.strip()
                for g in raw_genres.split(",")
                if g.strip()
                and g.strip() != "N/A"
            ]

        elif isinstance(
            raw_genres,
            (list, tuple)
        ):
            for g in raw_genres:
                if isinstance(g, dict):
                    name = (
                        g.get("name")
                        or g.get("genre")
                    )

                    if name:
                        genre_names.append(
                            str(name).strip()
                        )

                elif isinstance(g, str):
                    genre_names.append(
                        g.strip()
                    )

                else:
                    name = str(g).strip()

                    if name:
                        genre_names.append(name)

        if not genre_names:
            hdhub_genres = await get_hdhub4u_genres(
                base_name
            )

            if hdhub_genres != "N/A":
                genre_names = [
                    g.strip()
                    for g in hdhub_genres.split(",")
                    if g.strip()
                ]

        genre_list = [
            GENRE_MAPPING.get(g, g)
            for g in genre_names
            if g in STANDARD_GENRES
            or g in GENRE_MAPPING
        ]

        if not genre_list and genre_names:
            genre_list = genre_names

        genres = (
            ", ".join(genre_list)
            if genre_list
            else "N/A"
        )

        movie_doc = {
            "_id": base_name,
            "clean_title": clean_title,
            "files": [file_data],
            "poster_url": poster_url,
            "genres": genres,
            "rating": rating,
            "runtime": runtime,
            "certificates": certificates,
            "imdb_url": imdb_url,
            "year": (
                tmdb_details.get("year")
                or imdb_details.get("year")
                or media_info["year"]
            ),
            "tag": media_info["tag"],
            "ott_platform": media_info["ott_platform"],
            "message_id": None,
            "is_photo": False,
            "error_tmdb": error_tmdb,
            "is_backdrop": is_backdrop
        }

        try:
            await db.movie_updates.insert_one(
                movie_doc
            )

        except DuplicateKeyError:
            movie_doc = await db.movie_updates.find_one(
                {"_id": base_name}
            )

            if not movie_doc:
                return

            if any(
                f.get("filename") == filename
                for f in movie_doc.get("files", [])
            ):
                return

            await db.movie_updates.update_one(
                {"_id": base_name},
                {
                    "$push": {
                        "files": file_data
                    }
                }
            )

            schedule_update(
                bot,
                base_name
            )
            return

        await send_movie_update(
            bot,
            base_name
        )

    else:
        existing_files = movie_doc.get(
            "files",
            []
        )

        if any(
            f.get("filename") == filename
            for f in existing_files
        ):
            logger.info(
                f"Duplicate file skipped: {filename}"
            )
            return

        update_fields = {
            "$push": {
                "files": file_data
            }
        }

        if final_file_runtime != "N/A":
            update_fields["$set"] = {
                "runtime": final_file_runtime
            }

        await db.movie_updates.update_one(
            {"_id": base_name},
            update_fields
        )

        schedule_update(
            bot,
            base_name
        )


async def send_movie_update(bot, base_name):
    if base_name in sending_updates:
        logger.warning(
            f"Duplicate send prevented: {base_name}"
        )
        return None

    sending_updates.add(base_name)

    try:
        max_retries = 3

        for attempt in range(max_retries):
            try:
                movie_doc = await db.movie_updates.find_one(
                    {"_id": base_name}
                )

                if not movie_doc:
                    return None

                existing_message_id = movie_doc.get(
                    "message_id"
                )

                if existing_message_id:
                    logger.info(
                        f"Movie already posted, updating instead: {base_name}"
                    )
                    await update_movie_message(
                        bot,
                        base_name
                    )
                    return None

                text = generate_movie_message(
                    movie_doc,
                    base_name
                )

                all_tags = {
                    f.get("tag")
                    for f in movie_doc.get("files", [])
                    if f.get("tag")
                }

                primary_tag = (
                    "#SERIES"
                    if "#SERIES" in all_tags
                    else "#MOVIE"
                )

                btn_style = (
                    enums.ButtonStyle.SUCCESS
                    if primary_tag == "#SERIES"
                    else enums.ButtonStyle.DANGER
                )

                buttons = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "ɢᴇᴛ ғɪʟᴇs",
                            url=(
                                f"https://t.me/{temp.U_NAME}"
                                f"?start=getfile-"
                                f"{base_name.replace(' ', '-')}"
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
                    else
                    (853, 1280)
                )

                if (
                    movie_doc.get("poster_url")
                    and not LINK_PREVIEW
                ):
                    resized_poster = await fetch_image(
                        movie_doc["poster_url"],
                        size
                    )

                    if resized_poster:
                        msg = await bot.send_photo(
                            chat_id=MOVIE_UPDATE_CHANNEL,
                            photo=resized_poster,
                            caption=text,
                            reply_markup=buttons,
                            parse_mode=enums.ParseMode.HTML
                        )

                        is_photo = True

                    else:
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

                    if (
                        movie_doc.get("poster_url")
                        and LINK_PREVIEW
                    ):
                        send_params["invert_media"] = ABOVE_PREVIEW

                    msg = await bot.send_message(
                        **send_params
                    )

                    is_photo = False

                await db.movie_updates.update_one(
                    {
                        "_id": base_name,
                        "message_id": None
                    },
                    {
                        "$set": {
                            "message_id": msg.id,
                            "is_photo": is_photo
                        }
                    }
                )

                logger.info(
                    f"Movie update posted successfully: {base_name} -> {msg.id}"
                )

                return msg

            except FloodWait as e:
                wait_time = e.value + 2
                await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(
                    f"Failed to send movie update: {e}"
                )
                break

        return None

    finally:
        sending_updates.discard(base_name)


async def update_movie_message(bot, base_name):
    try:
        movie_doc = await db.movie_updates.find_one(
            {"_id": base_name}
        )

        if not movie_doc:
            return

        text = generate_movie_message(
            movie_doc,
            base_name
        )

        all_tags = {
            f.get("tag")
            for f in movie_doc.get("files", [])
            if f.get("tag")
        }

        primary_tag = (
            "#SERIES"
            if "#SERIES" in all_tags
            else "#MOVIE"
        )

        btn_style = (
            enums.ButtonStyle.SUCCESS
            if primary_tag == "#SERIES"
            else enums.ButtonStyle.DANGER
        )

        buttons = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "ɢᴇᴛ ғɪʟᴇs",
                    url=(
                        f"https://t.me/{temp.U_NAME}"
                        f"?start=getfile-"
                        f"{base_name.replace(' ', '-')}"
                    ),
                    style=btn_style
                )
            ]]
        )

        message_id = movie_doc.get(
            "message_id"
        )

        is_photo = movie_doc.get(
            "is_photo",
            False
        )

        if not message_id:
            await send_movie_update(
                bot,
                base_name
            )
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
                    invert_media=ABOVE_PREVIEW,
                    disable_web_page_preview=not LINK_PREVIEW
                )

            logger.info(
                f"Movie update edited successfully: {base_name}"
            )

        except MessageNotModified:
            logger.info(
                f"Movie message unchanged: {base_name}"
            )

        except MessageIdInvalid:
            logger.warning(
                f"Invalid movie message ID: {base_name}"
            )

            await db.movie_updates.update_one(
                {"_id": base_name},
                {
                    "$set": {
                        "message_id": None
                    }
                }
            )

            await send_movie_update(
                bot,
                base_name
            )

        except Exception as e:
            logger.error(
                f"Error updating movie message: {e}"
            )

    except Exception as e:
        logger.error(
            f"Failed to update movie message for {base_name}: {e}"
        )


def generate_movie_message(movie_doc, base_name):
    all_qualities = set()
    all_languages = set()
    all_ott_platforms = set()
    all_tags = set()
    episodes_by_season = defaultdict(set)

    for file in movie_doc.get("files", []):
        if file.get("quality") != "N/A":
            all_qualities.update(
                q.strip()
                for q in file.get("quality", "").split(",")
                if q.strip()
            )

        if file.get("language") != "N/A":
            all_languages.update(
                lang.strip()
                for lang in file.get("language", "").split(",")
                if lang.strip()
            )

        if file.get("ott_platform") != "N/A":
            platforms = [
                p.strip()
                for p in file.get("ott_platform", "").split("|")
                if p.strip()
            ]

            all_ott_platforms.update(
                platforms
            )

        if file.get("tag"):
            all_tags.add(
                file.get("tag")
            )

        if (
            file.get("season") is not None
            and file.get("episode")
        ):
            season = file.get("season")
            episode = str(
                file.get("episode")
            )

            episodes_by_season[
                season
            ].add(episode)

    primary_tag = (
        "#SERIES"
        if "#SERIES" in all_tags
        else "#MOVIE"
    )

    epi_block = ""

    if episodes_by_season:
        episode_lines = []

        for season, episodes in sorted(
            episodes_by_season.items(),
            key=lambda x: int(x[0])
        ):
            singles = []
            ranges = []

            for ep in episodes:
                if "-" in ep:
                    ranges.append(ep)
                else:
                    try:
                        singles.append(
                            int(ep)
                        )
                    except ValueError:
                        ranges.append(ep)

            singles.sort()

            collapsed = []
            start = None
            end = None

            for num in singles:
                if start is None:
                    start = end = num

                elif num == end + 1:
                    end = num

                else:
                    collapsed.append(
                        str(start)
                        if start == end
                        else f"{start}-{end}"
                    )

                    start = end = num

            if start is not None:
                collapsed.append(
                    str(start)
                    if start == end
                    else f"{start}-{end}"
                )

            all_ep_parts = (
                collapsed
                + sorted(
                    ranges,
                    key=lambda s: int(
                        s.split("-")[0]
                    )
                )
            )

            episode_lines.append(
                f"S{int(season)}: "
                f"{', '.join(all_ep_parts)}"
            )

        epi_str = "\n".join(
            episode_lines
        )

        if epi_str:
            epi_block = (
                f"\n📺 ᴇᴘɪsᴏᴅᴇs : "
                f"<b>{epi_str}</b>"
            )

    genres = movie_doc.get(
        "genres",
        "N/A"
    )

    quality_str = (
        ", ".join(
            sorted(all_qualities)
        )
        if all_qualities
        else "N/A"
    )

    language_str = (
        ", ".join(
            sorted(all_languages)
        )
        if all_languages
        else "N/A"
    )

    ott_str = (
        ", ".join(
            sorted(all_ott_platforms)
        )
        if all_ott_platforms
        else "N/A"
    )

    raw_rating = movie_doc.get(
        "rating",
        "-"
    )

    imdb_url = movie_doc.get(
        "imdb_url",
        ""
    )

    try:
        r = float(
            str(raw_rating)
            .replace("/10", "")
            .strip()
        )
    except (TypeError, ValueError):
        r = 0.0

    invalid_ratings = {
        "N/A",
        "-",
        "NONE",
        "",
        "0",
        "0.0",
        "NULL"
    }

    is_invalid = (
        r == 0.0
        or not raw_rating
        or str(raw_rating)
        .strip()
        .upper()
        in invalid_ratings
    )

    if is_invalid:
        rating_display = "<small>x/10</small>"
    else:
        clean_rating = (
            str(raw_rating)
            .replace("/10", "")
            .strip()
        )

        rating_display = (
            f"<small>{clean_rating}/10</small>"
        )

    if imdb_url:
        rating_text = (
            f'<a href="{imdb_url}">'
            f"{rating_display}"
            f"</a>"
        )
    else:
        rating_text = rating_display

    raw_runtime = movie_doc.get(
        "runtime",
        "N/A"
    )

    runtime = format_runtime(
        raw_runtime
    )

    certificates = movie_doc.get(
        "certificates",
        "N/A"
    )

    filename_display = base_name

    raw_text = script.MOVIE_UPDATE_NOTIFY_TXT.format(
        poster_url=movie_doc.get(
            "poster_url",
            ""
        ),
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
