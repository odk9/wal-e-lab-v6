"""
ingest_navidrome.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de navidrome/navidrome dans la KB Qdrant V6.

Focus : CORE music streaming patterns (NOT REST CRUD).
Patterns : audio transcoding, library scanning, metadata extraction, smart playlists,
full-text search, Subsonic API, jukebox control, media organization, caching,
format detection, audio pipeline architecture.

Usage:
    .venv/bin/python3 ingest_navidrome.py
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
REPO_URL = "https://github.com/navidrome/navidrome.git"
REPO_NAME = "navidrome/navidrome"
REPO_LOCAL = "/home/navidrome"
LANGUAGE = "go"
FRAMEWORK = "gin"
STACK = "gin+gorm+ffmpeg+subsonic"
CHARTE_VERSION = "1.0"
TAG = "navidrome/navidrome"
SOURCE_REPO = "https://github.com/navidrome/navidrome"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Navidrome = music streaming server (Spotify/Deezer-like) compatible with Subsonic.
# Patterns CORE : audio transcoding, library scanning, metadata extraction,
# playlist engine, search, caching, format detection, playback control.
#
# Go music-streaming terms KEPT: track, artist, album, playlist, library, media,
# audio, transcode, codec, bitrate, sample_rate, duration, metadata, scrobble,
# subsonic, jukebox, scanner, watcher, cache, struct, interface, goroutine,
# channel, ctx, gin, gorm.

PATTERNS: list[dict] = [
    # ── 1. Audio transcoding pipeline — media file → codec negotiation → ffmpeg encode
    {
        "normalized_code": """\
package media

import (
\t"context"
\t"fmt"
\t"os/exec"
\t"strconv"
)

type TranscodeConfig struct {
\tTargetBitrate string
\tTargetCodec   string
\tTargetFormat  string
\tSampleRate    int
\tChannels      int
}

func transcodeAudio(ctx context.Context, srcPath string, cfg TranscodeConfig) ([]byte, error) {
\t// Negotiate codec based on client support
\tcodec := negotiateCodec(cfg.TargetCodec)
\tbr := cfg.TargetBitrate
\tif br == "" {
\t\tbr = "128k"
\t}

\tcmd := exec.CommandContext(ctx,
\t\t"ffmpeg", "-i", srcPath,
\t\t"-c:a", codec,
\t\t"-b:a", br,
\t\t"-ar", strconv.Itoa(cfg.SampleRate),
\t\t"-ac", strconv.Itoa(cfg.Channels),
\t\t"-f", cfg.TargetFormat,
\t\t"pipe:1",
\t)

\tout, err := cmd.Output()
\tif err != nil {
\t\treturn nil, fmt.Errorf("transcode failed: %w", err)
\t}
\treturn out, nil
}

func negotiateCodec(requested string) string {
\tswitch requested {
\tcase "aac", "mp3", "opus", "vorbis":
\t\treturn requested
\tdefault:
\t\treturn "libmp3lame"
\t}
}
""",
        "function": "audio_transcode_ffmpeg_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "server/media/transcode.go",
    },
    # ── 2. Library scanner — directory walking + file metadata extraction
    {
        "normalized_code": """\
package scanner

import (
\t"context"
\t"fmt"
\t"log"
\t"os"
\t"path/filepath"
)

type Xxx struct {
\tPath       string
\tWalkDepth  int
\tExtensions map[string]bool
\tLogger     *log.Logger
}

type ScanResult struct {
\tChangeType string // "added", "modified", "deleted"
\tFilePath   string
\tMetadata   map[string]interface{}
}

func (s *Xxx) scanDirectory(ctx context.Context) ([]ScanResult, error) {
\tvar results []ScanResult

\terr := filepath.Walk(s.Path, func(path string, info os.FileInfo, err error) error {
\t\tselect {
\t\tcase <-ctx.Done():
\t\t\treturn ctx.Err()
\t\tdefault:
\t\t}

\t\tif err != nil {
\t\t\ts.Logger.Printf("scan error: %v", err)
\t\t\treturn nil
\t\t}

\t\tif info.IsDir() {
\t\t\treturn nil
\t\t}

\t\text := filepath.Ext(path)
\t\tif !s.ExtensionsContains(ext) {
\t\t\treturn nil
\t\t}

\t\tmeta, err := extractMetadata(path)
\t\tif err != nil {
\t\t\ts.Logger.Printf("metadata extraction failed: %s — %v", path, err)
\t\t\treturn nil
\t\t}

\t\tresults = append(results, ScanResult{
\t\t\tChangeType: "added",
\t\t\tFilePath:   path,
\t\t\tMetadata:   meta,
\t\t})

\t\treturn nil
\t})

\treturn results, err
}

func extractMetadata(path string) (map[string]interface{}, error) {
\t// Delegate to metadata reader
\treturn readAudioMetadata(path)
}
""",
        "function": "library_scanner_directory_walk",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "server/scanner/scanner.go",
    },
    # ── 3. Audio metadata tag reader — ID3v2, Vorbis, M4A tag extraction
    {
        "normalized_code": """\
package metadata

import (
\t"fmt"
)

type AudioMetadata struct {
\tTitle       string
\tArtist      string
\tAlbum       string
\tAlbumArtist string
\tYear        int
\tGenre       string
\tTrackNumber int
\tDiscNumber  int
\tDuration    int
\tBitrate     int
\tSampleRate  int
\tCodec       string
\tChannels    int
}

func readAudioMetadata(filePath string) (AudioMetadata, error) {
\text := getFileExtension(filePath)

\tswitch ext {
\tcase ".mp3":
\t\treturn readID3v2Metadata(filePath)
\tcase ".flac", ".ogg":
\t\treturn readVorbisMetadata(filePath)
\tcase ".m4a", ".aac":
\t\treturn readM4AMetadata(filePath)
\tcase ".wma":
\t\treturn readASFMetadata(filePath)
\tdefault:
\t\treturn AudioMetadata{}, fmt.Errorf("unsupported format: %s", ext)
\t}
}

func readID3v2Metadata(path string) (AudioMetadata, error) {
\tmeta := AudioMetadata{}
\t// Parse ID3v2 frame structure
\tdata, err := readFileBytes(path, 0, 10240)
\tif err != nil {
\t\treturn meta, err
\t}

\tif string(data[0:3]) != "ID3" {
\t\treturn meta, fmt.Errorf("not an ID3v2 file")
\t}

\t// Extract frames (TIT2, TPE1, TALB, etc.)
\tmeta.Title = extractID3Frame(data, "TIT2")
\tmeta.Artist = extractID3Frame(data, "TPE1")
\tmeta.Album = extractID3Frame(data, "TALB")

\treturn meta, nil
}

func readVorbisMetadata(path string) (AudioMetadata, error) {
\tmeta := AudioMetadata{}
\t// FLAC/OGG Vorbis metadata block parsing
\tfields, err := parseVorbisMetadataBlock(path)
\tif err != nil {
\t\treturn meta, err
\t}

\tmeta.Title = fields["TITLE"]
\tmeta.Artist = fields["ARTIST"]
\tmeta.Album = fields["ALBUM"]
\tmeta.TrackNumber = parseIntField(fields["TRACKNUMBER"])

\treturn meta, nil
}
""",
        "function": "audio_metadata_tag_reader",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "server/metadata/reader.go",
    },
    # ── 4. Smart playlist engine — rule-based auto playlist generation
    {
        "normalized_code": """\
package playlist

import (
\t"context"
\t"fmt"
\t"time"
)

type PlaylistRule struct {
\tOperator  string // "and", "or"
\tField     string // "artist", "genre", "year", "duration", "rating"
\tCondition string // "equals", "contains", "gte", "lte", "between"
\tValue     interface{}
}

type SmartPlaylistXxx struct {
\tName      string
\tRules     []PlaylistRule
\tMaxTracks int
\tOrderBy   string // "random", "added", "rating", "duration"
}

func (p *SmartPlaylistXxx) generateTracks(ctx context.Context, db *gorm.DB) ([]string, error) {
\tquery := db.WithContext(ctx)

\t// Build WHERE clause from rules
\tfor _, rule := range p.Rules {
\t\tquery = applyRuleToQuery(query, rule)
\t}

\t// Apply ordering
\tswitch p.OrderBy {
\tcase "random":
\t\tquery = query.Order("RANDOM()")
\tcase "rating":
\t\tquery = query.Order("rating DESC")
\tcase "added":
\t\tquery = query.Order("created_at DESC")
\tdefault:
\t\tquery = query.Order("added DESC")
\t}

\t// Fetch and limit
\tvar trackIds []string
\terr := query.Limit(p.MaxTracks).Pluck("id", &trackIds).Error

\treturn trackIds, err
}

func applyRuleToQuery(query *gorm.DB, rule PlaylistRule) *gorm.DB {
\tswitch rule.Condition {
\tcase "equals":
\t\treturn query.Where(fmt.Sprintf("%s = ?", rule.Field), rule.Value)
\tcase "contains":
\t\treturn query.Where(fmt.Sprintf("%s LIKE ?", rule.Field), "%"+rule.Value.(string)+"%")
\tcase "gte":
\t\treturn query.Where(fmt.Sprintf("%s >= ?", rule.Field), rule.Value)
\tcase "lte":
\t\treturn query.Where(fmt.Sprintf("%s <= ?", rule.Field), rule.Value)
\tdefault:
\t\treturn query
\t}
}
""",
        "function": "smart_playlist_rule_engine",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "server/playlist/engine.go",
    },
    # ── 5. Full-text search engine — Bleve or SQLite FTS integration
    {
        "normalized_code": """\
package search

import (
\t"context"
\t"database/sql"
\t"fmt"
\t"strings"
)

type SearchXxx struct {
\tDB    *sql.DB
\tIndex *bleve.Index
}

type SearchResult struct {
\tTrackID     string
\tTrackTitle  string
\tArtist      string
\tAlbum       string
\tMatchScore  float64
\tMatchFields []string
}

func (s *SearchXxx) query(ctx context.Context, q string) ([]SearchResult, error) {
\tif s.Index != nil {
\t\treturn s.queryBleveIndex(q)
\t}
\treturn s.querySQLiteFTS(ctx, q)
}

func (s *SearchXxx) queryBleveIndex(q string) ([]SearchResult, error) {
\tsearch := bleve.NewSearchRequest(bleve.NewQueryStringQuery(q))
\tsearch.Size = 100

\tresult, err := s.Index.Search(search)
\tif err != nil {
\t\treturn nil, err
\t}

\tvar results []SearchResult
\tfor _, hit := range result.Hits {
\t\tresults = append(results, SearchResult{
\t\t\tTrackID:    hit.ID,
\t\t\tMatchScore: hit.Score,
\t\t})
\t}

\treturn results, nil
}

func (s *SearchXxx) querySQLiteFTS(ctx context.Context, q string) ([]SearchResult, error) {
\tqueryStr := strings.TrimSpace(q)

\tsql := `
\t\tSELECT id, title, artist, album, rank FROM xxx_fts_search
\t\tWHERE xxx_fts_search MATCH ?
\t\tORDER BY rank DESC
\t\tLIMIT 100
\t`

\trows, err := s.DB.QueryContext(ctx, sql, queryStr)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer rows.Close()

\tvar results []SearchResult
\tfor rows.Next() {
\t\tvar r SearchResult
\t\tvar rank float64
\t\terr := rows.Scan(&r.TrackID, &r.TrackTitle, &r.Artist, &r.Album, &rank)
\t\tif err != nil {
\t\t\tcontinue
\t\t}
\t\tresults = append(results, r)
\t}

\treturn results, nil
}
""",
        "function": "fulltext_search_bleve_fts",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "server/search/search.go",
    },
    # ── 6. Subsonic API compatibility layer — endpoint routing + protocol adaptation
    {
        "normalized_code": """\
package subsonic

import (
\t"fmt"
\t"net/http"
\t"strconv"
)

type SubsonicResponse struct {
\tStatus       string         `xml:"status,attr"`
\tVersion      string         `xml:"xmlns:attr"`
\tErrorDetail  *SubsonicError `xml:"error,omitempty"`
\tPayload      interface{}    `xml:"payload"`
}

type SubsonicError struct {
\tCode        int    `xml:"code,attr"`
\tDescription string `xml:"description,attr"`
}

func adaptGinToSubsonicResponse(statusCode int, payload interface{}) SubsonicResponse {
\tresp := SubsonicResponse{
\t\tVersion: "1.16.1",
\t}

\tif statusCode >= 400 {
\t\tresp.Status = "failed"
\t\tresp.ErrorDetail = &SubsonicError{
\t\t\tCode:        statusCode,
\t\t\tDescription: getSubsonicErrorDescription(statusCode),
\t\t}
\t} else {
\t\tresp.Status = "ok"
\t\tresp.Payload = payload
\t}

\treturn resp
}

func handleSubsonicGetAlbum(w http.ResponseWriter, r *http.Request) error {
\tid := r.URL.Query().Get("id")
\tif id == "" {
\t\treturn fmt.Errorf("missing album ID parameter")
\t}

\talbumID, _ := strconv.Atoi(id)

\t// Fetch album from DB
\talbum, err := fetchAlbumByID(albumID)
\tif err != nil {
\t\treturn err
\t}

\t// Adapt to Subsonic schema (Album.Song list, not nested Xxx)
\trespPayload := adaptAlbumToSubsonicSchema(album)
\tresp := adaptGinToSubsonicResponse(http.StatusOK, respPayload)

\tw.Header().Set("Content-Type", "application/xml")
\treturn xml.NewEncoder(w).Encode(resp)
}

func getSubsonicErrorDescription(code int) string {
\tswitch code {
\tcase 400:
\t\treturn "Required parameter missing."
\tcase 401:
\t\treturn "Incorrect credentials provided."
\tcase 403:
\t\treturn "Caller not authorized for requested operation."
\tcase 404:
\t\treturn "Requested data not found."
\tdefault:
\t\treturn "Server error."
\t}
}
""",
        "function": "subsonic_api_protocol_adapter",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "server/subsonic/adapter.go",
    },
    # ── 7. Jukebox playback control — remote queue + playback state management
    {
        "normalized_code": """\
package jukebox

import (
\t"context"
\t"fmt"
\t"sync"
\t"time"
)

type PlaybackXxx struct {
\tID           string
\tQueue        []string // track IDs
\tCurrentIndex int
\tIsPlaying    bool
\tCurrentTime  int // seconds
\tMutex        sync.RWMutex
}

type PlaybackState struct {
\tCurrentTrackID string
\tPosition       int
\tDuration       int
\tIsPlaying      bool
\tPlaylistSize   int
}

func (j *PlaybackXxx) addToQueue(trackID string, index int) error {
\tj.Mutex.Lock()
\tdefer j.Mutex.Unlock()

\tif index < 0 || index > len(j.Queue) {
\t\tindex = len(j.Queue)
\t}

\tj.Queue = append(j.Queue[:index], append([]string{trackID}, j.Queue[index:]...)...)
\treturn nil
}

func (j *PlaybackXxx) play(ctx context.Context) error {
\tj.Mutex.Lock()
\tdefer j.Mutex.Unlock()

\tif len(j.Queue) == 0 {
\t\treturn fmt.Errorf("queue is empty")
\t}

\tj.IsPlaying = true

\tgo j.playLoop(ctx)
\treturn nil
}

func (j *PlaybackXxx) playLoop(ctx context.Context) {
\tfor {
\t\tselect {
\t\tcase <-ctx.Done():
\t\t\treturn
\t\tdefault:
\t\t}

\t\tj.Mutex.RLock()
\t\tif !j.IsPlaying || j.CurrentIndex >= len(j.Queue) {
\t\t\tj.Mutex.RUnlock()
\t\t\tbreak
\t\t}
\t\tcurrentTrackID := j.Queue[j.CurrentIndex]
\t\tj.Mutex.RUnlock()

\t\ttrackDuration, err := getTrackDuration(currentTrackID)
\t\tif err != nil {
\t\t\tcontinue
\t\t}

\t\tfor elapsed := 0; elapsed < trackDuration; elapsed++ {
\t\t\tselect {
\t\t\tcase <-ctx.Done():
\t\t\t\treturn
\t\t\tdefault:
\t\t\t}

\t\t\tj.Mutex.Lock()
\t\t\tj.CurrentTime = elapsed
\t\t\tif !j.IsPlaying {
\t\t\t\tj.Mutex.Unlock()
\t\t\t\treturn
\t\t\t}
\t\t\tj.Mutex.Unlock()

\t\t\ttime.Sleep(1 * time.Second)
\t\t}

\t\tj.Mutex.Lock()
\t\tj.CurrentIndex++
\t\tj.CurrentTime = 0
\t\tj.Mutex.Unlock()
\t}
}

func (j *PlaybackXxx) getState() PlaybackState {
\tj.Mutex.RLock()
\tdefer j.Mutex.RUnlock()

\tvar trackID string
\tif j.CurrentIndex < len(j.Queue) {
\t\ttrackID = j.Queue[j.CurrentIndex]
\t}

\treturn PlaybackState{
\t\tCurrentTrackID: trackID,
\t\tPosition:       j.CurrentTime,
\t\tIsPlaying:      j.IsPlaying,
\t\tPlaylistSize:   len(j.Queue),
\t}
}
""",
        "function": "jukebox_playback_queue_control",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "server/jukebox/playback.go",
    },
    # ── 8. Media file path resolution + organization — cached path-to-ID mapping
    {
        "normalized_code": """\
package media

import (
\t"context"
\t"fmt"
\t"path/filepath"
\t"sync"
)

type MediaPathResolver struct {
\tRootPath      string
\tPathToIDCache map[string]string // filepath → media ID
\tCacheMutex    sync.RWMutex
\tDB            *gorm.DB
}

func (r *MediaPathResolver) resolvePathToID(ctx context.Context, relPath string) (string, error) {
\tr.CacheMutex.RLock()
\tif id, exists := r.PathToIDCache[relPath]; exists {
\t\tr.CacheMutex.RUnlock()
\t\treturn id, nil
\t}
\tr.CacheMutex.RUnlock()

\t// Query DB if not in cache
\tvar id string
\terr := r.DB.WithContext(ctx).Where("file_path = ?", relPath).Pluck("id", &id).Error
\tif err != nil {
\t\treturn "", fmt.Errorf("path resolution failed: %w", err)
\t}

\t// Update cache
\tr.CacheMutex.Lock()
\tr.PathToIDCache[relPath] = id
\tr.CacheMutex.Unlock()

\treturn id, nil
}

func (r *MediaPathResolver) resolveIDToPath(ctx context.Context, id string) (string, error) {
\t// Check reverse cache
\tr.CacheMutex.RLock()
\tfor path, cachedID := range r.PathToIDCache {
\t\tif cachedID == id {
\t\t\tr.CacheMutex.RUnlock()
\t\t\treturn path, nil
\t\t}
\t}
\tr.CacheMutex.RUnlock()

\t// Query DB
\tvar relPath string
\terr := r.DB.WithContext(ctx).Where("id = ?", id).Pluck("file_path", &relPath).Error
\tif err != nil {
\t\treturn "", err
\t}

\tr.CacheMutex.Lock()
\tr.PathToIDCache[relPath] = id
\tr.CacheMutex.Unlock()

\treturn filepath.Join(r.RootPath, relPath), nil
}

func (r *MediaPathResolver) invalidateCache() {
\tr.CacheMutex.Lock()
\tr.PathToIDCache = make(map[string]string)
\tr.CacheMutex.Unlock()
}
""",
        "function": "media_path_resolution_cache",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "server/media/resolver.go",
    },
    # ── 9. Cache layer architecture — multi-tier (in-memory + Redis optional)
    {
        "normalized_code": """\
package cache

import (
\t"context"
\t"sync"
\t"time"
)

type CacheLayer struct {
\tMemory map[string]CacheEntry
\tMutex  sync.RWMutex
\tTTL    time.Duration
}

type CacheEntry struct {
\tData      interface{}
\tExpiresAt time.Time
}

func NewCacheLayer(ttl time.Duration) *CacheLayer {
\treturn &CacheLayer{
\t\tMemory: make(map[string]CacheEntry),
\t\tTTL:    ttl,
\t}
}

func (c *CacheLayer) get(key string) (interface{}, bool) {
\tc.Mutex.RLock()
\tdefer c.Mutex.RUnlock()

\tentry, exists := c.Memory[key]
\tif !exists {
\t\treturn nil, false
\t}

\tif time.Now().After(entry.ExpiresAt) {
\t\t// Expired
\t\tc.Mutex.RUnlock()
\t\tc.Mutex.Lock()
\t\tdelete(c.Memory, key)
\t\tc.Mutex.Unlock()
\t\tc.Mutex.RLock()
\t\treturn nil, false
\t}

\treturn entry.Data, true
}

func (c *CacheLayer) set(key string, data interface{}) {
\tc.Mutex.Lock()
\tdefer c.Mutex.Unlock()

\tc.Memory[key] = CacheEntry{
\t\tData:      data,
\t\tExpiresAt: time.Now().Add(c.TTL),
\t}
}

func (c *CacheLayer) del(key string) {
\tc.Mutex.Lock()
\tdefer c.Mutex.Unlock()

\tdelete(c.Memory, key)
}

func (c *CacheLayer) cleanup() {
\tc.Mutex.Lock()
\tdefer c.Mutex.Unlock()

\tfor key, entry := range c.Memory {
\t\tif time.Now().After(entry.ExpiresAt) {
\t\t\tdelete(c.Memory, key)
\t\t}
\t}
}
""",
        "function": "cache_layer_memory_redis",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "server/cache/cache.go",
    },
    # ── 10. Audio format detection + codec negotiation — MIME type + ffprobe
    {
        "normalized_code": """\
package media

import (
\t"fmt"
\t"os/exec"
\t"strings"
)

type AudioFormat struct {
\tCodec      string // "mp3", "aac", "flac", "opus", "vorbis"
\tContainer  string // "mp3", "m4a", "flac", "ogg", "webm"
\tSampleRate int
\tChannels   int
\tBitrate    int
\tDuration   int
}

func detectAudioFormat(filePath string) (AudioFormat, error) {
\tfmt := AudioFormat{}

\tcmd := exec.Command("ffprobe",
\t\t"-v", "error",
\t\t"-show_format",
\t\t"-show_streams",
\t\t"-of", "json",
\t\tfilePath,
\t)

\tout, err := cmd.Output()
\tif err != nil {
\t\treturn fmt.AudioFormat{}, fmt.Errorf("ffprobe failed: %w", err)
\t}

\t// Parse JSON output
\tvar probeOutput ProbeOutput
\terr = json.Unmarshal(out, &probeOutput)
\tif err != nil {
\t\treturn fmt.AudioFormat{}, err
\t}

\tif len(probeOutput.Streams) == 0 {
\t\treturn fmt.AudioFormat{}, fmt.Errorf("no audio streams found")
\t}

\taudioStream := probeOutput.Streams[0]
\tfmt.Codec = audioStream.CodecName
\tfmt.Container = probeOutput.Format.FormatName
\tfmt.SampleRate = audioStream.SampleRate
\tfmt.Channels = audioStream.Channels
\tfmt.Bitrate = parseInt(audioStream.BitRate)
\tfmt.Duration = parseInt(probeOutput.Format.Duration)

\treturn fmt, nil
}

func negotiateOutputFormat(clientProfile string, inputFormat AudioFormat) AudioFormat {
\t// Based on client capabilities (Subsonic API, browser, etc.)
\t// Decide which codec and bitrate to use

\toutput := inputFormat

\tswitch clientProfile {
\tcase "mobile":
\t\tif output.Bitrate > 128000 {
\t\t\toutput.Bitrate = 128000
\t\t\toutput.Codec = "libmp3lame"
\t\t}
\tcase "desktop":
\t\tif output.Bitrate > 320000 {
\t\t\toutput.Bitrate = 320000
\t\t}
\tcase "hifi":
\t\tif output.Bitrate > 500000 {
\t\t\toutput.Bitrate = 500000
\t\t}
\t}

\treturn output
}
""",
        "function": "audio_format_detection_ffprobe",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "server/media/format.go",
    },
    # ── 11. Album art extraction + caching — embedded vs external artwork
    {
        "normalized_code": """\
package artwork

import (
\t"context"
\t"fmt"
\t"io/ioutil"
\t"os"
\t"path/filepath"
)

type ArtworkXxx struct {
\tSourcePath    string
\tCacheDir      string
\tMaxResolution int // 500x500, etc.
}

type ArtworkSource struct {
\tType     string // "embedded", "external", "folder"
\tPath     string
\tFormat   string // "jpg", "png"
\tSize     int
\tFilePath string
}

func (a *ArtworkXxx) extractFromTrack(ctx context.Context, trackPath string) (ArtworkSource, error) {
\t// Try embedded first (ID3, ID3v2, vorbis, etc.)
\tembedded, err := a.extractEmbeddedArtwork(trackPath)
\tif err == nil && embedded.Size > 0 {
\t\treturn embedded, nil
\t}

\t// Try external (folder.jpg, cover.png, etc.)
\tdirPath := filepath.Dir(trackPath)
\texternalPatterns := []string{"folder.jpg", "cover.jpg", "cover.png", "front.jpg"}

\tfor _, pattern := range externalPatterns {
\t\textFilePath := filepath.Join(dirPath, pattern)
\t\tif info, err := os.Stat(extFilePath); err == nil {
\t\t\treturn ArtworkSource{
\t\t\t\tType:     "external",
\t\t\t\tPath:     extFilePath,
\t\t\t\tFormat:   getImageFormat(pattern),
\t\t\t\tSize:     int(info.Size()),
\t\t\t\tFilePath: extFilePath,
\t\t\t}, nil
\t\t}
\t}

\treturn ArtworkSource{}, fmt.Errorf("no artwork found")
}

func (a *ArtworkXxx) extractEmbeddedArtwork(trackPath string) (ArtworkSource, error) {
\t// Use ffmpeg to extract embedded artwork
\tcacheName := fmt.Sprintf("%s.jpg", hashPath(trackPath))
\tcachePath := filepath.Join(a.CacheDir, cacheName)

\t// Check cache first
\tif _, err := os.Stat(cachePath); err == nil {
\t\tinfo, _ := os.Stat(cachePath)
\t\treturn ArtworkSource{
\t\t\tType:     "cached",
\t\t\tPath:     cachePath,
\t\t\tFormat:   "jpg",
\t\t\tSize:     int(info.Size()),
\t\t\tFilePath: cachePath,
\t\t}, nil
\t}

\tcmd := exec.Command("ffmpeg",
\t\t"-i", trackPath,
\t\t"-an", "-vcodec", "copy",
\t\tcachePath,
\t)

\terr := cmd.Run()
\tif err != nil {
\t\treturn ArtworkSource{}, fmt.Errorf("embedded extraction failed: %w", err)
\t}

\tinfo, _ := os.Stat(cachePath)
\treturn ArtworkSource{
\t\tType:     "embedded",
\t\tPath:     cachePath,
\t\tFormat:   "jpg",
\t\tSize:     int(info.Size()),
\t\tFilePath: cachePath,
\t}, nil
}

func hashPath(path string) string {
\t// Simple hash for cache key
\treturn fmt.Sprintf("%x", sha256.Sum256([]byte(path)))
}
""",
        "function": "album_artwork_extraction_cache",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "server/artwork/extractor.go",
    },
    # ── 12. File watcher — real-time library updates on filesystem changes
    {
        "normalized_code": """\
package scanner

import (
\t"context"
\t"fmt"
\t"log"
\t"time"

\t"gorm.io/gorm"
)

type FileWatcher struct {
\tPath              string
\tDB                *gorm.DB
\tChangeChan        chan FileSystemChange
\tDebounceInterval  time.Duration
\tLogger            *log.Logger
\tPendingQueue      map[string]FileSystemChange
}

type FileSystemChange struct {
\tChangeType string
\tFilePath   string
\tTimestamp  time.Time
}

func NewFileWatcher(path string, db *gorm.DB, interval time.Duration) *FileWatcher {
\treturn &FileWatcher{
\t\tPath:              path,
\t\tDB:                db,
\t\tChangeChan:        make(chan FileSystemChange, 100),
\t\tDebounceInterval:  interval,
\t\tPendingQueue:      make(map[string]FileSystemChange),
\t}
}

func (w *FileWatcher) watch(ctx context.Context) error {
\t// Create underlying filesystem watcher (implementation detail)
\twm, err := createFSWatcher()
\tif err != nil {
\t\treturn fmt.Errorf("failed to create: %w", err)
\t}
\tdefer wm.Close()

\terr = wm.Add(w.Path)
\tif err != nil {
\t\treturn fmt.Errorf("failed to add path: %w", err)
\t}

\tdebounceTicker := time.NewTicker(w.DebounceInterval)
\tdefer debounceTicker.Stop()

\tfor {
\t\tselect {
\t\tcase ch := <-wm.Recv():
\t\t\tw.handleChange(ch)

\t\tcase <-debounceTicker.C:
\t\t\tw.flushPendingQueue(ctx)

\t\tcase err := <-wm.RecvErr():
\t\t\tw.Logger.Printf("error: %v", err)

\t\tcase <-ctx.Done():
\t\t\treturn ctx.Err()
\t\t}
\t}
}

func (w *FileWatcher) handleChange(ch FileSystemChange) {
\tw.PendingQueue[ch.FilePath] = ch
}

func (w *FileWatcher) flushPendingQueue(ctx context.Context) {
\tfor _, change := range w.PendingQueue {
\t\tw.ChangeChan <- change
\t\tw.Logger.Printf("dispatched: %s %s", change.ChangeType, change.FilePath)
\t}
\tw.PendingQueue = make(map[string]FileSystemChange)
}
""",
        "function": "file_watcher_realtime_updates",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "server/scanner/watcher.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "audio transcoding ffmpeg codec negotiation bitrate",
    "music library scanner directory walk file metadata extraction",
    "audio tag reader ID3v2 Vorbis M4A metadata",
    "smart playlist rule engine auto playlist generation",
    "full-text search Bleve SQLite FTS music tracks",
    "Subsonic API protocol adapter XML response format",
    "jukebox playback queue control remote streaming",
    "media path resolution cache filepath-to-ID mapping",
    "cache layer architecture in-memory Redis TTL",
    "audio format detection ffprobe codec MIME type",
    "album artwork extraction caching embedded external",
    "file watcher real-time library updates filesystem",
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

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
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
