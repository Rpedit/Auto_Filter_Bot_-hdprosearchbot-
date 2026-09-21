import os
import re
import logging
import aiohttp
from bs4 import BeautifulSoup
from typing import Optional, Tuple
from database.users_chats_db import db

try:
    from info import HDHUB_DOMAIN
except ImportError:
    HDHUB_DOMAIN = os.environ.get("HDHUB_DOMAIN", "https://new6.hdhub4u.cl")

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?![A-Za-z0-9])")
NORMALIZE_PATTERN = re.compile(r"[._]+|[()\[\]{}:;'–!,.?_]")


def normalize(s: str) -> str:
    s = NORMALIZE_PATTERN.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_good_title_match(query: str, found_title: str) -> bool:
    if not query or not found_title:
        return False

    q_raw = YEAR_PATTERN.sub('', query).strip()
    f_raw = YEAR_PATTERN.sub('', found_title).strip()

    def clean_words(s: str):
        s = re.sub(r'\(?\b(?:full\s*movie|full\s*film|hd|rip|dubbed)\b\)?', '', s, flags=re.IGNORECASE)
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

    for sep in [':', '-', '–', '—', '|']:
        if sep in f_raw:
            main_part = f_raw.split(sep)[0].strip()
            main_words = clean_words(main_part)
            if q_words == main_words:
                return True

    if len(f_words) >= len(q_words):
        if f_words[:len(q_words)] == q_words:
            extra_words = f_words[len(q_words):]
            allowed_extra = {
                "tv", "series", "hindi", "telugu", "tamil", "kannada", 
                "malayalam", "korea", "korean", "ott", "season", "show",
                "full", "movie", "movies", "film", "dubbed", "dual", "org"
            }
            if set(extra_words).issubset(allowed_extra) or not extra_words:
                return True

    return False


async def get_hdhub_base_url() -> Optional[str]:
    # 1. MongoDB check karega (agar /setdomain use kiya ho)
    try:
        if hasattr(db, 'db'):
            setting = await db.db.settings.find_one({"_id": "hdhub_base_url"})
            if setting and setting.get("url"):
                return setting["url"].rstrip("/")
    except Exception:
        pass

    # 2. Koyeb Environment Variable ya info.py se lega
    env_domain = os.environ.get("HDHUB_DOMAIN") or HDHUB_DOMAIN
    if env_domain:
        return env_domain.strip().rstrip("/")

    return None


async def get_hdhub4u_data(base_name: str) -> Tuple[str, str, str]:
    genres = "N/A"
    rating = "N/A"
    imdb_url = ""
    try:
        base_url = await get_hdhub_base_url()
        if not base_url:
            return "N/A", "N/A", ""

        clean_search_query = re.sub(r'\b(season|s)\s*\d+\b', '', base_name, flags=re.IGNORECASE)
        clean_query = re.sub(r"\b(19|20)\d{2}\b", "", clean_search_query).strip()
        clean_query = re.sub(r"[._]+|[()\[\]{}:;'–!,.?_]", " ", clean_query).strip()
        search_url = f"{base_url.rstrip('/')}/?s={clean_query.replace(' ', '+')}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(search_url, headers=headers) as resp:
                if resp.status != 200:
                    return "N/A", "N/A", ""
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["header", "nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        for widget in soup.select(".sidebar, #sidebar, .widget, .trending, .slider, .carousel, .featured"):
            widget.decompose()

        candidate_links = soup.select(
            "h2 a, h3 a, .entry-title a, .archive-posts h2 a, .recent-movies a, .blog-posts a, article a, .post-item a"
        )

        movie_page_url = None
        for a in candidate_links:
            title_text = f"{a.get('title', '')} {a.get_text()}".strip()
            href = a.get("href", "")
            if not href or href == "#" or any(x in href for x in ["/category/", "/tag/", "/author/", "/page/", "/wp-content/"]):
                continue

            if is_good_title_match(clean_query, title_text) or is_good_title_match(base_name, title_text):
                movie_page_url = href
                break

        if not movie_page_url:
            clean_q = re.sub(r"['’]", "", clean_query).lower()
            query_words = [re.sub(r'[^a-zA-Z0-9]', '', w).lower() for w in clean_q.split()]
            query_words = [w for w in query_words if len(w) >= 3]

            def match_word(qw, target):
                if qw in target:
                    return True
                if qw.endswith('s') and qw[:-1] in target:
                    return True
                return False

            for a in candidate_links:
                title_text = f"{a.get('title', '')} {a.get_text()}".lower()
                href = a.get("href", "")
                if not href or href == "#" or any(x in href for x in ["/category/", "/tag/", "/author/", "/page/", "/wp-content/"]):
                    continue
                clean_target = re.sub(r"['’]", "", title_text).lower()
                if (clean_q in clean_target) or (
                    query_words and all(match_word(w, clean_target) for w in query_words)
                ):
                    movie_page_url = href
                    break

        if not movie_page_url:
            return "N/A", "N/A", ""

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(movie_page_url, headers=headers) as resp:
                if resp.status != 200:
                    return "N/A", "N/A", ""
                movie_html = await resp.text()

        movie_soup = BeautifulSoup(movie_html, "html.parser")

        for tag in movie_soup(["header", "nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        for widget in movie_soup.select(".sidebar, #sidebar, .widget, .related-posts, .comments"):
            widget.decompose()

        content = movie_soup.select_one(".entry-content, .post-content, article, .k-post-content")
        search_area = content if content else movie_soup

        for a_tag in search_area.find_all("a", href=True):
            href = a_tag["href"].strip()
            if "imdb.com/title/tt" in href:
                clean_match = re.search(r'https?://(?:www\.)?imdb\.com/title/(tt\d+)/?', href)
                if clean_match:
                    imdb_url = f"https://www.imdb.com/title/{clean_match.group(1)}/"
                    break

        for elem in search_area.find_all(["p", "div", "span", "strong", "b", "h4"]):
            text = elem.get_text(" ", strip=True)

            if genres == "N/A" and re.search(r'\b(?:Genre|Genres)\b', text, re.IGNORECASE):
                m = re.search(r'\b(?:Genre|Genres)\s*[:\-]\s*([^\n\r]+)', text, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    candidate = re.split(
                        r'\b(?:Release|IMDb|Rating|Language|Audio|Stars|Cast|Director|Quality|Size|Source|Format|Storyline|Info|Trailer|Screenshot|Screenshots|Synopsis|Plot)\b',
                        candidate, flags=re.IGNORECASE
                    )[0]
                    candidate = re.sub(r'["\'<>{}[\]\\]', '', candidate)
                    parts = re.split(r'[,|/•]', candidate)
                    cleaned = []
                    for p in parts:
                        p_val = re.sub(r'\b(?:info|trailer)\b', '', p, flags=re.IGNORECASE).strip()
                        if p_val and 2 <= len(p_val) <= 30 and not any(
                            bad in p_val.lower() for bad in ["dropdown", "menu", "select", "category", "home", "search", "click", "download"]
                        ):
                            cleaned.append(p_val)
                    if cleaned:
                        genres = ", ".join(cleaned)

            if rating == "N/A" and re.search(r'\b(?:IMDb|IMDB|Rating)\b', text, re.IGNORECASE):
                r_match = re.search(
                    r'\b(?:IMDb|IMDB|iMDB|Rating|Ratings)\s*(?:Rating|Ratings)?\s*[:\-•.\s]*\s*([0-9]+(?:\.[0-9]+)?|[xX]|N/?A)\s*(?:/\s*10)?',
                    text,
                    re.IGNORECASE
                )
                if r_match:
                    raw_val = r_match.group(1).strip()
                    if raw_val.lower() in ("x", "n/a", "na"):
                        rating = "x/10"
                    else:
                        try:
                            val = float(raw_val)
                            if 0.0 < val <= 10.0:
                                rating = f"{val:.1f}"
                        except ValueError:
                            rating = "x/10"

        if genres == "N/A":
            cat_links = search_area.select(".cat-links a, a[rel='category tag'], .entry-category a, .genres a")
            ignored_cats = {
                "uncategorized", "movies", "web series", "bollywood",
                "hollywood", "dual audio", "hindi dubbed", "tv shows",
                "720p", "480p", "1080p", "hevc", "south hindi", "series", "dropdown", "info", "trailer"
            }
            extracted_genres = [
                c.text.strip()
                for c in cat_links
                if c.text.strip() and c.text.strip().lower() not in ignored_cats and "<" not in c.text and ">" not in c.text
            ]
            if extracted_genres:
                genres = ", ".join(extracted_genres)

    except Exception as e:
        logger.error(f"Error scraping HDHub4u data: {e}")

    return genres, rating, imdb_url
