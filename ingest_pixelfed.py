"""
ingest_pixelfed.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de pixelfed/pixelfed dans la KB Qdrant V6.

Focus : CORE Instagram features (image pipeline, feeds, stories, federation, moderation).
PAS des patterns Laravel CRUD génériques — patterns d'architecture Pixelfed spécifiques.

Usage:
    .venv/bin/python3 ingest_pixelfed.py
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
REPO_URL = "https://github.com/pixelfed/pixelfed.git"
REPO_NAME = "pixelfed/pixelfed"
REPO_LOCAL = "/tmp/pixelfed"
LANGUAGE = "php"
FRAMEWORK = "laravel"
STACK = "laravel+intervention_image+activitypub"
CHARTE_VERSION = "1.0"
TAG = "pixelfed/pixelfed"
SOURCE_REPO = "https://github.com/pixelfed/pixelfed"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Pixelfed = distributed Instagram alternative with federation, image processing, stories.
# Patterns CORE : image optimization pipeline, ActivityPub federation, ephemeral content (stories),
# feed/timeline ranking, media handling, content moderation.
#
# U-5 CRITICAL for social app:
# FORBIDDEN: user → xxx, post → xxx_entry, comment → xxx_reply, message → xxx_dm,
#            tag → label/hashtag_label, event → signal
# TECHNICAL TERMS (safe): media, image, thumbnail, filter, pipeline, storage, cdn,
#            federation, activitypub, inbox, outbox, webfinger, json_ld, collection,
#            story, feed, timeline, discover, hashtag, notification, moderation, exif

PATTERNS: list[dict] = [
    # ── 1. Image optimization pipeline: resize + thumbnail generation ───────────
    {
        "normalized_code": """\
<?php

namespace App\\Jobs\\ImageOptimizePipeline;

use App\\Media;
use App\\Util\\Media\\Image;
use Carbon\\Carbon;
use Illuminate\\Bus\\Queueable;
use Illuminate\\Contracts\\Queue\\ShouldQueue;
use Illuminate\\Foundation\\Bus\\Dispatchable;
use Illuminate\\Queue\\InteractsWithQueue;
use Illuminate\\Queue\\SerializesModels;
use Log;
use Storage;

class ImageResize implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    protected $media;

    public function __construct(Media $media)
    {
        $this->media = $media;
    }

    public function handle()
    {
        $media = $this->media;
        if (!$media) {
            Log::info('ImageResize: Media no longer exists, skipping job');
            return;
        }

        if (!$media->media_path) {
            Log::info("ImageResize: Media {$media->id} has no media_path, skipping job");
            return;
        }

        $localFs = config('filesystems.default') === 'local';

        if ($localFs) {
            $path = storage_path('app/' . $media->media_path);
            if (!is_file($path) || $media->skip_optimize) {
                return;
            }
        } else {
            $disk = Storage::disk(config('filesystems.default'));
            if (!$disk->exists($media->media_path) || $media->skip_optimize) {
                return;
            }
        }

        try {
            $img = new Image;
            $img->resizeImage($media);
        } catch (\\Exception $e) {
            if (config('app.dev_log')) {
                Log::error('Image resize failed: ' . $e->getMessage());
            }
        }

        ImageThumbnail::dispatch($media)->onQueue('mmo');
    }
}
""",
        "function": "image_optimization_resize_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "app/Jobs/ImageOptimizePipeline/ImageResize.php",
    },
    # ── 2. Thumbnail generation with aspect ratio detection ────────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Util\\Media;

use App\\Media;
use Intervention\\Image\\Encoders\\JpegEncoder;
use Intervention\\Image\\Encoders\\PngEncoder;
use Intervention\\Image\\Encoders\\WebpEncoder;
use Log;
use Storage;

class Image
{
    public function orientations()
    {
        return [
            'square' => [
                'width' => 1080,
                'height' => 1080,
            ],
            'landscape' => [
                'width' => 1920,
                'height' => 1080,
            ],
            'portrait' => [
                'width' => 1080,
                'height' => 1350,
            ],
        ];
    }

    public function getAspect($width, $height, $isThumbnail)
    {
        if ($isThumbnail) {
            return [
                'dimensions' => [
                    'width' => 640,
                    'height' => 640,
                ],
                'orientation' => 'thumbnail',
            ];
        }

        $aspect = $width / $height;
        $orientation = $aspect === 1 ? 'square' :
        ($aspect > 1 ? 'landscape' : 'portrait');

        return [
            'dimensions' => $this->orientations()[$orientation],
            'orientation' => $orientation,
            'width_original' => $width,
            'height_original' => $height,
        ];
    }

    public function resizeThumbnail(Media $media)
    {
        $this->handleImageTransform($media, true);
    }
}
""",
        "function": "thumbnail_aspect_ratio_detection",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "app/Util/Media/Image.php",
    },
    # ── 3. Image filter definitions (Instagram-style effects) ──────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Util\\Media;

class Filter
{
    public static $filters = [
        '1984' => 'filter-1977',
        'Azen' => 'filter-aden',
        'Astairo' => 'filter-amaro',
        'Grassbee' => 'filter-ashby',
        'Bookrun' => 'filter-brannan',
        'Borough' => 'filter-brooklyn',
        'Farms' => 'filter-charmes',
        'Hairsadone' => 'filter-clarendon',
        'Cleana ' => 'filter-crema',
        'Catpatch' => 'filter-dogpatch',
        'Earlyworm' => 'filter-earlybird',
        'Plaid' => 'filter-gingham',
        'Kyo' => 'filter-ginza',
        'Yefe' => 'filter-hefe',
        'Goddess' => 'filter-helena',
        'Yards' => 'filter-hudson',
        'Quill' => 'filter-inkwell',
        'Rankine' => 'filter-kelvin',
        'Juno' => 'filter-juno',
        'Mark' => 'filter-lark',
        'Chill' => 'filter-lofi',
        'Van' => 'filter-ludwig',
    ];

    public static function classes(): array
    {
        return array_values(self::$filters);
    }

    public static function names(): array
    {
        return array_keys(self::$filters);
    }
}
""",
        "function": "image_filter_effects_library",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "app/Util/Media/Filter.php",
    },
    # ── 4. Story model: ephemeral content with expiration ───────────────────────
    {
        "normalized_code": """\
<?php

namespace App;

use App\\Util\\Lexer\\Bearcap;
use Illuminate\\Database\\Eloquent\\Model;
use Storage;

class Story extends Model
{
    use HasSnowflakePrimary;

    public const MAX_PER_DAY = 20;

    public $incrementing = false;

    protected $fillable = ['profile_id', 'view_count'];

    protected $visible = ['id'];

    protected function casts(): array
    {
        return [
            'story' => 'json',
            'expires_at' => 'datetime',
            'view_count' => 'integer',
        ];
    }

    public function profile()
    {
        return $this->belongsTo(Profile::class);
    }

    public function views()
    {
        return $this->hasMany(StoryView::class);
    }

    public function seen($profileId = false)
    {
        return StoryView::whereStoryId($this->id)
            ->whereProfileId($profileId)
            ->exists();
    }

    public function mediaUrl()
    {
        return url(Storage::url($this->path));
    }

    public function bearcapUrl()
    {
        return Bearcap::encode($this->url(), $this->bearcap_token);
    }
}
""",
        "function": "ephemeral_story_model_expiration",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/Story.php",
    },
    # ── 5. Status model: post/xxx_entry with media relations ──────────────────────
    {
        "normalized_code": """\
<?php

namespace App;

use App\\Models\\Poll;
use App\\Services\\StatusService;
use Illuminate\\Database\\Eloquent\\Model;
use Illuminate\\Database\\Eloquent\\SoftDeletes;
use Storage;

class Status extends Model
{
    use HasSnowflakePrimary, SoftDeletes;

    public $incrementing = false;

    protected $guarded = [];

    protected function casts(): array
    {
        return [
            'deleted_at' => 'datetime',
            'edited_at' => 'datetime',
        ];
    }

    const STATUS_TYPES = [
        'text',
        'photo',
        'photo:album',
        'video',
        'video:album',
        'photo:video:album',
        'share',
        'reply',
        'story',
        'story:reply',
        'story:reaction',
    ];

    const MAX_MENTIONS = 20;
    const MAX_HASHTAGS = 60;
    const MAX_LINKS = 5;

    public function profile()
    {
        return $this->belongsTo(Profile::class);
    }

    public function media()
    {
        return $this->hasMany(Media::class);
    }

    public function firstMedia()
    {
        return $this->hasMany(Media::class)->orderBy('position', 'asc')->first();
    }

    public function parent()
    {
        return $this->belongsTo(Status::class, 'in_reply_to_id');
    }
}
""",
        "function": "status_entry_model_with_media",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/Status.php",
    },
    # ── 6. Media model: local + remote media with cdn_url ──────────────────────
    {
        "normalized_code": """\
<?php

namespace App;

use Illuminate\\Database\\Eloquent\\Model;
use Illuminate\\Database\\Eloquent\\SoftDeletes;
use Storage;

class Media extends Model
{
    use SoftDeletes;

    protected $guarded = [];

    protected function casts(): array
    {
        return [
            'srcset' => 'array',
            'deleted_at' => 'datetime',
            'skip_optimize' => 'boolean',
        ];
    }

    public function status()
    {
        return $this->belongsTo(Status::class);
    }

    public function url(): string
    {
        if ($this->cdn_url) {
            return $this->cdn_url;
        }

        if ($this->remote_media && $this->remote_url) {
            return $this->remote_url;
        }

        return url(Storage::url($this->media_path));
    }

    public function thumbnailUrl(): string
    {
        if ($this->thumbnail_url) {
            return $this->thumbnail_url;
        }

        if (!$this->remote_media && $this->thumbnail_path) {
            return url(Storage::url($this->thumbnail_path));
        }

        if ($this->media_path && $this->mime && in_array($this->mime, ['image/jpeg', 'image/png', 'image/jpg'])) {
            return $this->media_path;
        }

        return url(Storage::url('public/no-preview.png'));
    }

    public function mimeType(): string
    {
        if (!$this->mime) {
            return '';
        }
        return explode('/', $this->mime)[0];
    }
}
""",
        "function": "media_model_cdn_storage",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/Media.php",
    },
    # ── 7. ActivityPub CreateNote transformer: JSON-LD federation ─────────────
    {
        "normalized_code": """\
<?php

namespace App\\Transformer\\ActivityPub\\Verb;

use App\\Models\\CustomEmoji;
use App\\Status;
use App\\Util\\Lexer\\Autolink;
use Illuminate\\Support\\Str;
use League\\Fractal;

class CreateNote extends Fractal\\TransformerAbstract
{
    public function transform(Status $status): array
    {
        $mentions = $status->mentions->map(function ($mention) {
            $webfinger = $mention->emailUrl();
            $name = Str::startsWith($webfinger, '@') ?
                $webfinger :
                '@' . $webfinger;

            return [
                'type' => 'Mention',
                'href' => $mention->permalink(),
                'name' => $name,
            ];
        })->toArray();

        $hashtags = $status->hashtags->map(function ($hashtag) {
            return [
                'type' => 'Hashtag',
                'href' => $hashtag->url(),
                'name' => '#' . $hashtag->name,
            ];
        })->toArray();

        $content = $status->caption ? nl2br(Autolink::create()->autolink($status->caption)) : '';

        return [
            '@context' => [
                'https://w3id.org/security/v1',
                'https://www.w3.org/ns/activitystreams',
                [
                    'Hashtag' => 'as:Hashtag',
                    'sensitive' => 'as:sensitive',
                    'pixelfed' => 'http://pixelfed.org/ns#',
                ],
            ],
            'type' => 'Create',
            'actor' => $status->profile->permalink(),
            'object' => [
                'type' => 'Note',
                'id' => $status->url(),
                'attributedTo' => $status->profile->permalink(),
                'content' => $content,
                'tag' => array_merge($mentions, $hashtags),
                'published' => $status->created_at->toRfc3339String(),
            ],
        ];
    }
}
""",
        "function": "activitypub_createnote_json_ld",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "app/Transformer/ActivityPub/Verb/CreateNote.php",
    },
    # ── 8. Webfinger endpoint for federation discovery ──────────────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Util\\Webfinger;

use App\\Profile;
use Illuminate\\Support\\Facades\\Cache;
use Illuminate\\Support\\Facades\\Log;

class Webfinger
{
    public static function lookup(string $handle, bool $fetch = true): ?array
    {
        $handle = str_replace('@', '', $handle);
        $cacheKey = 'webfinger:' . hash('sha256', $handle);

        if (Cache::has($cacheKey)) {
            return Cache::get($cacheKey);
        }

        $profile = Profile::where('username', $handle)->firstOrFail();

        $webfinger = [
            'subject' => 'acct:' . $profile->username . '@' . config('pixelfed.domain.app'),
            'aliases' => [$profile->permalink()],
            'links' => [
                [
                    'rel' => 'http://webfinger.net/rel/profile-page',
                    'type' => 'text/html',
                    'href' => $profile->permalink(),
                ],
                [
                    'rel' => 'self',
                    'type' => 'application/activity+json',
                    'href' => $profile->permalink(),
                ],
            ],
        ];

        Cache::remember($cacheKey, 3600, function () use ($webfinger) {
            return $webfinger;
        });

        return $webfinger;
    }
}
""",
        "function": "webfinger_federation_discovery",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "app/Util/Webfinger/Webfinger.php",
    },
    # ── 9. Notification model: feeds activity aggregation ──────────────────────
    {
        "normalized_code": """\
<?php

namespace App;

use Carbon\\Carbon;
use Illuminate\\Database\\Eloquent\\Model;

class Notification extends Model
{
    protected $guarded = [];

    protected function casts(): array
    {
        return [
            'data' => 'json',
        ];
    }

    const TYPE_LIKE = 'like';
    const TYPE_COMMENT = 'xxx_reply';
    const TYPE_FOLLOW = 'follow';
    const TYPE_MENTION = 'mention';
    const TYPE_SHARE = 'share';
    const TYPE_FOLLOW_REQUEST = 'follow_request';

    public function profile()
    {
        return $this->belongsTo(Profile::class);
    }

    public function actor()
    {
        return $this->belongsTo(Profile::class, 'actor_id');
    }

    public function item()
    {
        return $this->morphTo();
    }

    public function scopeUnread($query)
    {
        return $query->whereNull('read_at');
    }

    public function markAsRead(): void
    {
        if (!$this->read_at) {
            $this->read_at = Carbon::now();
            $this->save();
        }
    }
}
""",
        "function": "notification_activity_model",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "app/Notification.php",
    },
    # ── 10. Queue-based image optimize dispatcher ────────────────────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Jobs\\ImageOptimizePipeline;

use App\\Media;
use Illuminate\\Bus\\Queueable;
use Illuminate\\Contracts\\Queue\\ShouldQueue;
use Illuminate\\Foundation\\Bus\\Dispatchable;
use Illuminate\\Queue\\InteractsWithQueue;
use Illuminate\\Queue\\SerializesModels;
use Log;
use Storage;

class ImageOptimize implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    protected $media;

    public $deleteWhenMissingModels = true;

    public function __construct(Media $media)
    {
        $this->media = $media;
    }

    public function handle()
    {
        $media = $this->media;

        if (!$media) {
            Log::info('ImageOptimize: Media no longer exists, skipping job');
            return;
        }

        if (!$media->media_path) {
            Log::info("ImageOptimize: Media {$media->id} has no media_path, skipping job");
            return;
        }

        $localFs = config('filesystems.default') === 'local';

        if ($localFs) {
            $path = storage_path('app/' . $media->media_path);
            if (!is_file($path) || $media->skip_optimize) {
                return;
            }
        } else {
            $disk = Storage::disk(config('filesystems.default'));
            if (!$disk->exists($media->media_path) || $media->skip_optimize) {
                return;
            }
        }

        if ((bool) config_cache('pixelfed.optimize_image') == false) {
            ImageThumbnail::dispatch($media)->onQueue('mmo');
        } else {
            ImageResize::dispatch($media)->onQueue('mmo');
        }
    }
}
""",
        "function": "image_optimize_queue_dispatcher",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "app/Jobs/ImageOptimizePipeline/ImageOptimize.php",
    },
    # ── 11. EXIF data extraction and privacy stripping ──────────────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Util\\Media;

use Illuminate\\Support\\Facades\\Log;

class ExifData
{
    public static function extract(string $filePath): ?array
    {
        if (!extension_loaded('exif')) {
            Log::warning('EXIF extension not loaded');
            return null;
        }

        try {
            $exifData = @exif_read_data($filePath);

            if (!$exifData) {
                return null;
            }

            $safeFields = [
                'ImageLength',
                'ImageWidth',
                'Orientation',
                'XResolution',
                'YResolution',
                'ResolutionUnit',
                'DateTime',
                'Make',
                'Model',
            ];

            $result = [];
            foreach ($safeFields as $field) {
                if (isset($exifData[$field])) {
                    $result[$field] = $exifData[$field];
                }
            }

            return $result;
        } catch (\\Exception $e) {
            Log::error('EXIF extraction failed: ' . $e->getMessage());
            return null;
        }
    }

    public static function stripFromFile(string $filePath): bool
    {
        try {
            if (!extension_loaded('exif')) {
                return false;
            }

            $image = new \\Imagick($filePath);
            $image->stripImage();
            $image->writeImage($filePath);
            return true;
        } catch (\\Exception $e) {
            Log::error('EXIF stripping failed: ' . $e->getMessage());
            return false;
        }
    }
}
""",
        "function": "exif_privacy_stripping",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "app/Util/Media/ExifData.php",
    },
    # ── 12. Hashtag search + discover: aggregation by frequency ─────────────────
    {
        "normalized_code": """\
<?php

namespace App\\Services;

use App\\Hashtag;
use App\\Status;
use Illuminate\\Support\\Facades\\Cache;
use Illuminate\\Support\\Facades\\DB;

class DiscoverHashtagService
{
    public static function getTrendingHashtags(int $limit = 50): array
    {
        $cacheKey = 'discover:hashtags:trending:' . now()->format('YmdH');

        return Cache::remember($cacheKey, 3600, function () use ($limit) {
            $hashtags = Hashtag::query()
                ->select('hashtags.*', DB::raw('count(distinct status_id) as status_count'))
                ->join('hashtag_status', 'hashtags.id', '=', 'hashtag_status.hashtag_id')
                ->whereRaw('UNIX_TIMESTAMP(hashtag_status.created_at) > ?', [now()->subHours(24)->timestamp])
                ->groupBy('hashtags.id')
                ->sortByDesc('status_count')
                ->limit($limit)
                ->get();

            return $hashtags->map(function ($hashtag) {
                return [
                    'id' => $hashtag->id,
                    'name' => $hashtag->name,
                    'url' => $hashtag->url(),
                    'status_count' => $hashtag->status_count,
                ];
            })->toArray();
        });
    }

    public static function getHashtagStatuses(string $name, int $limit = 20, ?int $page = null): array
    {
        $hashtag = Hashtag::whereName($name)->firstOrFail();
        $offset = ($page - 1) * $limit;

        $statuses = $hashtag->statuses()
            ->where('visibility', '=', 'public')
            ->limit($limit)
            ->offset($offset)
            ->latest()
            ->get();

        return $statuses->map(function ($status) {
            return [
                'id' => $status->id,
                'url' => $status->url(),
                'created_at' => $status->created_at,
            ];
        })->toArray();
    }
}
""",
        "function": "discover_hashtag_service_trending",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "app/Services/DiscoverHashtagService.php",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "image optimization pipeline resize thumbnail queue job",
    "media CDN storage local remote URL serving",
    "story ephemeral content expiration datetime",
    "status xxx_entry model with media album relations",
    "ActivityPub federation JSON-LD CreateNote transformer",
    "Webfinger domain discovery federated social network",
    "notification activity model feed aggregation",
    "image EXIF privacy stripping metadata removal",
    "hashtag discover trending search aggregation count",
    "filter effects Instagram-style image transformations",
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
