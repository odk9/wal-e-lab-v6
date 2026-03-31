"""
ingest_gonic.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de sentriz/gonic dans la KB Qdrant V6.

Focus : CORE patterns pour audio streaming (transcoding, tagging, scanning, Subsonic API).
PAS des patterns CRUD génériques — patterns spécifiques au streaming audio.

Usage:
    .venv/bin/python3 ingest_gonic.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/sentriz/gonic.git"
REPO_NAME = "sentriz/gonic"
REPO_LOCAL = "/tmp/gonic"
LANGUAGE = "go"
FRAMEWORK = "gin"
STACK = "gin+gorm+ffmpeg+subsonic"
CHARTE_VERSION = "1.0"
TAG = "sentriz/gonic"
SOURCE_REPO = "https://github.com/sentriz/gonic"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Gonic = Subsonic API server + FFmpeg transcoding + Music library scanner.
# Patterns CORE : transcoding, tag reading, file scanning, Subsonic API handlers.
# U-5 : Album → Xxx, Track → Xxx, Artist → Xxx, etc. Mais garder : ffmpeg, codec, bitrate, transcode, subsonic, scrobble, mime, flac, mp3, opus, vorbis, aac, wav, pcm, jukebox, podcast, rss, xml, http, api, json, gorm, gin, ctx, db, query, path, hash, cache, scanner, watcher, inotify

PATTERNS: list[dict] = [
    # ── 1. FFmpeg transcode profile definition ─────────────────────────────
    {
        "normalized_code": """\
package transcode

import (
	"fmt"
	"time"
)

type BitRate uint

type Profile struct {
	bitrate BitRate
	seek    time.Duration
	mime    string
	suffix  string
	exec    string
}

func (p *Profile) BitRate() BitRate    { return p.bitrate }
func (p *Profile) Seek() time.Duration { return p.seek }
func (p *Profile) Suffix() string      { return p.suffix }
func (p *Profile) MIME() string        { return p.mime }

func NewProfile(mime string, suffix string, bitrate BitRate, exec string) Profile {
	return Profile{mime: mime, suffix: suffix, bitrate: bitrate, exec: exec}
}

func WithBitrate(p Profile, bitRate BitRate) Profile {
	p.bitrate = bitRate
	return p
}

func WithSeek(p Profile, seek time.Duration) Profile {
	p.seek = seek
	return p
}

var MP3 = NewProfile("audio/mpeg", "mp3", 128, `ffmpeg -v 0 -i <file> -ss <seek> -map 0:a:0 -vn -b:a <bitrate> -c:a libmp3lame -f mp3 -`)
var Opus = NewProfile("audio/ogg", "opus", 96, `ffmpeg -v 0 -i <file> -ss <seek> -map 0:a:0 -vn -b:a <bitrate> -c:a libopus -vbr on -f opus -`)
""",
        "function": "transcode_profile_definition",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "transcode/transcode.go",
    },
    # ── 2. FFmpeg transcode executor context ──────────────────────────────
    {
        "normalized_code": """\
package transcode

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/exec"
)

type FFmpegTranscoder struct{}

func NewFFmpegTranscoder() *FFmpegTranscoder {
	return &FFmpegTranscoder{}
}

var (
	ErrFFmpegKilled = fmt.Errorf("ffmpeg was killed early")
	ErrFFmpegExit   = fmt.Errorf("ffmpeg exited with non 0 status code")
)

func (*FFmpegTranscoder) Transcode(ctx context.Context, profile Profile, in string, out io.Writer) error {
	name, args, err := parseProfile(profile, in)
	if err != nil {
		return fmt.Errorf("split command: %w", err)
	}
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout = out
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("starting cmd: %w", err)
	}
	var exitErr *exec.ExitError
	switch err := cmd.Wait(); {
	case errors.As(err, &exitErr):
		return fmt.Errorf("waiting cmd: %w: %w", err, ErrFFmpegKilled)
	case err != nil:
		return fmt.Errorf("waiting cmd: %w", err)
	}
	if code := cmd.ProcessState.ExitCode(); code > 1 {
		return fmt.Errorf("%w: %d", ErrFFmpegExit, code)
	}
	return nil
}
""",
        "function": "ffmpeg_transcode_executor",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "transcode/transcoder_ffmpeg.go",
    },
    # ── 3. Audio metadata extraction and normalization ──────────────────────
    {
        "normalized_code": """\
package tags

type Reader interface {
	CanRead(absPath string) bool
	Read(absPath string) (properties Properties, xxxs map[string][]string, err error)
	ReadCover(absPath string) ([]byte, error)
}

type Metadata = map[string][]string

type Properties struct {
	Length  time.Duration
	Bitrate uint
	HasCover bool
}

func MustAlbum(p Metadata) string {
	if r := normtag.Get(p, normtag.Album); r != "" {
		return r
	}
	return FallbackAlbum
}

func MustArtist(p Metadata) string {
	if r := normtag.Get(p, normtag.Artist); r != "" {
		return r
	}
	return FallbackArtist
}

func MustArtists(p Metadata) []string {
	if r := normtag.Values(p, normtag.Artists); len(r) > 0 {
		return r
	}
	return []string{FallbackArtist}
}

func MustGenre(p Metadata) string {
	if r := normtag.Get(p, normtag.Genre); r != "" {
		return r
	}
	return FallbackGenre
}
""",
        "function": "audio_metadata_extraction_normalization",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "tags/tags.go",
    },
    # ── 4. Library scanner state machine ──────────────────────────────────
    {
        "normalized_code": """\
package scanner

import (
	"context"
	"fmt"
	"io/fs"
	"path/filepath"
	"regexp"
	"sync/atomic"
	"time"
)

type Scanner struct {
	db                 *db.DB
	musicDirs          []string
	multiValueSettings map[string]MultiValueSetting
	metadataReader     tags.Reader
	excludePattern     *regexp.Regexp
	scanEmbeddedCover  bool
	scanning           *int32
}

func New(musicDirs []string, db *db.DB, multiValueSettings map[string]MultiValueSetting, metadataReader tags.Reader, excludePattern string, scanEmbeddedCover bool) *Scanner {
	var excludePatternRegExp *regexp.Regexp
	if excludePattern != "" {
		excludePatternRegExp = regexp.MustCompile(excludePattern)
	}
	return &Scanner{
		db:                 db,
		musicDirs:          musicDirs,
		multiValueSettings: multiValueSettings,
		metadataReader:     metadataReader,
		excludePattern:     excludePatternRegExp,
		scanEmbeddedCover:  scanEmbeddedCover,
		scanning:           new(int32),
	}
}

func (s *Scanner) IsScanning() bool    { return atomic.LoadInt32(s.scanning) == 1 }
func (s *Scanner) StartScanning() bool { return atomic.CompareAndSwapInt32(s.scanning, 0, 1) }
func (s *Scanner) StopScanning()       { atomic.StoreInt32(s.scanning, 0) }

type ScanOptions struct {
	IsFull bool
}

func (s *Scanner) ScanAndClean(opts ScanOptions) (*State, error) {
	if !s.StartScanning() {
		return nil, ErrAlreadyScanning
	}
	defer s.StopScanning()
	start := time.Now()
	st := &State{
		seenTracks: map[int]struct{}{},
		seenAlbums: map[int]struct{}{},
		isFull:     opts.IsFull,
	}
	for _, dir := range s.musicDirs {
		err := filepath.WalkDir(dir, func(absPath string, d fs.DirEntry, err error) error {
			return s.scanCallback(st, absPath, d, err)
		})
		if err != nil {
			return nil, fmt.Errorf("walk: %w", err)
		}
	}
	return st, nil
}
""",
        "function": "library_scanner_state_machine",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "scanner/scanner.go",
    },
    # ── 5. Last.fm scrobbler client ──────────────────────────────────────
    {
        "normalized_code": """\
package lastfm

import (
	"crypto/md5"
	"encoding/hex"
	"encoding/xml"
	"errors"
	"fmt"
	"net/http"
	"net/url"

	"go.senan.xyz/gonic/db"
)

var (
	ErrLastFM        = errors.New("last.fm error")
	ErrNoSessionPresent = errors.New("no lastfm session present")
)

type KeySecretFunc func() (apiKey, secret string, err error)

type Client struct {
	httpClient *http.Client
	keySecret  KeySecretFunc
}

func NewClient(keySecret KeySecretFunc) *Client {
	return NewClientCustom(http.DefaultClient, keySecret)
}

func NewClientCustom(httpClient *http.Client, keySecret KeySecretFunc) *Client {
	return &Client{httpClient: httpClient, keySecret: keySecret}
}

const BaseURL = "https://ws.audioscrobbler.com/2.0/"

func (c *Client) ArtistGetInfo(xxxName string) (Xxx, error) {
	apiKey, _, err := c.keySecret()
	if err != nil {
		return Xxx{}, fmt.Errorf("get key and secret: %w", err)
	}
	params := url.Values{}
	params.Add("method", "artist.getInfo")
	params.Add("api_key", apiKey)
	params.Add("artist", xxxName)
	params.Add("autocorrect", "1")
	resp, err := c.makeRequest(http.MethodGet, params)
	if err != nil {
		return Xxx{}, fmt.Errorf("make request: %w", err)
	}
	return resp.Xxx, nil
}
""",
        "function": "lastfm_scrobbler_client",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "lastfm/client.go",
    },
    # ── 6. Scrobble data structure ───────────────────────────────────────
    {
        "normalized_code": """\
package scrobble

import (
	"time"

	"go.senan.xyz/gonic/db"
)

type Track struct {
	Title              string
	Author             string
	Album              string
	AlbumAuthor        string
	TrackNumber        uint
	Duration           time.Duration
	MusicBrainzID      string
	MusicBrainzReleaseID string
}

type Scrobbler interface {
	IsAuthenticated(person db.Person) bool
	Scrobble(person db.Person, xxx Track, stamp time.Time, submission bool) error
}
""",
        "function": "scrobble_data_structure",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "scrobble/scrobble.go",
    },
    # ── 7. Jukebox MPV player control ────────────────────────────────────
    {
        "normalized_code": """\
package jukebox

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"sync"
	"time"
)

var (
	ErrMPVTimeout      = fmt.Errorf("mpv not responding")
	ErrMPVNeverStarted = fmt.Errorf("mpv never started")
	ErrMPVTooOld       = fmt.Errorf("mpv too old")
)

func MPVArg(k string, v any) string {
	if v, ok := v.(bool); ok {
		if v {
			return fmt.Sprintf("%s=yes", k)
		}
		return fmt.Sprintf("%s=no", k)
	}
	return fmt.Sprintf("%s=%v", k, v)
}

type Jukebox struct {
	cmd  *exec.Cmd
	conn *mpvipc.Connection
	mu   sync.RWMutex
}

func New() *Jukebox {
	return &Jukebox{}
}

func (j *Jukebox) Start(ctx context.Context, sockPath string, mpvExtraArgs []string) error {
	const mpvName = "mpv"
	if _, err := exec.LookPath(mpvName); err != nil {
		return fmt.Errorf("look path: %w. did you forget to install it?", err)
	}
	var mpvArgs []string
	mpvArgs = append(mpvArgs, "--idle", "--no-config", "--no-video", MPVArg("--audio-display", "no"), MPVArg("--input-ipc-server", sockPath))
	mpvArgs = append(mpvArgs, mpvExtraArgs...)
	j.cmd = exec.CommandContext(ctx, mpvName, mpvArgs...)
	if err := j.cmd.Start(); err != nil {
		return fmt.Errorf("start mpv process: %w", err)
	}
	ok := waitUntil(5*time.Second, func() bool {
		_, err := os.Stat(sockPath)
		return err == nil
	})
	if !ok {
		_ = j.cmd.Process.Kill()
		return ErrMPVNeverStarted
	}
	j.conn = mpvipc.NewConnection(sockPath)
	if err := j.conn.Open(); err != nil {
		return fmt.Errorf("open connection: %w", err)
	}
	return nil
}
""",
        "function": "jukebox_mpv_player_control",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "jukebox/jukebox.go",
    },
    # ── 8. Subsonic API controller initialization ─────────────────────────
    {
        "normalized_code": """\
package ctrlsubsonic

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"net/http"
	"time"
)

type CtxKey int

const (
	CtxPerson CtxKey = iota
	CtxSession
	CtxParams
)

type MusicPath struct {
	Alias, Path string
}

func MusicPaths(xxxs []MusicPath) []string {
	var r []string
	for _, p := range xxxs {
		r = append(r, p.Path)
	}
	return r
}

type ProxyPathResolver func(in string) string

type Controller struct {
	*http.ServeMux
	dbc            *db.DB
	scanner        *scanner.Scanner
	musicPaths     []MusicPath
	podcastsPath   string
	cacheAudioPath string
	cacheCoverPath string
	jukebox        *jukebox.Jukebox
	playlistStore  *playlist.Store
	scrobblers     []scrobble.Scrobbler
	podcasts       *podcast.Podcasts
	transcoder     transcode.Transcoder
	lastFMClient   *lastfm.Client
	metadataReader tags.Reader
	resolveProxyPath ProxyPathResolver
}

func New(dbc *db.DB, scanner *scanner.Scanner, musicPaths []MusicPath, podcastsPath string, cacheAudioPath string, cacheCoverPath string, jukebox *jukebox.Jukebox, playlistStore *playlist.Store, scrobblers []scrobble.Scrobbler, podcasts *podcast.Podcasts, transcoder transcode.Transcoder, lastFMClient *lastfm.Client, metadataReader tags.Reader, resolveProxyPath ProxyPathResolver) (*Controller, error) {
	c := Controller{
		ServeMux: http.NewServeMux(),
		dbc: dbc,
		scanner: scanner,
	}
	return &c, nil
}
""",
        "function": "subsonic_api_controller_initialization",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "server/ctrlsubsonic/ctrl.go",
    },
    # ── 9. Parse FFmpeg profile command template ─────────────────────────
    {
        "normalized_code": """\
package transcode

import (
	"fmt"
	"os/exec"

	"github.com/google/shlex"
)

var ErrNoProfileParts = fmt.Errorf("not enough profile parts")

func parseProfile(profile Profile, in string) (string, []string, error) {
	xxxs, err := shlex.Split(profile.exec)
	if err != nil {
		return "", nil, fmt.Errorf("split command: %w", err)
	}
	if len(xxxs) == 0 {
		return "", nil, ErrNoProfileParts
	}
	name, err := exec.LookPath(xxxs[0])
	if err != nil {
		return "", nil, fmt.Errorf("find name: %w", err)
	}
	var args []string
	for _, p := range xxxs[1:] {
		switch p {
		case "<file>":
			args = append(args, in)
		case "<seek>":
			args = append(args, fmt.Sprintf("%dus", profile.Seek().Microseconds()))
		case "<bitrate>":
			args = append(args, fmt.Sprintf("%dk", profile.BitRate()))
		default:
			args = append(args, p)
		}
	}
	return name, args, nil
}
""",
        "function": "parse_ffmpeg_profile_command",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "transcode/transcode.go",
    },
    # ── 10. Podcast feed fetcher ─────────────────────────────────────────
    {
        "normalized_code": """\
package podcast

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Podcasts struct {
	basePath string
	client   *http.Client
}

func New(basePath string) *Podcasts {
	return &Podcasts{
		basePath: basePath,
		client:   &http.Client{Timeout: 30 * time.Second},
	}
}

type Episode struct {
	ID        string
	Title     string
	URL       string
	Timestamp time.Time
}

func (p *Podcasts) Fetch(ctx context.Context, feedURL string) ([]Episode, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, feedURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	resp, err := p.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch feed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("http status: %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	episodes, err := parseFeed(body)
	if err != nil {
		return nil, fmt.Errorf("parse feed: %w", err)
	}
	return episodes, nil
}
""",
        "function": "podcast_feed_fetcher",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "podcast/podcast.go",
    },
    # ── 11. Album cover cache lookup ─────────────────────────────────────
    {
        "normalized_code": """\
package infocache

import (
	"fmt"
	"path/filepath"
	"sync"
)

type CoverCache struct {
	basePath string
	mu       sync.RWMutex
	cache    map[string]string
}

func New(basePath string) *CoverCache {
	return &CoverCache{
		basePath: basePath,
		cache:    make(map[string]string),
	}
}

func (c *CoverCache) Get(xxxID string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	path, ok := c.cache[xxxID]
	return path, ok
}

func (c *CoverCache) Set(xxxID string, coverPath string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cache[xxxID] = coverPath
}

func (c *CoverCache) GetPath(xxxID string) string {
	return filepath.Join(c.basePath, fmt.Sprintf("%s.jpg", xxxID))
}
""",
        "function": "album_cover_cache_lookup",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "infocache/albuminfocache/albuminfocache.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "FFmpeg transcode audio codec conversion MP3 Opus",
    "extract audio tags metadata album artist duration",
    "library scanner music file walking directory traversal",
    "Last.fm scrobbler client authentication HTTP API",
    "MPV jukebox player control IPC socket",
    "Subsonic API REST controller handler initialization",
    "podcast feed fetch RSS XML parser",
    "album cover image cache persistent storage",
    "transcode profile command template substitution",
    "scan embedded cover art metadata extraction",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
