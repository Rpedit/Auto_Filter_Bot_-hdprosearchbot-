import re
import asyncio
import aiohttp
import warnings
import logging
from io import BytesIO
from datetime import datetime
from collections import defaultdict
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, MAX_LIST_ELM, TMDB_API_KEY

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
    try:
        data = await get_movie_details(query, id=id, file=file)
        if data:
            return data
    except Exception as e:
        logger.error(f"IMDb direct fetch failed: {e}")
    return None

async def _fetch_tmdb_data(query, api_key=None):
    key = api_key or TMDB_API_KEY
    if not key:
        return None
    try:
        session = await get_session()
        url = f"https://api.themoviedb.org/3/search/multi?api_key={key}&query={aiohttp.helpers.quote(query)}"
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            res = await resp.json()
            results = res.get('results', [])
            if not results:
                return None
            item = next((r for r in results if r.get('media_type') in ['movie', 'tv']), results[0])
            media_type = item.get('media_type') or ('tv' if 'name' in item else 'movie')
            tmdb_id = item.get('id')
            if not tmdb_id:
                return None
            
            detail_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={key}&append_to_response=images"
            async with session.get(detail_url) as d_resp:
                if d_resp.status != 200:
                    return None
                d_data = await d_resp.json()
                
                images = d_data.get('images', {})
                backdrops_raw = images.get('backdrops', [])
                posters_raw = images.get('posters', [])
                
                backdrops = defaultdict(list)
                for b in backdrops_raw:
                    iso = b.get('iso_639_1') or 'no_lang'
                    path = b.get('file_path')
                    if path:
                        backdrops[iso].append(f"https://image.tmdb.org/t/p/original{path}")
                        
                posters = defaultdict(list)
                for p in posters_raw:
                    iso = p.get('iso_639_1') or 'no_lang'
                    path = p.get('file_path')
                    if path:
                        posters[iso].append(f"https://image.tmdb.org/t/p/original{path}")
                        
                poster_path = d_data.get('poster_path')
                poster_url = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else None
                
                return {
                    'title': d_data.get('title') or d_data.get('name'),
                    'localized_title': d_data.get('original_title') or d_data.get('original_name'),
                    'year': (d_data.get('release_date') or d_data.get('first_air_date') or '')[:4],
                    'rating': str(d_data.get('vote_average', '0.0')),
                    'images': {
                        'backdrops': dict(backdrops),
                        'posters': dict(posters),
                        'original_language': d_data.get('original_language')
                    },
                    'poster_url': poster_url
                }
    except Exception as e:
        logger.error(f"TMDB API data fetch error: {e}")
    return None

async def get_tmdb_details(query, api_key=None):
    """Fetch TMDB landscape backdrop for the query."""
    q = str(query).strip()
    try:
        data = await _fetch_tmdb_data(q, api_key=api_key)
        if data:
            details = {}
            details['title'] = data.get('title') or data.get('localized_title')
            details['year'] = data.get('year')
            details['rating'] = data.get('rating')
            
            backdrops = data.get('images', {}).get('backdrops', {})
            original_language = data.get('images', {}).get('original_language')
            backdrop_url = None
            for key in ('en', original_language, 'xx', 'no_lang'):
                if key and backdrops.get(key):
                    backdrop_url = backdrops[key][0]
                    break
            if not backdrop_url and backdrops:
                for lang_list in backdrops.values():
                    if lang_list:
                        backdrop_url = lang_list[0]
                        break
                        
            details['backdrop_url'] = backdrop_url.replace("/original/", "/w1280/") if backdrop_url else None
            
            posters = data.get('images', {}).get('posters', {})
            poster_url = data.get('poster_url')
            if not poster_url:
                for key in ('en', original_language, 'xx'):
                    if key and posters.get(key):
                        poster_url = posters[key][0]
                        break
            details['poster_url'] = poster_url.replace("/original/", "/w1280/") if poster_url else None
            return details
    except Exception as e:
        logger.error(f"TMDB backdrop fetch error: {e}")
    return None
