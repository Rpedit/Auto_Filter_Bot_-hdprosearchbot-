import re
import asyncio
import aiohttp
import warnings
import logging
from io import BytesIO
from datetime import datetime
from difflib import SequenceMatcher
from PIL import Image
from info import DREAMXBOTZ_IMAGE_FETCH, TMDB_API_KEY, MAX_LIST_ELM

logger = logging.getLogger(__name__)

LONG_IMDB_DESCRIPTION = False

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

# --- TMDB Configuration ---
TMDB_BEARER_TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI2ZGU3YTIyZGU1YjE5YTFjNmUyZGU5ZWEyMzE2ZmQxMCIsIm5iZiI6MTc0NSMyMjQ2Mi41MzMsInN1YiI6IjY4MDc4MWRlYzVjODAzNWZiMDhhNjExNCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.rMMJ2-PBIv8Y7ybxPIEpIlzTEXzuwrm9ruKxAUCAsbw'
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/original'
MIN_RUNTIME = 40

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

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error in fetch_image: {e}")
    except IOError as e:
        logger.error(f"I/O error in fetch_image: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_image: {e}")

    return None

async def close_session():
    if _session and not _session.closed:
        await _session.close()

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""

def _list_to_str_tmdb(data_list, limit=10, key=None):
    if not data_list or not isinstance(data_list, list):
        return None
    items = data_list[:limit]
    if key:
        return ", ".join(str(item.get(key, '')) for item in items if item)
    return ", ".join(str(item) for item in items if item)

def extract_sequel_num(text: str):
    if not text:
        return None
    t = text.lower()
    m = re.search(r'\b(?:part|chapter|volume|vol)?\s*([2-9]|ii|iii|iv|v|vi|vii|viii|ix|x)\b', t, re.IGNORECASE)
    if m:
        val = m.group(1).lower()
        roman_map = {'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
        return roman_map.get(val, val)
    return None

def _extract_title_year_and_season(query: str):
    q = query.strip()
    if re.match(r'^tt\d+$', q, re.IGNORECASE):
        return q, None, None

    year = None
    y_match = re.search(r'\b(19\d{2}|20\d{2})\b', q)
    if y_match:
        year = int(y_match.group(1))
        q = re.sub(rf'\b{year}\b', '', q).strip()

    season = None
    s_match = re.search(r'\b(?:season|s)\s*0*(\d{1,2})\b', q, re.IGNORECASE)
    if s_match:
        season = int(s_match.group(1))
        q = re.sub(r'\b(?:season|s)\s*0*\d{1,2}\b', '', q, flags=re.IGNORECASE).strip()

    q = re.sub(r'\s+', ' ', q).strip()
    return q, season, year

async def _tmdb_get(path, params=None, api_key=None):
    url = f"{TMDB_BASE_URL}/{path.lstrip('/')}"
    _params = params.copy() if params else {}
    _headers = {}

    if api_key:
        _params['api_key'] = api_key
    elif TMDB_BEARER_TOKEN:
        _headers = {
            'Authorization': f'Bearer {TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

    session = await get_session()
    async with session.get(url, params=_params, headers=_headers, ssl=False) as resp:
        resp.raise_for_status()
        return await resp.json()

async def _fetch_media_details(media_type: str, media_id: int, api_key=None):
    params = {
        'append_to_response': 'credits,external_ids,alternative_titles,release_dates,images',
        'include_image_language': 'en,hi,null'
    }
    return await _tmdb_get(f"{media_type}/{media_id}", params=params, api_key=api_key)

async def _fetch_season_poster(tv_id: int, season_number: int, api_key=None):
    try:
        data = await _tmdb_get(
            f"tv/{tv_id}/season/{season_number}", 
            params={'append_to_response': 'images', 'include_image_language': 'en,hi,null'}, 
            api_key=api_key
        )
        posters = data.get('images', {}).get('posters', [])
        if posters:
            return f"{TMDB_IMAGE_BASE_URL}{posters[0]['file_path']}"
    except Exception:
        pass
    return None

async def _search_media_id(query: str, api_key=None, is_series: bool = None):
    # Direct IMDb ID universal lookup
    if re.match(r'^tt\d+$', query.strip(), re.IGNORECASE):
        try:
            find_res = await _tmdb_get(f"find/{query.strip()}", params={'external_source': 'imdb_id'}, api_key=api_key)
            order = ('tv', 'movie') if is_series else ('movie', 'tv')
            for mtype in order:
                res_list = find_res.get(f"{mtype}_results", [])
                if res_list:
                    return mtype, res_list[0]['id']
        except Exception:
            pass

    title, season, year = _extract_title_year_and_season(query)
    clean_title_for_match = title

    multi_results = []
    queries_to_try = [title]
    if year:
        queries_to_try.append(f"{title} {year}")

    for target_query in queries_to_try:
        if not target_query:
            continue
        params = {'query': target_query, 'language': 'en-US', 'page': 1, 'include_adult': 'false'}
        try:
            result = await _tmdb_get('search/multi', params=params, api_key=api_key)
            multi_results = result.get('results', [])
            if multi_results:
                break
        except Exception:
            continue

    if not multi_results:
        return None, None

    def get_ratio(s1, s2):
        if not s1 or not s2:
            return 0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    scored_results = []
    query_words = set(clean_title_for_match.lower().split())
    target_type = 'tv' if is_series is True else ('movie' if is_series is False else None)
    q_sequel = extract_sequel_num(clean_title_for_match)

    for r in multi_results:
        mtype = r.get('media_type')
        if mtype not in ['movie', 'tv']:
            continue

        type_bonus = 0.0
        if target_type:
            if mtype == target_type:
                type_bonus = 0.35
            else:
                type_bonus = -0.35

        media_name = r.get('title') or r.get('name') or ''
        orig_name = r.get('original_title') or r.get('original_name') or ''
        
        ratio = max(
            get_ratio(media_name, clean_title_for_match),
            get_ratio(orig_name, clean_title_for_match)
        )
        
        m_sequel = extract_sequel_num(media_name) or extract_sequel_num(orig_name)

        # Sequel Validation
        if q_sequel != m_sequel:
            type_bonus -= 1.0  # Heavy penalty so Part 1 and Part 2 never cross-match
        else:
            type_bonus += 0.30

        media_words = set(media_name.lower().split()) | set(orig_name.lower().split())
        overlap = len(query_words.intersection(media_words))
        lang_bonus = 0.15 if r.get('original_language') == 'hi' else 0.0
        final_ratio = ratio + type_bonus + lang_bonus

        if ratio >= 0.35 or (query_words and overlap >= len(query_words) * 0.5):
            scored_results.append((r, final_ratio, overlap))

    if not scored_results:
        valid_res = [r for r in multi_results if r.get('media_type') in ['movie', 'tv']]
        if valid_res:
            scored_results = [(valid_res[0], 1.0, 1)]

    candidates_past, candidates_upcoming, candidates_nodate = [], [], []
    today = datetime.utcnow().date()

    for item in scored_results:
        r = item[0]
        ratio = item[1]
        mtype = r.get('media_type')
        rd_str = r.get('release_date') or r.get('first_air_date')
        
        candidate = {
            'type': mtype, 
            'id': r['id'], 
            'date': None, 
            'score': r.get('popularity', 0), 
            'ratio': ratio
        }

        if not rd_str:
            candidates_nodate.append(candidate)
            continue

        try:
            rd_date = datetime.strptime(rd_str, '%Y-%m-%d').date()
            candidate['date'] = rd_date
        except ValueError:
            candidates_nodate.append(candidate)
            continue

        if year:
            if abs(rd_date.year - year) == 0:
                candidate['ratio'] += 0.40
            elif abs(rd_date.year - year) > 1:
                candidate['ratio'] -= 0.50

        (candidates_upcoming if rd_date > today else candidates_past).append(candidate)

    candidates_past.sort(key=lambda x: (x['ratio'], x['score'], x['date'] or today), reverse=True)
    candidates_upcoming.sort(key=lambda x: (x['ratio'], x['score']), reverse=True)
    candidates_nodate.sort(key=lambda x: (x['ratio'], x['score']), reverse=True)
    
    final = candidates_past or candidates_upcoming or candidates_nodate
    if not final:
        return None, None
    return final[0]['type'], final[0]['id']

def _process_images(images_data):
    posters_by_lang, backdrops_by_lang = {}, {}
    for img in images_data.get('posters', []):
        lang = img.get('iso_639_1') or 'no_lang'
        posters_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    for img in images_data.get('backdrops', []):
        lang = img.get('iso_639_1') or 'no_lang'
        backdrops_by_lang.setdefault(lang, []).append(f"{TMDB_IMAGE_BASE_URL}{img['file_path']}")
    posters_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('posters', [])]
    backdrops_by_lang['all'] = [f"{TMDB_IMAGE_BASE_URL}{i['file_path']}" for i in images_data.get('backdrops', [])]
    languages = sorted(set(posters_by_lang) | set(backdrops_by_lang))
    return {'posters': posters_by_lang, 'backdrops': backdrops_by_lang, 'available_languages': languages}

async def _fetch_tmdb_data(query: str, api_key=None, is_series: bool = None):
    title, season, year_extracted = _extract_title_year_and_season(query)
    media_type, media_id = await _search_media_id(query, api_key=api_key, is_series=is_series)
    if not media_id:
        return None

    details = await _fetch_media_details(media_type, media_id, api_key=api_key)
    crew = details.get('credits', {}).get('crew', [])

    certificates = None
    if media_type == 'movie' and 'release_dates' in details:
        us = [r for r in details['release_dates']['results'] if r['iso_3166_1'] == 'US']
        if us and us[0]['release_dates']:
            certificates = us[0]['release_dates'][0].get('certification')

    runtime_display = None
    er_raw = details.get('episode_run_time', [])
    er_val = er_raw[0] if isinstance(er_raw, list) and er_raw else None

    if media_type == 'movie':
        runtime = details.get('runtime')
        runtime_display = f"{runtime} min" if runtime else None
    else:
        runtime_display = f"{er_val} min" if er_val else None

    images_structured = _process_images(details.get('images', {}))
    images_structured['original_language'] = details.get('original_language')

    poster_url = None
    if media_type == 'tv' and season is not None:
        poster_url = await _fetch_season_poster(media_id, season, api_key=api_key)

    if not poster_url:
        poster_url = f"{TMDB_IMAGE_BASE_URL}{details.get('poster_path')}" if details.get('poster_path') else None

    output_data = {
        'query': query, 'media_type': media_type, 'media_id': media_id,
        'title': details.get('title') or details.get('name'),
        'localized_title': details.get('original_title') or details.get('original_name'),
        'aka': _list_to_str_tmdb(details.get('alternative_titles', {}).get('titles', []), key='title'),
        'kind': media_type,
        'year': (details.get('release_date') or details.get('first_air_date', ''))[:4],
        'release_date': details.get('release_date') or details.get('first_air_date'),
        'imdb_id': details.get('external_ids', {}).get('imdb_id'),
        'tmdb_id': details.get('id'),
        'rating': details.get('vote_average'),
        'votes': details.get('vote_count'),
        'runtime': runtime_display,
        'episode_run_time': str(er_val) if er_val else None,
        'certificates': certificates,
        'genres': _list_to_str_tmdb(details.get('genres', []), key='name'),
        'languages': _list_to_str_tmdb(details.get('spoken_languages', []), key='english_name'),
        'countries': _list_to_str_tmdb(details.get('production_countries', []), key='name'),
        'director': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director'], key='name'),
        'writer': _list_to_str_tmdb([p for p in crew if p.get('job') in ['Screenplay', 'Writer', 'Story']], key='name'),
        'producer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Producer'], key='name'),
        'composer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Original Music Composer'], key='name'),
        'cinematographer': _list_to_str_tmdb([p for p in crew if p.get('job') == 'Director of Photography'], key='name'),
        'cast': _list_to_str_tmdb(details.get('credits', {}).get('cast', []), key='name', limit=15),
        'plot': details.get('overview'),
        'tagline': details.get('tagline'),
        'box_office': details.get('revenue') if details.get('revenue', 0) > 0 else "N/A",
        'distributors': _list_to_str_tmdb(details.get('production_companies', []), key='name'),
        'poster_url': poster_url,
        'backdrop_path': details.get('backdrop_path'),
        'url': f"https://www.themoviedb.org/{media_type}/{details.get('id')}",
        'images': images_structured,
    }

    if media_type == 'tv':
        output_data.update({
            'seasons': details.get('number_of_seasons'),
            'episodes': details.get('number_of_episodes'),
        })

    return output_data

async def get_movie_details(query, bulk=False, id=False, file=None, is_series: bool = None):
    from utils import listx_to_str, imdb

    q_str = str(query).strip()
    if q_str.lower().startswith("tt") and q_str[2:].isdigit():
        id = True
        movieid_str = q_str

    if not id:
        title, season, year_val = _extract_title_year_and_season(q_str)
        if file is not None and not year_val:
            y_m = re.search(r'\b(19\d{2}|20\d{2})\b', file)
            if y_m:
                year_val = int(y_m.group(1))

        search_result = await asyncio.to_thread(imdb.search_movie, title.lower())
        if not search_result:
            return None
            
        movie_list = search_result.titles[:MAX_LIST_ELM] if hasattr(search_result, 'titles') else search_result[:MAX_LIST_ELM]

        # Episode pages ko filter karein
        movie_list = [m for m in movie_list if getattr(m, 'kind', None) != 'episode']

        if is_series is True:
            kind_filter = ['tv series', 'tvSeries', 'tvMiniSeries']
        elif is_series is False:
            kind_filter = ['movie', 'tvMovie']
        else:
            kind_filter = ['movie', 'tv series', 'tvSeries', 'tvMiniSeries', 'tvMovie']

        valid_kinds = [m for m in movie_list if getattr(m, 'kind', None) in kind_filter]
        if valid_kinds:
            movie_list = valid_kinds

        # IMDb Sequel & Year Ranking Engine
        q_seq = extract_sequel_num(title)

        def match_score(m):
            m_title = getattr(m, 'title', '')
            m_year = getattr(m, 'year', None)
            m_seq = extract_sequel_num(m_title)
            
            score = 0.0
            if q_seq == m_seq:
                score += 5.0
            else:
                score -= 10.0

            if year_val and m_year:
                if str(m_year) == str(year_val):
                    score += 4.0
                elif abs(int(m_year) - int(year_val)) <= 1:
                    score += 2.0
                else:
                    score -= 3.0

            ratio = SequenceMatcher(None, title.lower(), m_title.lower()).ratio()
            score += ratio * 3.0
            return score

        movie_list.sort(key=match_score, reverse=True)

        if bulk:
            return movie_list[:MAX_LIST_ELM]
        if not movie_list:
            return None   

        movie_brief = movie_list[0]
        movieid_str = getattr(movie_brief, 'imdb_id', getattr(movie_brief, 'movieID', None))
    else:
        movieid_str = query

    if not movieid_str:
        return None

    movie = await asyncio.to_thread(imdb.get_movie, str(movieid_str).replace("tt", ""))
    if not movie:
        return None

    date = getattr(movie, 'release_date', None) or str(getattr(movie, 'year', '')) or "N/A"
    plot = movie.plot[0] if isinstance(getattr(movie, 'plot', None), list) else getattr(movie, 'plot', "") or ""
    if len(plot) > 800:
        plot = plot[:800] + "..."
        
    imdb_id = getattr(movie, 'imdb_id', getattr(movie, 'movieID', ''))
    if imdb_id and not str(imdb_id).startswith("tt"):
        imdb_id = f"tt{imdb_id}"

    return {
        'title': getattr(movie, 'title', ''),
        'votes': getattr(movie, 'votes', 0),
        "aka": listx_to_str(getattr(movie, 'title_akas', [])),
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": getattr(movie, 'worldwide_gross', 'N/A'),
        'localized_title': getattr(movie, 'title_localized', ''),
        'kind': getattr(movie, 'kind', ''),
        "imdb_id": imdb_id,
        "cast": listx_to_str(getattr(movie, 'stars', [])),
        "runtime": listx_to_str(getattr(movie, 'duration', [])),
        "countries": listx_to_str(getattr(movie, 'countries', [])),
        "certificates": listx_to_str(getattr(movie, 'certificates', [])),
        "languages": listx_to_str(getattr(movie, 'languages', [])),
        "director": listx_to_str(getattr(movie, 'directors', [])),
        "writer": listx_to_str([p.name for p in getattr(movie, 'writers', []) if hasattr(p, 'name')]),
        "producer": listx_to_str([p.name for p in getattr(movie, 'producers', []) if hasattr(p, 'name')]),
        "composer": listx_to_str([p.name for p in getattr(movie, 'composers', []) if hasattr(p, 'name')]),
        "cinematographer": listx_to_str([p.name for p in getattr(movie, 'cinematographers', []) if hasattr(p, 'name')]),
        "music_team": listx_to_str([p.name for p in getattr(movie, 'music_team', []) if hasattr(p, 'name')]),
        "distributors": listx_to_str([c.name for c in getattr(movie, 'distributors', []) if hasattr(c, 'name')]),        
        'release_date': date,
        'year': getattr(movie, 'year', None),
        'genres': listx_to_str(getattr(movie, 'genres', [])),
        'poster': getattr(movie, 'cover_url', None),
        'poster_url': movie.cover_url.split("._V1_")[0] + "._V1_SX1280.jpg" if getattr(movie, 'cover_url', None) and "._V1_" in movie.cover_url else getattr(movie, 'cover_url', None),
        'plot': plot,
        'rating': str(getattr(movie, 'rating', 'x/10')),
        "url": getattr(movie, 'url', None) or f"https://www.imdb.com/title/{imdb_id}"
    }

async def get_movie_detailsx(query, id=False, file=None, is_series: bool = None):
    q = str(query).strip()
    try:
        data = await _fetch_tmdb_data(q, api_key=TMDB_API_KEY or None, is_series=is_series)
        if not data:
            logger.info(f"TMDB returned no results for '{q}' → switching to IMDb fallback")
            return await get_movie_details(q, is_series=is_series)
    except Exception as e:
        logger.info(f"TMDB direct call failed → fallback IMDb: {e}")
        return await get_movie_details(q, is_series=is_series)

    details = {}
    details['title'] = data.get('title') or data.get('localized_title')
    details['year'] = data.get('year') if data.get('year') else None
    details['release_date'] = data.get('release_date')
    details['rating'] = round(float(data.get('rating', 0)), 1) if data.get('rating') is not None else None
    details['votes'] = int(data.get('votes', 0))
    details['runtime'] = data.get('runtime')
    details['episode_run_time'] = data.get('episode_run_time')
    details['certificates'] = data.get('certificates')
    details['tmdb_url'] = data.get('url')
    
    for key in ('genres', 'languages', 'countries'):
        raw = data.get(key)
        details[key] = [s.strip() for s in raw.split(',')] if raw else []
    for role in ('director', 'writer', 'producer', 'composer', 'cinematographer', 'cast'):
        raw = data.get(role)
        details[role] = [s.strip() for s in raw.split(',')] if raw else []
        
    details['plot'] = data.get('plot')
    details['tagline'] = data.get('tagline')
    details['box_office'] = data.get('box_office') if data.get('box_office') else None
    raw_dist = data.get('distributors')
    details['distributors'] = [d.strip() for d in raw_dist.split(',')] if raw_dist else []
    details['imdb_id'] = data.get('imdb_id')
    details['tmdb_id'] = data.get('tmdb_id')
    
    posters = data.get('images', {}).get('posters', {})
    original_language = data.get('images', {}).get('original_language')
    poster_url = data.get('poster_url')
    if not poster_url:
        for key in ('hi', 'en', original_language, 'xx', 'no_lang', 'all'):
            if key and posters.get(key):
                poster_url = posters[key][0]
                break
    details['poster_url'] = poster_url.replace("/original/", "/w1280/") if poster_url else None

    backdrops = data.get('images', {}).get('backdrops', {})
    backdrop_url = None
    for key in ('hi', 'en', original_language, 'xx', 'no_lang', 'all'):
        if key and backdrops.get(key):
            backdrop_url = backdrops[key][0]
            break
            
    if not backdrop_url and data.get('backdrop_path'):
        backdrop_url = f"{TMDB_IMAGE_BASE_URL}{data['backdrop_path']}"

    details['backdrop_url'] = backdrop_url.replace("/original/", "/w1280/") if backdrop_url else None

    return details
