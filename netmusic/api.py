"""网易云接口层（自带路由自愈：多方案探测 / 失败自动切换 / 宽松解析 / 可配置补丁）

设计目标：网易改动接口时，程序尽量自己恢复，而不是直接不可用。

三层保障
1. 每项能力（搜索/歌单/歌词/播放地址/登录…）都预置多套接口方案，逐一尝试；
   第一套失败自动换下一套，成功的方案记进 ~/.config/netmusic/routes.json，下次优先用。
2. 解析层不假设固定字段结构（兼容新旧返回格式、data/result/playlist 嵌套差异、
   Content-Type 为 text/plain 但实际是 JSON 等情况）。
3. 可用 ~/.config/netmusic/endpoints.json 追加自定义接口路径（改接口不用改代码），
   支持 {keyword}/{song_id}/{playlist_id}/{uid}/{limit}/{offset} 占位符。
"""
import base64
import hashlib
import json
import os
import random
import string
import time
import traceback
import uuid

from requests import Session
from requests.utils import cookiejar_from_dict, dict_from_cookiejar

BASE = "https://music.163.com"
CONFIG_DIR = os.path.expanduser("~/.config/netmusic")
COOKIE_FILE = os.path.join(CONFIG_DIR, "cookies.json")
ROUTES_FILE = os.path.join(CONFIG_DIR, "routes.json")
ENDPOINTS_FILE = os.path.join(CONFIG_DIR, "endpoints.json")
LOG_FILE = os.path.join(CONFIG_DIR, "netmusic.log")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ---- weapi 加密（登录类接口现在要求加密，明文会被判 401 无权限访问. ENC）----
_WEAPI_PRESET_KEY = "0CoJUm6Qyw8W8jud"
_WEAPI_IV = "0102030405060708"
_WEAPI_MODULUS = int(
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa"
    "76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a4"
    "6bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7",
    16)
_WEAPI_PUBKEY_E = 65537

try:
    from cryptography.hazmat.primitives import padding as _padding
    from cryptography.hazmat.primitives.ciphers import Cipher as _Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms as _algorithms
    from cryptography.hazmat.primitives.ciphers import modes as _modes
    HAS_WEAPI = True
except Exception:  # 设备没装 cryptography 时降级到明文接口
    HAS_WEAPI = False

class RouteError(Exception):
    """某套接口方案不可用（路径失效/结构不符）"""


class CapabilityError(Exception):
    def __init__(self, capability, attempts):
        self.capability = capability
        self.attempts = attempts
        detail = "；".join("%s: %s" % (name, err) for name, err in attempts)
        super().__init__("「%s」所有接口方案均失败 → %s" % (capability, detail))


# ---------------------------------------------------------------- 基础工具

def _log(message):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 512 * 1024:
            os.replace(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _aes_cbc_b64(text, key):
    padder = _padding.PKCS7(128).padder()
    data = padder.update(text.encode("utf-8")) + padder.finalize()
    enc = _Cipher(_algorithms.AES(key.encode("utf-8")),
                  _modes.CBC(_WEAPI_IV.encode("utf-8"))).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode("ascii")


def _rsa_encrypt(text):
    """网易固定公钥 RSA（无填充），密钥字节倒序后取模幂"""
    raw = text[::-1].encode("utf-8")
    return format(pow(int.from_bytes(raw, "big"), _WEAPI_PUBKEY_E,
                      _WEAPI_MODULUS), "x").rjust(256, "0")


def weapi_form(payload):
    """构造 weapi 的 params / encSecKey（两层 AES-CBC + RSA）"""
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    secret = "".join(random.choice(string.ascii_letters + string.digits)
                     for _ in range(16))
    return {"params": _aes_cbc_b64(_aes_cbc_b64(text, _WEAPI_PRESET_KEY), secret),
            "encSecKey": _rsa_encrypt(secret)}


def _first(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _dig(payload, *path):
    """按路径逐层取值，任意层缺失返回 None"""
    cur = payload
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int):
            cur = cur[key] if -len(cur) <= key < len(cur) else None
        else:
            return None
    return cur


def _walk_lists(payload, keys):
    """在常见嵌套位置寻找列表字段"""
    for container in (payload, _dig(payload, "result"), _dig(payload, "data"),
                      _dig(payload, "result", "data")):
        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)
                if isinstance(value, list) and value:
                    return value
    return None


def parse_json(resp):
    """容忍 text/plain 的 JSON 响应"""
    try:
        return resp.json()
    except ValueError:
        text = (resp.text or "").strip()
        if not text:
            raise RouteError("空响应 (HTTP %s)" % resp.status_code)
        try:
            return json.loads(text)
        except ValueError:
            raise RouteError("响应不是 JSON (HTTP %s): %s" % (resp.status_code, text[:120]))


def normalize_song(song):
    """兼容新旧歌曲结构"""
    artists = _first(song.get("ar"), song.get("artists"), song.get("artist"))
    artist_id = 0
    if isinstance(artists, dict):
        artist_name = artists.get("name", "")
        artist_id = artists.get("id") or 0
    elif isinstance(artists, list):
        artist_name = " / ".join(
            a.get("name", "") if isinstance(a, dict) else str(a) for a in artists)
        for artist in artists:
            if isinstance(artist, dict) and artist.get("id"):
                artist_id = artist["id"]
                break
    elif isinstance(artists, str):
        artist_name = artists
    else:
        artist_name = ""
    artist_id = artist_id or song.get("artistId") or 0

    album = _first(song.get("al"), song.get("album"), {})
    if isinstance(album, str):
        album = {"name": album}
    duration = _first(song.get("dt"), song.get("duration"),
                      _dig(song, "h", "playTime"), _dig(song, "l", "playTime"), 0)
    cover = _first(album.get("picUrl"), album.get("img1v1Url"),
                   song.get("picUrl"), song.get("coverImgUrl"), "")
    return {
        "id": song.get("id") or song.get("songId"),
        "name": _first(song.get("name"), song.get("songName"), ""),
        "artist": artist_name,
        "artist_id": artist_id,
        "album": _first(album.get("name"), album.get("albumName"), ""),
        "album_id": album.get("id") or song.get("albumId"),
        "cover": cover,
        "duration": duration or 0,
        "fee": song.get("fee", 0),
    }


def _artist_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name", "")
    if isinstance(value, list):
        return " / ".join(
            a.get("name", "") if isinstance(a, dict) else str(a) for a in value)
    return ""


def extract_album(payload):
    """专辑详情：兼容 /api/album 与 /api/v1/album 的返回结构"""
    if not isinstance(payload, dict):
        raise RouteError("专辑响应结构异常")
    album = _first(payload.get("album"), _dig(payload, "data", "album"),
                   _dig(payload, "result", "album"))
    if album is None and isinstance(payload.get("result"), dict):
        album = payload["result"]
    if not isinstance(album, dict):
        raise RouteError("返回中找不到专辑对象")
    songs = album.get("songs")
    if not isinstance(songs, list):
        songs = payload.get("songs")
    if not isinstance(songs, list):
        songs = _walk_lists(payload, ("songs",)) or []
    artist_name = _artist_text(album.get("artists"))
    if not artist_name:
        artist_name = _artist_text(album.get("artist"))
    return {
        "id": album.get("id"),
        "name": album.get("name") or album.get("albumName") or "",
        "artist": artist_name,
        "cover": _first(album.get("picUrl"), album.get("blurPicUrl"),
                        album.get("img1v1Url"), ""),
        "description": _first(album.get("description"), album.get("briefDesc"), ""),
        "company": album.get("company") or "",
        "publish_time": album.get("publishTime") or 0,
        "songs": [normalize_song(song) for song in songs
                  if isinstance(song, dict)],
    }


def extract_artist(payload, artist_id=0):
    """歌手详情：兼容 /api/artist 与 /api/v1/artist 的返回结构"""
    artist = _first(payload.get("artist"), _dig(payload, "data", "artist"),
                    _dig(payload, "result", "artist"))
    if not isinstance(artist, dict):
        artist = {}
    songs = _first(payload.get("hotSongs"), payload.get("songs"),
                   _dig(payload, "data", "songs"), _dig(payload, "result", "songs"))
    if not isinstance(songs, list):
        songs = _walk_lists(payload, ("hotSongs", "songs")) or []
    alias = artist.get("alias") or artist.get("alia") or []
    if isinstance(alias, list):
        alias = " / ".join(str(a) for a in alias if a)
    else:
        alias = str(alias or "")
    return {
        "id": artist.get("id") or artist_id,
        "name": artist.get("name") or "",
        "alias": alias,
        "cover": _first(artist.get("picUrl"), artist.get("img1v1Url"),
                        artist.get("avatar"), ""),
        "description": _first(artist.get("briefDesc"),
                             artist.get("description"),
                             artist.get("trans"), ""),
        "music_size": artist.get("musicSize") or 0,
        "album_size": artist.get("albumSize") or 0,
        "songs": [normalize_song(song) for song in songs
                  if isinstance(song, dict)],
    }


def extract_artist_albums(payload):
    """歌手专辑列表：兼容 hotAlbums / albums 两种字段"""
    albums = _first(payload.get("hotAlbums"), payload.get("albums"),
                    _dig(payload, "data", "hotAlbums"),
                    _dig(payload, "data", "albums"),
                    _dig(payload, "result", "hotAlbums"),
                    _dig(payload, "result", "albums"))
    if not isinstance(albums, list):
        albums = _walk_lists(payload, ("hotAlbums", "albums")) or []
    result = []
    for album in albums:
        if not isinstance(album, dict):
            continue
        result.append({
            "id": album.get("id"),
            "name": album.get("name") or "",
            "cover": _first(album.get("picUrl"), album.get("cover"),
                            album.get("img1v1Url"), ""),
            "publish_time": album.get("publishTime") or 0,
            "size": album.get("size") or 0,
            "company": album.get("company") or "",
        })
    return result


def normalize_playlist(item):
    return {
        "id": item.get("id") or item.get("playlistId"),
        "name": _first(item.get("name"), item.get("playlistName"), ""),
        "cover": _first(item.get("coverImgUrl"), item.get("picUrl"),
                        item.get("coverUrl"), ""),
        "track_count": _first(item.get("trackCount"), item.get("songCount"), 0),
        "creator": _dig(item, "creator", "nickname") or "",
    }


def extract_songs(payload):
    songs = _walk_lists(payload, ("songs", "tracks", "songList"))
    if songs is None:
        for holder in (payload, _dig(payload, "result")):
            if isinstance(holder, dict) and any(
                    key in holder for key in ("songs", "tracks", "songList")):
                return []
        raise RouteError("返回中找不到歌曲列表")
    return [normalize_song(song) for song in songs if isinstance(song, dict)]


def extract_playlist(payload):
    playlist = _first(payload.get("playlist"), _dig(payload, "result", "playlist"),
                      _dig(payload, "data", "playlist"))
    if playlist is None and isinstance(payload.get("result"), dict):
        candidate = payload["result"]
        if "tracks" in candidate or "trackIds" in candidate:
            playlist = candidate
    if not isinstance(playlist, dict):
        raise RouteError("返回中找不到歌单对象")
    return playlist


def extract_playlists(payload):
    items = _walk_lists(payload, ("result", "playlists", "recommend"))
    if items is None:
        raise RouteError("返回中找不到歌单列表")
    if items and not isinstance(items[0], dict):
        raise RouteError("歌单列表结构异常")
    return [normalize_playlist(item) for item in items]


def extract_url(payload, song_id):
    data = _first(payload.get("data"), _dig(payload, "data", "data"), payload.get("url"))
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise RouteError("返回中找不到播放地址字段")
    entry = next((x for x in data if isinstance(x, dict)
                  and (x.get("id") in (None, song_id))), data[0])
    if not isinstance(entry, dict):
        raise RouteError("播放地址结构异常")
    return entry.get("url") or entry.get("playUrl") or entry.get("src") or None


def extract_lyric(payload):
    for holder in (payload, _dig(payload, "lrc"), _dig(payload, "data")):
        if isinstance(holder, dict):
            for key in ("lyric", "lyricDoc", "lrc", "text"):
                value = holder.get(key)
                if isinstance(value, str):
                    return value
    if payload.get("nolyric") or payload.get("uncollected"):
        return ""
    raise RouteError("返回中找不到歌词字段")


def _normalize_comment(item):
    """把新旧评论结构整理成 UI 能直接消费的字段"""
    if not isinstance(item, dict):
        return None
    raw = item.get("comment") if isinstance(item.get("comment"), dict) else item
    content = raw.get("content") or raw.get("richContent") or ""
    if not content:
        return None
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    replies = []
    for reply in raw.get("beReplied") or []:
        if not isinstance(reply, dict):
            continue
        reply_user = reply.get("user") if isinstance(reply.get("user"), dict) else {}
        replies.append({
            "nickname": reply_user.get("nickname") or "网易云用户",
            "content": reply.get("content") or "",
        })
    return {
        "id": raw.get("commentId") or raw.get("id"),
        "content": content,
        "nickname": user.get("nickname") or "网易云用户",
        "avatar": user.get("avatarUrl") or "",
        "time": raw.get("time") or 0,
        "time_text": raw.get("timeStr") or "",
        "liked": raw.get("likedCount") or 0,
        "reply": replies,
    }


def extract_comments(payload):
    """兼容 hotComments/topComments/comments 等不同返回层级"""
    if not isinstance(payload, dict):
        raise RouteError("评论响应结构异常")
    hot = []
    latest = []
    for holder in (payload, _dig(payload, "data"), _dig(payload, "result")):
        if not isinstance(holder, dict):
            continue
        hot_raw = holder.get("hotComments") or holder.get("topComments")
        latest_raw = holder.get("comments")
        if isinstance(hot_raw, list):
            hot = [c for c in (_normalize_comment(x) for x in hot_raw) if c]
        if isinstance(latest_raw, list):
            latest = [c for c in (_normalize_comment(x) for x in latest_raw) if c]
        if hot or latest:
            break
    total = _first(payload.get("total"), _dig(payload, "data", "total"),
                   len(latest))
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        total = len(latest)
    more = bool(payload.get("more") or _dig(payload, "data", "more"))
    return {"hot": hot, "latest": latest, "total": total, "more": more}


def extract_account(payload):
    account = _first(payload.get("account"), _dig(payload, "data", "account"))
    profile = _first(payload.get("profile"), _dig(payload, "data", "profile"))
    if not isinstance(account, dict):
        if isinstance(profile, dict):
            account = profile
        else:
            return None
    if isinstance(profile, dict):
        for key in ("nickname", "avatarUrl"):
            if profile.get(key) and not account.get(key):
                account[key] = profile[key]
    return account


# ---------------------------------------------------------------- 接口方案

class Route:
    def __init__(self, capability, name, handler, description="", weight=10):
        self.capability = capability
        self.name = name
        self.handler = handler
        self.description = description
        self.weight = weight


def route(capability, name, description="", weight=10):
    def decorator(handler):
        return Route(capability, name, handler, description, weight)
    return decorator


@route("search", "search/get", "旧版搜索接口")
def _search_legacy(client, keyword, limit=30, offset=0):
    payload = client.request("GET", "/api/search/get",
                             params={"s": keyword, "type": 1,
                                     "limit": limit, "offset": offset})
    return extract_songs(payload)


@route("search", "cloudsearch/get", "云搜索 GET")
def _search_cloud_get(client, keyword, limit=30, offset=0):
    payload = client.request("GET", "/api/cloudsearch/pc",
                             params={"s": keyword, "type": 1,
                                     "limit": limit, "offset": offset})
    return extract_songs(payload)


@route("search", "cloudsearch/post", "云搜索 POST")
def _search_cloud_post(client, keyword, limit=30, offset=0):
    payload = client.request("POST", "/api/cloudsearch/pc",
                             data={"s": keyword, "type": 1,
                                   "limit": limit, "offset": offset})
    return extract_songs(payload)


@route("song_url", "url/v1-exhigh", "播放地址 v1（极高）")
def _url_v1(client, song_id, level="exhigh"):
    levels = [level] if level else ["exhigh", "higher", "standard"]
    for lv in levels:
        payload = client.request("GET", "/api/song/enhance/player/url/v1",
                                 params={"ids": json.dumps([song_id]), "level": lv,
                                         "encodeType": "flac"})
        return extract_url(payload, song_id)
    return None


@route("song_url", "url/v1-standard", "播放地址 v1（标准）")
def _url_v1_standard(client, song_id, level=None):
    payload = client.request("GET", "/api/song/enhance/player/url/v1",
                             params={"ids": json.dumps([song_id]),
                                     "level": "standard", "encodeType": "flac"})
    return extract_url(payload, song_id)


@route("song_url", "url/legacy", "播放地址旧接口（320k）")
def _url_legacy(client, song_id, level=None):
    payload = client.request("GET", "/api/song/enhance/player/url",
                             params={"ids": json.dumps([song_id]), "br": 320000})
    return extract_url(payload, song_id)


@route("song_url", "url/outer", "外链播放地址")
def _url_outer(client, song_id, level=None):
    url = BASE + "/song/media/outer/url?id=%s.mp3" % song_id
    resp = client.raw("GET", url.replace(BASE, ""))
    final = resp.url or ""
    if "404" in final:
        raise RouteError("外链不可用")
    return final


@route("lyric", "song/lyric", "歌词接口")
def _lyric(client, song_id):
    payload = client.request("GET", "/api/song/lyric",
                             params={"id": song_id, "lv": 1, "kv": 1, "tv": -1})
    return extract_lyric(payload)


@route("playlist", "v6/detail", "歌单详情 v6")
def _playlist_v6(client, playlist_id):
    payload = client.request("GET", "/api/v6/playlist/detail",
                             params={"id": playlist_id, "n": 1000, "s": 0})
    playlist = extract_playlist(payload)
    tracks = playlist.get("tracks") or []
    ids = [t.get("id") for t in playlist.get("trackIds") or [] if t.get("id")]
    if len(ids) > len(tracks):
        tracks = client.tracks_by_ids(ids)
    return _pack_playlist(playlist, tracks)


@route("playlist", "detail-legacy", "歌单详情旧版")
def _playlist_legacy(client, playlist_id):
    payload = client.request("GET", "/api/playlist/detail",
                             params={"id": playlist_id})
    playlist = extract_playlist(payload)
    tracks = playlist.get("tracks") or []
    ids = [t.get("id") for t in playlist.get("trackIds") or [] if t.get("id")]
    if len(ids) > len(tracks):
        tracks = client.tracks_by_ids(ids)
    return _pack_playlist(playlist, tracks)


def _pack_playlist(playlist, tracks):
    return {
        "id": playlist.get("id"),
        "name": playlist.get("name", ""),
        "cover": _first(playlist.get("coverImgUrl"), playlist.get("coverUrl"), ""),
        "creator": _dig(playlist, "creator", "nickname") or "",
        "track_count": _first(playlist.get("trackCount"), len(tracks)),
        "tracks": [normalize_song(t) for t in tracks if isinstance(t, dict)],
    }


@route("recommend", "personalized/playlist", "个性化推荐")
def _recommend_personalized(client, limit=12):
    payload = client.request("GET", "/api/personalized/playlist",
                             params={"limit": limit}, allow_fail=True)
    if payload.get("code") not in (None, 200):
        raise RouteError("接口返回 code=%s" % payload.get("code"))
    return extract_playlists(payload)


@route("recommend", "recommend/resource", "推荐资源（需登录）")
def _recommend_resource(client, limit=12):
    payload = client.request("GET", "/api/v1/discovery/recommend/resource")
    items = extract_playlists(payload)
    return items[:limit]


@route("daily", "discovery/recommend/songs", "每日推荐（加密版）")
def _daily(client):
    payload = client.weapi("/weapi/v1/discovery/recommend/songs", {"csrf_token": ""})
    data = payload.get("data") or {}
    songs = data.get("dailySongs") or []
    if not songs:
        raise RouteError("返回中没有每日推荐歌曲")
    return [normalize_song(song) for song in songs if isinstance(song, dict)]


@route("intelligence", "playmode/intelligence/list", "心动模式（官方）", weight=1)
def _intelligence_official(client, playlist_id, song_id):
    payload = client.request("GET", "/api/playmode/intelligence/list",
                             params={"id": song_id, "pid": playlist_id},
                             allow_fail=True)
    data = payload.get("data") or []
    songs = [normalize_song(song) for song in data if isinstance(song, dict)]
    if not songs:
        raise RouteError("接口没有返回心动歌曲")
    return songs


@route("intelligence", "simiSong", "心动模式（相似歌曲）")
def _intelligence_simi(client, playlist_id, song_id):
    """官方心动接口对网页端常返回 500，退化为相似歌曲串联"""
    songs, seen = [], set()
    seed = song_id
    for _ in range(4):
        payload = client.request("GET", "/api/v1/discovery/simiSong",
                                 params={"songid": seed}, allow_fail=True)
        batch = [normalize_song(song) for song in (payload.get("songs") or [])
                 if isinstance(song, dict)]
        fresh = [song for song in batch if song.get("id") not in seen]
        if not fresh:
            break
        songs.extend(fresh)
        seen.update(song.get("id") for song in fresh)
        seed = fresh[0].get("id")
    if not songs:
        raise RouteError("相似歌曲接口没有返回")
    return songs[:30]


@route("user_playlists", "user/playlist", "用户歌单")
def _user_playlists(client, uid, limit=1000):
    payload = client.request("GET", "/api/user/playlist",
                             params={"uid": uid, "limit": limit, "offset": 0})
    items = _walk_lists(payload, ("playlist", "playlists"))
    if items is None:
        raise RouteError("返回中找不到歌单列表")
    return [normalize_playlist(item) for item in items]


@route("account", "nuser/account", "当前账号")
def _account(client):
    payload = client.request("GET", "/api/nuser/account/get")
    return extract_account(payload)


@route("qr_unikey", "qrcode/unikey-weapi", "二维码 key（weapi 加密）", weight=20)
def _qr_unikey_weapi(client):
    payload = client.weapi("/weapi/login/qrcode/unikey",
                           {"type": 3, "csrf_token": ""})
    key = payload.get("unikey") or payload.get("key")
    if not key:
        raise RouteError("未返回 unikey")
    return key


@route("qr_check", "qrcode/client-login-weapi", "扫码状态（weapi 加密）", weight=20)
def _qr_check_weapi(client, unikey):
    """type=3 是 App 扫码；type=1 是旧网页端，新版扫码 key 必须配对 type=3"""
    payload = client.weapi("/weapi/login/qrcode/client/login",
                           {"type": 3, "key": unikey,
                            "csrf_token": ""})
    code = payload.get("code")
    if code is None:
        raise RouteError("返回中找不到 code")
    client.absorb_login_cookie(payload, "扫码状态(type=3)")
    if code == 802:
        _log("已扫码，等待手机端确认")
    elif code == 803:
        _log("803 响应字段: %s" % ",".join(sorted(payload.keys())))
        client.log_cookie_state("扫码成功(weapi)")
        if "MUSIC_U" not in dict_from_cookiejar(client.s.cookies):
            for _ in range(2):
                try:
                    extra = client.weapi("/weapi/login/qrcode/client/login",
                                         {"type": 3, "key": unikey,
                                          "csrf_token": ""})
                    client.absorb_login_cookie(extra, "扫码二次确认")
                    client.log_cookie_state("二次确认(type=3)")
                except Exception as exc:
                    _log("扫码二次确认失败(type=3): %s" % exc)
    return code, payload.get("message", "")


@route("sms_send", "weapi/sms/captcha/sent", "发送短信验证码", weight=1)
def _sms_send(client, phone, countrycode="86"):
    payload = client.weapi("/weapi/sms/captcha/sent",
                           {"cellphone": str(phone),
                            "ctcode": str(countrycode or "86"),
                            "secrete": "music_middleuser_pclogin",
                            "csrf_token": ""})
    if payload.get("code") != 200:
        raise RouteError("发送失败 code=%s %s" % (
            payload.get("code"), payload.get("message", "")))
    return payload


@route("sms_login", "weapi/w/login/cellphone", "短信验证码登录（新版）", weight=1)
def _sms_login(client, phone, code, countrycode="86"):
    payload = client.weapi("/weapi/w/login/cellphone", {
        "type": "1",
        "https": "true",
        "phone": str(phone),
        "countrycode": str(countrycode or "86"),
        "captcha": str(code),
        "remember": "true",
        "secureCaptcha": "",
    })
    client.absorb_login_cookie(payload, "验证码登录")
    if payload.get("code") != 200:
        raise RouteError("登录失败 code=%s %s" % (
            payload.get("code"),
            payload.get("message") or payload.get("msg") or ""))
    return payload


@route("login_phone", "weapi/w/login/cellphone", "手机号密码登录（新版）", weight=1)
def _login_phone(client, phone, password, countrycode="86"):
    payload = client.weapi("/weapi/w/login/cellphone", {
        "type": "1",
        "https": "true",
        "phone": str(phone),
        "countrycode": str(countrycode or "86"),
        "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
        "remember": "true",
        "secureCaptcha": "",
    })
    client.absorb_login_cookie(payload, "手机号登录")
    if payload.get("code") != 200:
        raise RouteError("登录失败 code=%s %s" % (
            payload.get("code"),
            payload.get("message") or payload.get("msg") or ""))
    return payload


@route("login_email", "weapi/w/login", "邮箱密码登录（新版）", weight=1)
def _login_email(client, email, password):
    payload = client.weapi("/weapi/w/login", {
        "type": "0",
        "https": "true",
        "username": str(email),
        "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
        "rememberLogin": "true",
    })
    client.absorb_login_cookie(payload, "邮箱登录")
    if payload.get("code") != 200:
        raise RouteError("登录失败 code=%s %s" % (
            payload.get("code"),
            payload.get("message") or payload.get("msg") or ""))
    return payload


@route("qr_unikey", "qrcode/unikey-post", "二维码 key（POST，type=3）", weight=0)
def _qr_unikey_post(client):
    payload = client.request("POST", "/api/login/qrcode/unikey",
                             data={"type": 3, "_": int(time.time() * 1000)})
    key = payload.get("unikey") or payload.get("key")
    if not key:
        raise RouteError("未返回 unikey")
    return key


@route("qr_unikey", "qrcode/unikey-get", "二维码 key（GET，type=3）", weight=1)
def _qr_unikey_get(client):
    payload = client.request("GET", "/api/login/qrcode/unikey",
                             params={"type": 3, "_": int(time.time() * 1000)})
    key = payload.get("unikey") or payload.get("key")
    if not key:
        raise RouteError("未返回 unikey")
    return key


@route("qr_check", "qrcode/client-login", "扫码状态（type=3）", weight=0)
def _qr_check(client, unikey):
    payload = client.request("GET", "/api/login/qrcode/client/login",
                             params={"type": 3, "key": unikey,
                                     "_": int(time.time() * 1000)})
    code = payload.get("code")
    if code is None:
        raise RouteError("返回中找不到 code")
    client.absorb_login_cookie(payload, "扫码状态(明文)")
    if code == 802:
        _log("已扫码，等待手机端确认")
    elif code == 803:
        client.log_cookie_state("扫码成功(明文)")
        if "MUSIC_U" not in dict_from_cookiejar(client.s.cookies):
            try:
                extra = client.request("GET",
                                       "/api/login/qrcode/client/login",
                                       params={"type": 3, "key": unikey,
                                               "_": int(time.time() * 1000)})
                client.absorb_login_cookie(extra, "扫码二次确认(明文)")
                client.log_cookie_state("二次确认(type=3)")
            except Exception as exc:
                _log("扫码二次确认失败(type=3): %s" % exc)
    return code, payload.get("message", "")


# ---------------------------------------------------------------- 客户端

class NeteaseClient:
    def __init__(self):
        self.s = Session()
        self.s.headers.update({"User-Agent": UA, "Referer": BASE + "/",
                               "Origin": BASE, "Accept": "*/*"})
        self.account = None
        self._liked_ids = None
        self._routes_cache = self._load_json(ROUTES_FILE, {})
        self._custom_routes = self._load_json(ENDPOINTS_FILE, {}).get("custom", {})
        self._switch_listeners = []
        self._fail_streak = {}
        self._load_cookies()
        self._seed_device_cookies()

    def _seed_device_cookies(self):
        """补齐浏览器惯有的设备指纹 cookie，降低登录风控概率"""
        try:
            jar = dict_from_cookiejar(self.s.cookies)
            nuid = jar.get("_ntes_nuid")
            if not nuid:
                nuid = uuid.uuid4().hex
                self.s.cookies.set("_ntes_nuid", nuid, domain=".music.163.com")
                self.s.cookies.set("_ntes_nnid",
                                   "%s,%d" % (nuid, int(time.time() * 1000)),
                                   domain=".music.163.com")
            if not jar.get("os"):
                self.s.cookies.set("os", "pc", domain=".music.163.com")
            if not jar.get("appver"):
                self.s.cookies.set("appver", "2.9.6.199999",
                                   domain=".music.163.com")
            if not jar.get("channel"):
                self.s.cookies.set("channel", "netease",
                                   domain=".music.163.com")
        except Exception as exc:
            _log("初始化设备 cookie 失败: %r" % exc)

    # ---------- 本地状态 ----------
    @staticmethod
    def _load_json(path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            pass
        return default

    def _save_json(self, path, data):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            _log("保存 %s 失败: %r" % (path, exc))

    def _load_cookies(self):
        try:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, "r", encoding="utf-8") as fh:
                    self.s.cookies.update(cookiejar_from_dict(json.load(fh)))
        except Exception:
            pass

    def _save_cookies(self):
        self._save_json(COOKIE_FILE, dict_from_cookiejar(self.s.cookies))

    # ---------- 事件 ----------
    def on_switch(self, callback):
        """接口自动切换时的回调：callback(capability, old, new)"""
        self._switch_listeners.append(callback)

    def _emit_switch(self, capability, old, new):
        _log("接口自动切换: %s %s -> %s" % (capability, old, new))
        for callback in list(self._switch_listeners):
            try:
                callback(capability, old, new)
            except Exception:
                pass

    # ---------- HTTP ----------
    def request(self, method, path, params=None, data=None, allow_fail=False,
                timeout=12):
        url = path if path.startswith("http") else BASE + path
        resp = self.s.request(method, url, params=params, data=data, timeout=timeout)
        if resp.status_code >= 500:
            raise RouteError("服务端 %s" % resp.status_code)
        payload = parse_json(resp)
        if not allow_fail and isinstance(payload, dict):
            code = payload.get("code")
            if code not in (None, 200, 801, 802, 803, 800):
                raise RouteError("接口返回 code=%s %s" % (code, payload.get("message", "")))
        return payload

    def raw(self, method, path):
        url = path if path.startswith("http") else BASE + path
        return self.s.request(method, url, timeout=12, allow_redirects=True)

    def weapi(self, path, payload, timeout=12):
        """加密 POST（weapi）：登录类接口现在必须加密，明文会被判 401 ENC"""
        if not HAS_WEAPI:
            raise RouteError("缺少 cryptography，无法调用加密接口")
        if isinstance(payload, dict) and "csrf_token" not in payload:
            payload = dict(payload)
            try:
                payload["csrf_token"] = self.s.cookies.get("__csrf") or ""
            except Exception:  # noqa: BLE001
                payload["csrf_token"] = ""
        resp = self.s.post(BASE + path, data=weapi_form(payload), timeout=timeout)
        if resp.status_code >= 500:
            raise RouteError("服务端 %s" % resp.status_code)
        data = parse_json(resp)
        if not isinstance(data, dict):
            raise RouteError("响应结构异常")
        code = data.get("code")
        if code not in (None, 200, 800, 801, 802, 803):
            raise RouteError("接口返回 code=%s %s" % (code, data.get("message", "")))
        return data

    # ---------- 登录态 cookie ----------
    _COOKIE_ATTRS = {"max-age", "expires", "path", "domain", "httponly",
                     "secure", "samesite", "version", "comment", "expires"}

    @classmethod
    def _cookie_pairs(cls, raw):
        pairs = {}
        for part in str(raw).replace("\n", ";").split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            if not key or key.lower() in cls._COOKIE_ATTRS:
                continue
            pairs[key] = value.strip()
        return pairs

    def absorb_login_cookie(self, payload, tag=""):
        """把响应体里的 cookie 字段并进会话（部分登录接口只放在 body 里）"""
        if not isinstance(payload, dict):
            return False
        raw = None
        for holder in (payload, payload.get("data"), payload.get("result")):
            if not isinstance(holder, dict):
                continue
            for key in ("cookie", "cookies", "set-cookie", "setCookie"):
                if holder.get(key):
                    raw = holder[key]
                    break
            if raw:
                break
        if not raw:
            return False
        if isinstance(raw, (list, tuple)):
            raw = "; ".join(str(item) for item in raw)
        pairs = self._cookie_pairs(raw)
        if not pairs:
            return False
        self.s.cookies.update(cookiejar_from_dict(pairs))
        _log("从%s响应体合并 cookie: %s" % (tag or "登录", ",".join(sorted(pairs))))
        return True

    def log_cookie_state(self, tag=""):
        names = sorted(dict_from_cookiejar(self.s.cookies).keys())
        _log("%s 当前 cookie: %s" % (tag or "登录", ",".join(names) or "空"))

    # ---------- 路由核心 ----------
    def _routes_for(self, capability):
        routes = [r for r in ROUTE_TABLE.get(capability, [])]
        for entry in self._custom_routes.get(capability, []):
            routes.insert(0, self._build_custom(capability, entry))
        if not routes:
            raise CapabilityError(capability, [(capability, "没有可用方案")])
        return routes

    def _build_custom(self, capability, entry):
        method = (entry.get("method") or "GET").upper()
        path = entry.get("path") or ""
        params_tpl = entry.get("params") or {}
        data_tpl = entry.get("data") or {}

        def handler(client, **kwargs):
            params = {k: _format_value(v, kwargs) for k, v in params_tpl.items()}
            data = {k: _format_value(v, kwargs) for k, v in data_tpl.items()}
            payload = client.request(method, path,
                                     params=params or None, data=data or None)
            if capability == "search":
                return extract_songs(payload)
            if capability == "song_url":
                return extract_url(payload, kwargs.get("song_id"))
            if capability == "lyric":
                return extract_lyric(payload)
            raise RouteError("自定义方案暂不支持该能力")

        return Route(capability, entry.get("name", "custom"), handler,
                     entry.get("description", "来自 endpoints.json"), weight=0)

    def call(self, capability, **kwargs):
        routes = self._routes_for(capability)
        preferred = self._routes_cache.get(capability)
        # 升级后若新增了优先级更高的方案（如加密登录），先试新的，不沿用旧缓存
        if preferred:
            cached = next((r for r in routes if r.name == preferred), None)
            if cached is None or cached.weight > min(r.weight for r in routes):
                preferred = None
        ordered = sorted(routes, key=lambda r: (0 if r.name == preferred else 1,
                                                r.weight))
        attempts = []
        for candidate in ordered:
            try:
                result = candidate.handler(self, **kwargs)
            except Exception as exc:
                attempts.append((candidate.name, str(exc)))
                _log("方案失败 %s/%s: %s" % (capability, candidate.name, exc))
                continue
            if preferred and candidate.name != preferred:
                self._emit_switch(capability, preferred, candidate.name)
            elif not preferred:
                _log("选定方案 %s -> %s" % (capability, candidate.name))
            if self._routes_cache.get(capability) != candidate.name:
                self._routes_cache[capability] = candidate.name
                self._save_json(ROUTES_FILE, self._routes_cache)
            self._fail_streak[capability] = 0
            return result
        self._fail_streak[capability] = self._fail_streak.get(capability, 0) + 1
        _log("能力全部失败 %s: %s" % (capability, attempts))
        raise CapabilityError(capability, attempts)

    # ---------- 对外能力 ----------
    def fetch_account(self):
        try:
            self.account = self.call("account")
            self._save_cookies()
        except CapabilityError as exc:
            _log("账号查询失败: %s" % exc)
            self.account = None
        return self.account

    @property
    def is_login(self):
        return bool(self.account)

    def _uid(self):
        if not self.account:
            return None
        return self.account.get("id") or self.account.get("userId")

    def search_songs(self, keyword, limit=30, offset=0):
        return self.call("search", keyword=keyword, limit=limit, offset=offset)

    def song_url(self, song_id, level=None):
        try:
            return self.call("song_url", song_id=song_id, level=level)
        except CapabilityError as exc:
            # 多数情况是版权/VIP 限制，不是接口故障：降级为“不可播放”
            _log("播放地址不可用: %s" % exc)
            return None

    def lyric(self, song_id):
        try:
            return self.call("lyric", song_id=song_id)
        except CapabilityError:
            return ""

    def comments(self, song_id, limit=20, offset=0):
        """读取歌曲评论；公开评论无需登录，接口失败时自动换新版端点"""
        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        errors = []
        thread = "R_SO_4_%s" % song_id

        # 1) 公开 GET，最稳定，也最容易在未登录时使用
        try:
            payload = self.request(
                "GET", "/api/v1/resource/comments/%s" % thread,
                params={"rid": song_id, "limit": limit,
                        "offset": offset, "beforeTime": 0},
                allow_fail=True)
            code = payload.get("code")
            if code not in (None, 200):
                raise RouteError("公开评论接口返回 %s" % code)
            result = extract_comments(payload)
            if result["hot"] or result["latest"] or result["total"] == 0:
                return result
            errors.append("公开评论接口无数据")
        except Exception as exc:  # noqa: BLE001
            errors.append("公开评论接口: %s" % exc)

        # 2) weapi 加密版
        try:
            payload = self.weapi("/weapi/v1/resource/comments/%s" % thread, {
                "rid": song_id, "limit": limit,
                "offset": offset, "beforeTime": 0,
            })
            return extract_comments(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append("weapi 评论接口: %s" % exc)

        # 3) 新版 v2 评论列表，作为最后的兼容方案
        try:
            payload = self.weapi("/weapi/v2/resource/comments", {
                "threadId": thread,
                "pageNo": offset // limit + 1,
                "showInner": True,
                "pageSize": limit,
                "cursor": "normalHot#%d" % offset,
                "sortType": 99,
            })
            return extract_comments(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append("v2 评论接口: %s" % exc)

        _log("评论读取失败: %s" % "; ".join(errors))
        raise RouteError("评论加载失败，请稍后重试")

    def add_comment(self, song_id, content):
        """发表歌曲评论；需要有效的 MUSIC_U 登录态"""
        content = (content or "").strip()
        if not content:
            raise RouteError("评论内容不能为空")
        if len(content) > 140:
            raise RouteError("评论最多 140 字")
        if not self.account:
            raise RouteError("请先登录后再发表评论")
        payload = self.weapi("/weapi/resource/comments/add", {
            "threadId": "R_SO_4_%s" % song_id,
            "content": content,
        })
        code = payload.get("code")
        if code not in (None, 200):
            raise RouteError(payload.get("message") or ("发表失败（code=%s）" % code))
        return payload

    def playlist_detail(self, playlist_id):
        return self.call("playlist", playlist_id=playlist_id)

    def recommend_playlists(self, limit=12):
        return self.call("recommend", limit=limit)

    def daily_songs(self):
        """每日推荐歌曲（需登录；失败返回空列表，界面上给提示）"""
        try:
            return self.call("daily")
        except CapabilityError as exc:
            _log("每日推荐失败: %s" % exc)
            return []

    def radar_playlist(self):
        """私人雷达：从推荐歌单里挑名字带「私人雷达」的那一个"""
        try:
            items = self.call("recommend", limit=30)
        except CapabilityError:
            return None
        for item in items:
            if "私人雷达" in (item.get("name") or ""):
                return item.get("id")
        return None

    def intelligence_list(self, song_id, playlist_id=None):
        """心动模式：以某首歌为种子生成一组歌曲"""
        playlist_id = playlist_id or self.radar_playlist()
        if not playlist_id:
            raise CapabilityError("intelligence", [("seed", "找不到可用的种子歌单")])
        return self.call("intelligence", playlist_id=playlist_id, song_id=song_id)

    def user_playlists(self, uid=None):
        uid = uid or self._uid()
        if not uid:
            return []
        try:
            return self.call("user_playlists", uid=uid)
        except CapabilityError:
            return []

    def tracks_by_ids(self, track_ids):
        songs = {}
        for start in range(0, len(track_ids), 200):
            chunk = [i for i in track_ids[start:start + 200] if i]
            try:
                payload = self.request("GET", "/api/song/detail",
                                       {"ids": json.dumps(chunk)})
            except Exception:
                continue
            items = _walk_lists(payload, ("songs", "tracks")) or []
            for song in items:
                if isinstance(song, dict):
                    songs[song.get("id")] = song
        return [songs[i] for i in track_ids if i in songs]

    def album_detail(self, album_id):
        """专辑详情；优先旧版接口，必要时切到 v1/weapi"""
        errors = []
        for path in ("/api/album/%s", "/api/v1/album/%s"):
            try:
                payload = self.request("GET", path % album_id, allow_fail=True)
                if payload.get("code") not in (None, 200):
                    raise RouteError("接口返回 code=%s" % payload.get("code"))
                result = extract_album(payload)
                if result.get("songs") or result.get("name"):
                    return result
            except Exception as exc:  # noqa: BLE001
                errors.append("%s: %s" % (path, exc))
        try:
            payload = self.weapi("/weapi/v1/album/%s" % album_id, {})
            return extract_album(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append("weapi: %s" % exc)
        _log("专辑读取失败: %s" % "; ".join(errors))
        raise RouteError("专辑加载失败，请稍后重试")

    def artist_detail(self, artist_id, name=""):
        """歌手详情与热门歌曲；兼容老版歌手接口和 v1 接口"""
        errors = []
        for path in ("/api/v1/artist/%s", "/api/artist/%s"):
            try:
                payload = self.request("GET", path % artist_id, allow_fail=True)
                if payload.get("code") not in (None, 200):
                    raise RouteError("接口返回 code=%s" % payload.get("code"))
                result = extract_artist(payload, artist_id)
                if result.get("name") or result.get("songs"):
                    if not result.get("name"):
                        result["name"] = name
                    return result
            except Exception as exc:  # noqa: BLE001
                errors.append("%s: %s" % (path, exc))
        # 老接口没有热门歌曲时，用歌手热门歌曲接口兜底
        try:
            payload = self.request("GET", "/api/artist/top/song",
                                   params={"id": artist_id}, allow_fail=True)
            if payload.get("code") not in (None, 200):
                raise RouteError("接口返回 code=%s" % payload.get("code"))
            result = extract_artist(payload, artist_id)
            result["name"] = name or result.get("name") or ""
            if result.get("songs"):
                return result
        except Exception as exc:  # noqa: BLE001
            errors.append("top/song: %s" % exc)
        _log("歌手读取失败: %s" % "; ".join(errors))
        raise RouteError("歌手页加载失败，请稍后重试")

    def artist_albums(self, artist_id, limit=30, max_total=500):
        """歌手专辑列表；分页读取，接口路径变化时尝试 v1 兼容路径"""
        errors = []
        for path in ("/api/artist/albums/%s", "/api/v1/artist/albums/%s"):
            albums = []
            seen = set()
            offset = 0
            try:
                while offset < max_total:
                    payload = self.request(
                        "GET", path % artist_id,
                        params={"limit": limit, "offset": offset},
                        allow_fail=True)
                    if payload.get("code") not in (None, 200):
                        raise RouteError("接口返回 code=%s" % payload.get("code"))
                    chunk = extract_artist_albums(payload)
                    raw = _first(payload.get("hotAlbums"), payload.get("albums"),
                                 _walk_lists(payload, ("hotAlbums", "albums")))
                    for album in chunk:
                        aid = album.get("id")
                        if aid and aid not in seen:
                            seen.add(aid)
                            albums.append(album)
                    # 200 且明确返回空列表，说明该歌手没有专辑，不是接口故障
                    if not chunk and isinstance(raw, list):
                        return albums
                    if not chunk or len(chunk) < limit:
                        break
                    if not payload.get("more"):
                        break
                    offset += len(chunk)
                return albums
            except Exception as exc:  # noqa: BLE001
                errors.append("%s: %s" % (path, exc))
        _log("歌手专辑读取失败: %s" % "; ".join(errors))
        raise RouteError("歌手专辑加载失败，请稍后重试")

    def liked_song_ids(self):
        """当前账号喜欢的歌曲 id 列表"""
        if not self.account:
            self._liked_ids = set()
            return []
        uid = self._uid()
        if not uid:
            return []
        try:
            payload = self.request(
                "POST", "/api/song/like/get", data={"uid": uid}, timeout=12)
        except Exception as exc:  # noqa: BLE001
            _log("喜欢列表读取失败: %s" % exc)
            return []
        ids = payload.get("ids") if isinstance(payload, dict) else None
        if not isinstance(ids, list):
            return []
        ids = [i for i in ids if i]
        self._liked_ids = set(ids)
        return ids

    def liked_songs(self):
        """返回带封面、歌手、专辑信息的喜欢的歌曲"""
        ids = self.liked_song_ids()
        if not ids:
            return []
        raw = self.tracks_by_ids(ids)
        return [normalize_song(song) for song in raw if isinstance(song, dict)]

    def is_favorite(self, song_id):
        if not song_id or self._liked_ids is None:
            return False
        try:
            return int(song_id) in self._liked_ids
        except (TypeError, ValueError):
            return False

    def set_favorite(self, song_id, liked=True):
        """喜欢或取消喜欢一首歌，成功后同步本地缓存"""
        if not self.account:
            raise RouteError("请先登录后再管理喜欢的音乐")
        uid = self._uid()
        if not uid:
            raise RouteError("登录态缺少用户 id")
        liked = bool(liked)
        errors = []
        payload = None
        try:
            payload = self.request(
                "POST", "/api/song/like",
                data={"trackId": song_id, "userid": uid,
                      "like": "true" if liked else "false"}, timeout=12)
        except Exception as exc:  # noqa: BLE001
            errors.append("song/like: %s" % exc)
            try:
                payload = self.weapi("/weapi/radio/like", {
                    "alg": "itembased", "trackId": song_id,
                    "like": liked, "time": "3",
                })
            except Exception as exc2:  # noqa: BLE001
                errors.append("radio/like: %s" % exc2)
        if not isinstance(payload, dict) or payload.get("code") not in (None, 200):
            _log("喜欢操作失败: %s" % ("; ".join(errors) or payload))
            raise RouteError("喜欢操作失败，请稍后重试")
        try:
            self._liked_ids = self._liked_ids or set()
            if liked:
                self._liked_ids.add(int(song_id))
            else:
                self._liked_ids.discard(int(song_id))
        except (TypeError, ValueError):
            pass
        return liked

    # ---------- 登录 ----------
    def qr_unikey(self):
        return self.call("qr_unikey")

    @staticmethod
    def qr_url(unikey):
        return "https://music.163.com/login?codekey=%s" % unikey

    def qr_check(self, unikey):
        return self.call("qr_check", unikey=unikey)

    def login_phone(self, phone, password, countrycode="86"):
        """手机号密码登录（备用通道，走加密接口）"""
        self.call("login_phone", phone=phone, password=password,
                  countrycode=countrycode)
        return self.after_login()

    def login_email(self, email, password):
        """网易邮箱密码登录（备用通道）"""
        self.call("login_email", email=email, password=password)
        return self.after_login()

    def send_sms_code(self, phone, countrycode="86"):
        """给手机号发登录验证码"""
        return self.call("sms_send", phone=phone, countrycode=countrycode)

    def login_sms(self, phone, code, countrycode="86"):
        """短信验证码登录（不用密码，绕开密码风控）"""
        self.call("sms_login", phone=phone, code=code, countrycode=countrycode)
        return self.after_login()

    def import_cookie(self, text):
        """导入浏览器里的 cookie（网易风控下最可靠的登录方式）

        支持三种粘贴格式：
        1. 整串 cookie：MUSIC_U=xxx; __csrf=yyy; ...
        2. JSON：{"MUSIC_U": "xxx", ...}
        3. 只粘贴 MUSIC_U 的值
        """
        raw = (text or "").strip()
        if not raw:
            raise ValueError("cookie 内容为空")
        pairs = {}
        if raw.startswith("{") or raw.startswith("["):
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            if isinstance(data, dict):
                pairs = {k: v for k, v in data.items() if isinstance(v, str) and v}
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("name"):
                        pairs[item["name"]] = str(item.get("value") or "")
        if not pairs:
            pairs = self._cookie_pairs(raw)
        if not pairs:
            pairs = {"MUSIC_U": raw}
        if not pairs.get("MUSIC_U"):
            raise ValueError("没有找到 MUSIC_U，请复制完整的 cookie")
        self.s.cookies.update(cookiejar_from_dict(pairs))
        self._save_cookies()
        self.log_cookie_state("导入 cookie")
        account = self.fetch_account()
        if not account:
            raise RuntimeError("cookie 无效或已过期，请重新登录网页版后再复制")
        return account

    def after_login(self):
        """扫码成功后收尾：落盘 cookie → 等登录态生效 → 连续校验账号"""
        self._save_cookies()
        self.log_cookie_state("扫码完成")
        for attempt in range(3):
            if attempt:
                time.sleep(1.5 * attempt)
            try:
                account = self.call("account")
            except Exception as exc:
                _log("账号校验失败(第%d次): %s" % (attempt + 1, exc))
                continue
            if account:
                self.account = account
                self._save_cookies()
                self.log_cookie_state("登录成功")
                return account
            _log("账号校验返回空(第%d次)，等待 cookie 生效" % (attempt + 1))
        self.account = None
        self.log_cookie_state("登录失败")
        return None

    def logout(self):
        try:
            self.s.post(BASE + "/api/logout", timeout=8)
        except Exception:
            pass
        self.s.cookies.clear()
        self.account = None
        self._liked_ids = None
        try:
            os.remove(COOKIE_FILE)
        except OSError:
            pass


def _format_value(template, kwargs):
    if isinstance(template, str):
        for key, value in kwargs.items():
            template = template.replace("{%s}" % key, str(value))
        return template
    return template


ROUTE_TABLE = {}
for _item in list(globals().values()):
    if isinstance(_item, Route):
        ROUTE_TABLE.setdefault(_item.capability, []).append(_item)
