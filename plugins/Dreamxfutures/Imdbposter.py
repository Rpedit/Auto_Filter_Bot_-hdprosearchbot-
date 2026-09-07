import re
import asyncio
import aiohttp
import warnings
import logging
from io import BytesIO
from datetime import datetime
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, MAX_LIST_ELM

logger = logging.getLogger(__name__)

LONG_IMDB_DESCRIPTION = False

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

_session: aiohttp.ClientSession | None = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
    return _session

async def fetch_image(url, size=(860, 1200)):
    if not DREAMXBOTZ_IMAGE_FETCH:
        logger.info("Image fetching is disabled.")
        return url

    try:
        session = await get_session()
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch image: {response.status} for {url}")
                return None

            data = await response.read()
            img = Image.open(BytesIO(data))
            img = img.resize(size, Image.LANCZOS)

            out = BytesIO()
            img.save(out, format="JPEG")
            out.seek(0)
            return out
    except Exception as e:
        logger.error(f"Error in fetch_image: {e}")
    return None

async def close_session():
    if _session and not _session.closed:
        await _session.close()

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""

async def get_movie_details(query, bulk=False, id=False, file=None):
    from utils import listx_to_str, imdb
    q_str = str(query).strip()
    
    if not id:
        query_lower = q_str.lower()
        title = query_lower
        year_val = None
        
        year_list = re.findall(r'[1-2]\d{3}$', query_lower, re.IGNORECASE)
        if year_list:
            year_val = year_list[0]
            title = (query_lower.replace(year_val, "")).strip()
        elif file is not None:
            year_list = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year_list:
                year_val = year_list[0]
        
        search_result = await asyncio.to_thread(imdb.search_movie, title.lower())
        if not search_result or not search_result.titles:
            return None
        
        movie_list = search_result.titles[:MAX_LIST_ELM]
        
        if year_val:
            filtered = [m for m in movie_list if m.year and str(m.year) == str(year_val)]
            if not filtered:
                filtered = movie_list
        else:
            filtered = movie_list
            
        kind_filter = ['movie', 'tv series', 'tvSeries', 'tvMiniSeries', 'tvMovie']
        filtered_kind = [m for m in filtered if m.kind and m.kind in kind_filter]
        
        if not filtered_kind:
            filtered_kind = filtered
        
        if bulk:
            return filtered_kind[:MAX_LIST_ELM]
        if not filtered_kind:
            return None   
        movie_brief = filtered_kind[0]
        movieid_str = movie_brief.imdb_id 
    else:
        movieid_str = query

    movie = await asyncio.to_thread(imdb.get_movie, movieid_str)
    if not movie:
        return None

    if movie.release_date:
        date = movie.release_date
    elif movie.year:
        date = str(movie.year)
    else:
        date = "N/A"
        
    plot = movie.plot[0] if isinstance(movie.plot, list) else movie.plot or ""
    if len(plot) > 800:
        plot = plot[:800] + "..."
        
    imdb_id = movie.imdb_id
    if not imdb_id.startswith("tt"):
        imdb_id = f"tt{imdb_id}"
        
    cover_url = getattr(movie, 'cover_url', None)
    poster_url = cover_url.split("._V1_")[0] + "._V1_SX1280.jpg" if cover_url and "._V1_" in cover_url else cover_url

    genres_raw = listx_to_str(movie.genres)
    genres_list = [s.strip() for s in genres_raw.split(',')] if genres_raw else []

    return {
        'title': getattr(movie, 'title', 'N/A'),
        'votes': getattr(movie, 'votes', 0),
        "aka": listx_to_str(getattr(movie, 'title_akas', [])),
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": getattr(movie, 'worldwide_gross', 'N/A'),
        'localized_title': getattr(movie, 'title_localized', 'N/A'),
        'kind': getattr(movie, 'kind', 'movie'),
        "imdb_id": imdb_id,
        "cast": listx_to_str(getattr(movie, 'stars', [])),
        "runtime": listx_to_str(getattr(movie, 'duration', [])),
        "countries": listx_to_str(getattr(movie, 'countries', [])),
        "certificates": listx_to_str(getattr(movie, 'certificates', [])),
        "languages": listx_to_str(getattr(movie, 'languages', [])),
        "director": listx_to_str(getattr(movie, 'directors', [])),
        "writer": listx_to_str([p.name for p in getattr(movie, 'writers', [])]),
        "producer": listx_to_str([p.name for p in getattr(movie, 'producers', [])]),
        "composer": listx_to_str([p.name for p in getattr(movie, 'composers', [])]),
        "cinematographer": listx_to_str([p.name for p in getattr(movie, 'cinematographers', [])]),
        'release_date': date,
        'year': getattr(movie, 'year', None),
        'genres': genres_list,
        'poster': cover_url,
        'poster_url': poster_url,
        'plot': plot,
        'rating': str(getattr(movie, 'rating', '0.0')),
        "url": getattr(movie, 'url', None) or f"https://www.imdb.com/title/{imdb_id}",
        'error': False
    }

async def get_movie_detailsx(query, id=False, file=None):
    """
    Primary movie & series details fetcher using IMDb directly to ensure correct years and sorting.
    """
    try:
        data = await get_movie_details(query, id=id, file=file)
        if data:
            return data
    except Exception as e:
        logger.error(f"IMDb direct fetch failed: {e}")
    return None
