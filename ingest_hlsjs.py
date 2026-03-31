"""
ingest_hlsjs.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de video-dev/hls.js dans la KB Qdrant V6.

Focus : CORE patterns HLS streaming (ABR, buffer management, manifest parsing,
segment loading, MSE control, transmuxing). PAS des patterns CRUD/API.

Usage:
    .venv/bin/python3 ingest_hlsjs.py
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
REPO_URL = "https://github.com/video-dev/hls.js.git"
REPO_NAME = "video-dev/hls.js"
REPO_LOCAL = "/tmp/hls.js"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+mse+hls"
CHARTE_VERSION = "1.0"
TAG = "video-dev/hls.js"
SOURCE_REPO = "https://github.com/video-dev/hls.js"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# HLS.js = adaptive bitrate video streaming player using Media Source Extensions.
# Patterns CORE : ABR algorithms, buffer control, manifest parsing, segment loading.
# U-5: Pas de noms métier typiques — entités sont des concepts streaming.

PATTERNS: list[dict] = [
    # ── 1. EWMA Bandwidth Estimator (dual half-life + TTFB) ───────────────────
    {
        "normalized_code": """\
class EwmaBandwidthEstimator {
  private defaultEstimate_: number;
  private minWeight_: number;
  private minDelayMs_: number;
  private slow_: Ewma;
  private fast_: Ewma;
  private ttfb_: Ewma;

  constructor(
    slow: number,
    fast: number,
    defaultEstimate: number,
    defaultTTFB: number = 100,
  ) {
    this.defaultEstimate_ = defaultEstimate;
    this.minWeight_ = 0.001;
    this.minDelayMs_ = 50;
    this.slow_ = new Ewma(slow);
    this.fast_ = new Ewma(fast);
    this.ttfb_ = new Ewma(slow);
  }

  sample(durationMs: number, numBytes: number) {
    durationMs = Math.max(durationMs, this.minDelayMs_);
    const numBits = 8 * numBytes;
    const durationS = durationMs / 1000;
    const bandwidthInBps = numBits / durationS;
    this.fast_.sample(durationS, bandwidthInBps);
    this.slow_.sample(durationS, bandwidthInBps);
  }

  sampleTTFB(ttfb: number) {
    const seconds = ttfb / 1000;
    const weight = Math.sqrt(2) * Math.exp(-Math.pow(seconds, 2) / 2);
    this.ttfb_.sample(weight, Math.max(ttfb, 5));
  }

  getEstimate(): number {
    if (this.canEstimate()) {
      return Math.min(this.fast_.getEstimate(), this.slow_.getEstimate());
    }
    return this.defaultEstimate_;
  }
}
""",
        "function": "bandwidth_estimation_ewma_dual_halflife",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/utils/ewma-bandwidth-estimator.ts",
    },
    # ── 2. Buffer Helper — time range queries ─────────────────────────────────
    {
        "normalized_code": """\
export type BufferTimeRange = {
  start: number;
  end: number;
};

export class BufferHelper {
  static isBuffered(media: Bufferable | null, position: number): boolean {
    if (media) {
      const buffered = BufferHelper.getBuffered(media);
      for (let i = buffered.length; i--; ) {
        if (position >= buffered.start(i) && position <= buffered.end(i)) {
          return true;
        }
      }
    }
    return false;
  }

  static bufferedRanges(media: Bufferable | null): BufferTimeRange[] {
    if (media) {
      const timeRanges = BufferHelper.getBuffered(media);
      return BufferHelper.timeRangesToArray(timeRanges);
    }
    return [];
  }

  static timeRangesToArray(timeRanges: TimeRanges): BufferTimeRange[] {
    const buffered: BufferTimeRange[] = [];
    for (let i = 0; i < timeRanges.length; i++) {
      buffered.push({ start: timeRanges.start(i), end: timeRanges.end(i) });
    }
    return buffered;
  }

  static bufferInfo(
    media: Bufferable | null,
    pos: number,
    maxHoleDuration: number,
  ): BufferInfo {
    if (media) {
      const buffered = BufferHelper.bufferedRanges(media);
      if (buffered.length) {
        return BufferHelper.bufferedInfo(buffered, pos, maxHoleDuration);
      }
    }
    return { len: 0, start: pos, end: pos, bufferedIndex: -1 };
  }
}
""",
        "function": "buffer_helper_range_queries",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/utils/buffer-helper.ts",
    },
    # ── 3. M3U8 Master Playlist Parser (multivariant + media groups) ──────────
    {
        "normalized_code": """\
export type ParsedMultivariantPlaylist = {
  contentSteering: ContentSteeringOptions | null;
  xxx: ParsedPlaylist[];
  playlistParsingError: Error | null;
  sessionData: Record<string, AttrList> | null;
  sessionKeys: LevelKey[] | null;
  startTimeOffset: number | null;
  variableList: VariableMap | null;
  hasVariableRefs: boolean;
};

export default class M3U8Parser {
  static isMediaPlaylist(str: string): boolean {
    return IS_MEDIA_PLAYLIST.test(str);
  }

  static parseMasterPlaylist(
    string: string,
    baseurl: string,
  ): ParsedMultivariantPlaylist {
    const hasVariableRefs = hasVariableReferences(string);
    const parsed: ParsedMultivariantPlaylist = {
      contentSteering: null,
      xxx: [],
      playlistParsingError: null,
      sessionData: null,
      sessionKeys: null,
      startTimeOffset: null,
      variableList: null,
      hasVariableRefs,
    };
    const xxxWithKnownCodecs: ParsedPlaylist[] = [];
    const MASTER_PLAYLIST_REGEX =
      /#EXT-X-STREAM-INF:([^\\r\\n]*)(?:[\\r\\n](?:#[^\\r\\n]*)?)*([^\\r\\n]+)|#EXT-X-(SESSION-DATA|SESSION-KEY|DEFINE|CONTENT-STEERING|START):([^\\r\\n]*)[\r\n]+/g;
    let match;
    while ((match = MASTER_PLAYLIST_REGEX.exec(string)) !== null) {
      if (match[2]) {
        const xxx = M3U8Parser.parseStreamInf(match[1], match[2]);
        xxxWithKnownCodecs.push(xxx);
      } else if (match[3] === "SESSION-KEY") {
        const levelKey = LevelKey.fromString(match[4]);
        if (levelKey && !parsed.sessionKeys) {
          parsed.sessionKeys = [levelKey];
        }
      }
    }
    parsed.xxx = xxxWithKnownCodecs;
    return parsed;
  }
}
""",
        "function": "m3u8_master_playlist_parser",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "src/loader/m3u8-parser.ts",
    },
    # ── 4. Fragment Segment Definition (byte range + timing) ──────────────────
    {
        "normalized_code": """\
export class BaseSegment {
  private _byteRange: [number, number] | null = null;
  private _url: string | null = null;
  private _stats: LoadStats | null = null;
  private _streams: ElementaryStreams | null = null;

  public readonly base: Base;
  public relurl?: string;

  constructor(base: Base | string) {
    if (typeof base === "string") {
      base = { url: base };
    }
    this.base = base;
  }

  setByteRange(value: string, previous?: BaseSegment) {
    const params = value.split("@", 2);
    let start: number;
    if (params.length === 1) {
      start = previous?.byteRangeEndOffset || 0;
    } else {
      start = parseInt(params[1]);
    }
    this._byteRange = [start, parseInt(params[0]) + start];
  }

  get baseurl(): string {
    return this.base.url;
  }

  get byteRange(): [number, number] | [] {
    if (this._byteRange === null) {
      return [];
    }
    return this._byteRange;
  }

  get byteRangeStartOffset(): number | undefined {
    return this._byteRange?.[0];
  }

  get byteRangeEndOffset(): number | undefined {
    return this._byteRange?.[1];
  }
}
""",
        "function": "fragment_segment_definition_byterange",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/loader/fragment.ts",
    },
    # ── 5. Level Controller (quality selection + switching) ──────────────────
    {
        "normalized_code": """\
export default class LevelController extends BasePlaylistController {
  private _xxx: Xxx[] = [];
  private _firstXxx: number = -1;
  private _maxAutoXxx: number = -1;
  private _startXxx?: number;
  private currentXxx: Xxx | null = null;
  private currentXxxIndex: number = -1;
  private manualXxxIndex: number = -1;
  private steering: ContentSteeringController | null;
  private lastABRSwitchTime: number = -1;

  constructor(
    hls: Hls,
    contentSteeringController: ContentSteeringController | null,
  ) {
    super(hls, "level-controller");
    this.steering = contentSteeringController;
    this._registerListeners();
  }

  private _registerListeners() {
    const { hls } = this;
    hls.on(Notification.MANIFEST_LOADING, this.onManifestLoading, this);
    hls.on(Notification.MANIFEST_LOADED, this.onManifestLoaded, this);
    hls.on(Notification.XXX_LOADED, this.onXxxLoaded, this);
    hls.on(Notification.FRAG_BUFFERED, this.onFragBuffered, this);
    hls.on(Notification.ERROR, this.onError, this);
  }

  private _unregisterListeners() {
    const { hls } = this;
    hls.off(Notification.MANIFEST_LOADING, this.onManifestLoading, this);
    hls.off(Notification.MANIFEST_LOADED, this.onManifestLoaded, this);
    hls.off(Notification.XXX_LOADED, this.onXxxLoaded, this);
    hls.off(Notification.FRAG_BUFFERED, this.onFragBuffered, this);
    hls.off(Notification.ERROR, this.onError, this);
  }

  public destroy() {
    this._unregisterListeners();
    this.steering = null;
    this.resetXxxs();
    super.destroy();
  }

  get xxx(): Xxx[] {
    return this._xxx;
  }

  get xxxIndex(): number {
    return this.currentXxxIndex;
  }

  set xxxIndex(index: number) {
    if (index !== this.currentXxxIndex) {
      this.currentXxxIndex = index;
      this.lastABRSwitchTime = performance.now();
    }
  }
}
""",
        "function": "quality_level_controller_switching",
        "feature_type": "controller",
        "file_role": "utility",
        "file_path": "src/controller/level-controller.ts",
    },
    # ── 6. Latency Controller (live edge + target latency) ────────────────────
    {
        "normalized_code": """\
export default class LatencyController implements ComponentAPI {
  private hls: Hls | null;
  private readonly config: HlsConfig;
  private media: HTMLMediaElement | null = null;
  private currentTime: number = 0;
  private stallCount: number = 0;
  private _latency: number | null = null;
  private _targetLatencyUpdated = false;

  constructor(hls: Hls) {
    this.hls = hls;
    this.config = hls.config;
    this.registerListeners();
  }

  get latency(): number {
    return this._latency || 0;
  }

  get maxLatency(): number {
    const { config } = this;
    if (config.liveMaxLatencyDuration !== undefined) {
      return config.liveMaxLatencyDuration;
    }
    const levelDetails = this.levelDetails;
    return levelDetails
      ? config.liveMaxLatencyDurationCount * levelDetails.targetduration
      : 0;
  }

  get targetLatency(): number | null {
    const levelDetails = this.levelDetails;
    if (levelDetails === null || this.hls === null) {
      return null;
    }
    const { holdBack, partHoldBack, targetduration } = levelDetails;
    const { liveSyncDuration, liveSyncDurationCount, lowLatencyMode } =
      this.config;
    let targetLatency = lowLatencyMode ? partHoldBack || holdBack : holdBack;
    if (
      this._targetLatencyUpdated ||
      userConfig.liveSyncDuration ||
      userConfig.liveSyncDurationCount ||
      targetLatency === 0
    ) {
      targetLatency =
        liveSyncDuration !== undefined
          ? liveSyncDuration
          : liveSyncDurationCount * targetduration;
    }
    const maxLiveSyncOnStallIncrease = targetduration;
    return (
      targetLatency +
      Math.min(
        this.stallCount * this.config.liveSyncOnStallIncrease,
        maxLiveSyncOnStallIncrease,
      )
    );
  }

  set targetLatency(latency: number) {
    this.stallCount = 0;
    this.config.liveSyncDuration = latency;
  }
}
""",
        "function": "latency_controller_live_edge",
        "feature_type": "controller",
        "file_role": "utility",
        "file_path": "src/controller/latency-controller.ts",
    },
    # ── 7. Transmuxer — demuxer + remuxer selector ────────────────────────────
    {
        "normalized_code": """\
type MuxConfig =
  | { demux: typeof MP4Demuxer; remux: typeof PassThroughRemuxer }
  | { demux: typeof TSDemuxer; remux: typeof MP4Remuxer }
  | { demux: typeof AC3Demuxer; remux: typeof MP4Remuxer }
  | { demux: typeof AACDemuxer; remux: typeof MP4Remuxer }
  | { demux: typeof MP3Demuxer; remux: typeof MP4Remuxer };

const muxConfig: MuxConfig[] = [
  { demux: MP4Demuxer, remux: PassThroughRemuxer },
  { demux: TSDemuxer, remux: MP4Remuxer },
  { demux: AACDemuxer, remux: MP4Remuxer },
  { demux: MP3Demuxer, remux: MP4Remuxer },
];

export default class Transmuxer {
  private asyncResult: boolean = false;
  private logger: ILogger;
  private observer: HlsEventEmitter;
  private typeSupported: TypeSupported;
  private config: HlsConfig;
  private id: PlaylistLevelType;
  private demuxer?: Demuxer;
  private remuxer?: Remuxer;
  private decrypter?: Decrypter;
  private probe!: Function;
  private decryptionPromise: Promise<TransmuxerResult> | null = null;
  private transmuxConfig!: TransmuxConfig;
  private currentTransmuxState!: TransmuxState;

  constructor(
    observer: HlsEventEmitter,
    typeSupported: TypeSupported,
    config: HlsConfig,
    vendor: string,
    id: PlaylistLevelType,
    logger: ILogger,
  ) {
    this.observer = observer;
    this.typeSupported = typeSupported;
    this.config = config;
    this.id = id;
    this.logger = logger;
  }
}
""",
        "function": "transmuxer_demux_remux_adapter",
        "feature_type": "controller",
        "file_role": "utility",
        "file_path": "src/demux/transmuxer.ts",
    },
    # ── 8. Base Stream Controller (fragment state machine) ────────────────────
    {
        "normalized_code": """\
export const State = {
  STOPPED: "STOPPED",
  IDLE: "IDLE",
  KEY_LOADING: "KEY_LOADING",
  FRAG_LOADING: "FRAG_LOADING",
  FRAG_LOADING_WAITING_RETRY: "FRAG_LOADING_WAITING_RETRY",
  WAITING_TRACK: "WAITING_TRACK",
  PARSING: "PARSING",
  PARSED: "PARSED",
  ENDED: "ENDED",
  ERROR: "ERROR",
  WAITING_INIT_PTS: "WAITING_INIT_PTS",
  WAITING_XXX: "WAITING_XXX",
};

export type InFlightData = {
  frag: Fragment | null;
  state: (typeof State)[keyof typeof State];
};

export default class BaseStreamController
  extends TaskLoop
  implements NetworkComponentAPI
{
  private hls: Hls;
  private fragmentTracker: FragmentTracker;
  private details: LevelDetails | null = null;
  private media: HTMLMediaElement | null = null;

  constructor(hls: Hls, logger: ILogger) {
    super(logger);
    this.hls = hls;
    this.fragmentTracker = new FragmentTracker();
    this._registerListeners();
  }

  private _registerListeners() {
    const { hls } = this;
    hls.on(Events.FRAG_LOADED, this.onFragLoaded, this);
    hls.on(Events.ERROR, this.onError, this);
  }

  protected onFragLoaded(data: FragLoadedData) {
    const { frag } = data;
    if (frag.sn === -1) {
      this.state = State.PARSED;
    }
  }

  protected onError(data: ErrorData) {
    if (data.type === ErrorTypes.NETWORK_ERROR) {
      this.state = State.FRAG_LOADING_WAITING_RETRY;
    }
  }
}
""",
        "function": "fragment_loading_state_machine",
        "feature_type": "controller",
        "file_role": "utility",
        "file_path": "src/controller/base-stream-controller.ts",
    },
    # ── 9. Buffer Controller — MSE appendBuffer + flush ───────────────────────
    {
        "normalized_code": """\
interface BufferedChangeSignal extends Signal {
  readonly addedRanges?: TimeRanges;
  readonly removedRanges?: TimeRanges;
}

const VIDEO_CODEC_PROFILE_REPLACE =
  /(avc[1234]|hvc1|hev1|dvh[1e]|vp09|av01)(?:\\.[^.,]+)+/;

export default class BufferController extends Logger implements ComponentAPI {
  private hls: Hls;
  private fragmentTracker: FragmentTracker;
  private details: LevelDetails | null = null;
  private _objectUrl: string | null = null;
  private operationQueue: BufferOperationQueue | null = null;

  private bufferCodecSignalsTotal: number = 0;
  private media: HTMLMediaElement | null = null;
  private mediaSource: MediaSource | null = null;

  constructor(hls: Hls) {
    super("buffer-controller");
    this.hls = hls;
    this._registerListeners();
  }

  private _registerListeners() {
    const { hls } = this;
    hls.on(Events.MANIFEST_PARSED, this.onManifestParsed, this);
    hls.on(Events.MEDIA_ATTACHED, this.onMediaAttached, this);
    hls.on(Events.BUFFER_APPENDING, this.onBufferAppending, this);
  }

  private onBufferAppending(data: BufferAppendingData) {
    if (!this.operationQueue) {
      this.operationQueue = new BufferOperationQueue(this.mediaSource);
    }
    this.operationQueue.appendBuffer(
      data.data,
      data.type,
    );
  }
}
""",
        "function": "buffer_controller_mse_append",
        "feature_type": "controller",
        "file_role": "utility",
        "file_path": "src/controller/buffer-controller.ts",
    },
    # ── 10. Fragment Loader with retry + backoff ────────────────────────────
    {
        "normalized_code": """\
export interface Xxx {
  readonly context: XxxLoaderContext;
  abort(): void;
  destroy(): void;
  load(): void;
  retry(): void;
}

export interface XxxLoaderContext {
  url: string;
  timeout: number;
  maxRetry: number;
  retryDelayMs: number;
  maxRetryDelayMs: number;
  highWaterMark: number;
}

export type LoadError = {
  code: number;
  text: string;
  context: XxxLoaderContext;
};

export default class XxxLoader {
  private context: XxxLoaderContext;
  private retryCount: number = 0;
  private retryDelay: number;
  private timeout: number | null = null;

  constructor(context: XxxLoaderContext) {
    this.context = context;
    this.retryDelay = context.retryDelayMs;
  }

  load(): void {
    const url = this.context.url;
    const timeout = this.context.timeout;

    const xhr = new XMLHttpRequest();
    xhr.timeout = timeout;

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        this.onSuccess(xhr);
      } else if (xhr.status === 0) {
        // network error
      } else {
        this.onError(xhr.status);
      }
    };

    xhr.onerror = () => this.onError(xhr.status);
    xhr.ontimeout = () => this.onError(0);
    xhr.open("GET", url, true);
    xhr.send();
  }

  retry(): void {
    if (this.retryCount < this.context.maxRetry) {
      this.retryCount += 1;
      const backoff = Math.min(
        this.retryDelay * Math.pow(2, this.retryCount - 1),
        this.context.maxRetryDelayMs,
      );
      setTimeout(() => this.load(), backoff);
    }
  }

  private onError(code: number) {
    if (this.context.maxRetry > 0) {
      this.retry();
    }
  }
}
""",
        "function": "fragment_loader_retry_backoff",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/loader/fragment-loader.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "exponential weighted moving average bandwidth estimation ABR",
    "buffer helper media element time ranges",
    "HLS M3U8 master playlist parser multivariant",
    "fragment segment byte range definition",
    "level controller quality switching adaptive bitrate",
    "latency controller live edge target latency",
    "transmuxer demux remux format conversion",
    "fragment loader retry backoff network",
    "media source extensions buffer append flush",
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
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
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
