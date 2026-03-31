"""
ingest_srs.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'ossrs/srs dans la KB Qdrant V6.

Focus : CORE patterns streaming media server (RTMP protocol, HLS segmentation,
packet encoding/decoding, coroutine-based connection handling, codec parsing,
DVR recording, stream pub/sub architecture, bandwidth control).

NOT CRUD/API patterns — patterns de streaming protocol et media container handling.

Usage:
    .venv/bin/python3 ingest_srs.py
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
REPO_URL = "https://github.com/ossrs/srs.git"
REPO_NAME = "ossrs/srs"
REPO_LOCAL = "/tmp/srs"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+st+rtmp+hls"
CHARTE_VERSION = "1.0"
TAG = "ossrs/srs"
SOURCE_REPO = "https://github.com/ossrs/srs"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# SRS = C++ streaming media server (RTMP, HLS, DVR, WebRTC, clustering).
# Patterns CORE : protocol handling, media container codecs, coroutine dispatch,
# connection state machines, pub/sub, bandwidth estimation.
# U-5 : noms streaming/network = GARDÉS (stream, client, connection, packet, frame, codec, etc.)
#       noms génériques interdits (message → packet/payload, task → coroutine/fiber, event → signal)

PATTERNS: list[dict] = [
    # ── 1. ISrsReader/ISrsWriter interface pattern (abstract codec I/O) ─────
    {
        "normalized_code": """\
#include <cstddef>

class ISrsReader
{
public:
    ISrsReader();
    virtual ~ISrsReader();

public:
    /**
     * Read bytes from reader (channel, socket, or file).
     * @param buf target buffer to read into
     * @param size bytes to read
     * @param nread actual bytes read, NULL to ignore
     * @return error code or success
     */
    virtual srs_error_t read(void *buf, size_t size, ssize_t *nread) = 0;
};

class ISrsStreamWriter
{
public:
    ISrsStreamWriter();
    virtual ~ISrsStreamWriter();

public:
    /**
     * Write bytes over writer (channel, socket, or file).
     * @param buf source buffer to write from
     * @param size bytes to write
     * @param nwrite actual bytes written, NULL to ignore
     * @return error code or success
     */
    virtual srs_error_t write(void *buf, size_t size, ssize_t *nwrite) = 0;
};
""",
        "function": "reader_writer_interface_io_abstraction",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_io.hpp",
    },
    # ── 2. ISrsEncoder/ISrsDecoder pattern (binary protocol serialization) ───
    {
        "normalized_code": """\
#include <cstdint>

class SrsBuffer;

class ISrsEncoder
{
public:
    ISrsEncoder();
    virtual ~ISrsEncoder();

public:
    /**
     * Calculate exact bytes needed to encode this object.
     * Used for buffer pre-allocation before encoding.
     * @return number of bytes required
     * @remark must be consistent for same object state
     */
    virtual uint64_t nb_bytes() = 0;

    /**
     * Encode this object into provided buffer.
     * @param buf target buffer (must have >= nb_bytes() space)
     * @return srs_success or error code
     * @remark buffer position advanced by bytes written
     */
    virtual srs_error_t encode(SrsBuffer *buf) = 0;
};

class ISrsDecoder
{
public:
    ISrsDecoder();
    virtual ~ISrsDecoder();

public:
    /**
     * Decode this object from binary data in buffer.
     * @param buf source buffer with binary data
     * @return srs_success or error code
     * @remark buffer position advanced by bytes consumed
     */
    virtual srs_error_t decode(SrsBuffer *buf) = 0;
};
""",
        "function": "encoder_decoder_binary_serialization",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_buffer.hpp",
    },
    # ── 3. SrsNaluSample + SrsMediaPacket (frame parsing & timestamping) ────
    {
        "normalized_code": """\
#include <cstdint>
#include <cstring>

class SrsNaluSample
{
public:
    int size_;
    char *bytes_;

public:
    SrsNaluSample();
    SrsNaluSample(char *b, int s);
    ~SrsNaluSample();

public:
    SrsNaluSample *copy();
};

enum SrsFrameType {
    SrsFrameTypeAudio = 0x01,
    SrsFrameTypeVideo = 0x02,
    SrsFrameTypeScript = 0x03,
};

class SrsMediaPacket
{
public:
    int64_t timestamp_;
    SrsFrameType message_type_;
    int32_t stream_id_;
    char *payload_;
    int size_;

public:
    SrsMediaPacket();
    virtual ~SrsMediaPacket();

public:
    virtual bool is_av();
    virtual bool is_audio();
    virtual bool is_video();
    virtual SrsMediaPacket *copy();
};
""",
        "function": "media_packet_nalu_frame_parsing",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/kernel/srs_kernel_packet.hpp",
    },
    # ── 4. SrsSimpleStream buffer management (append/erase/bytes access) ────
    {
        "normalized_code": """\
#include <vector>

class SrsSimpleStream
{
private:
    std::vector<char> data_;

public:
    SrsSimpleStream();
    virtual ~SrsSimpleStream();

public:
    /**
     * Get length of buffer (0 if empty).
     * @return number of bytes in buffer
     */
    virtual int length();

    /**
     * Get pointer to buffer bytes.
     * @return pointer to data, NULL if empty
     */
    virtual char *bytes();

    /**
     * Erase size bytes from beginning (sliding window).
     * Clears buffer if size >= length().
     * @param size number of bytes to remove from front
     */
    virtual void erase(int size);

    /**
     * Append bytes to end of buffer.
     * @param bytes source data
     * @param size number of bytes to copy
     */
    virtual void append(const char *bytes, int size);

    virtual void append(SrsSimpleStream *src);
};
""",
        "function": "simple_buffer_stream_sliding_window",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_stream.hpp",
    },
    # ── 5. ISrsCoroutineHandler (ST-coroutine dispatch + cycle pattern) ─────
    {
        "normalized_code": """\
#include <cstdint>

class ISrsCoroutineHandler
{
public:
    ISrsCoroutineHandler();
    virtual ~ISrsCoroutineHandler();

public:
    /**
     * Do the work cycle. Thread terminates if this returns.
     * For long-running coroutines (e.g., RTMP receive):
     *   while (true) {
     *       if ((err = coroutine->pull()) != srs_success) return err;
     *       // Do work (st_read, process, etc.)
     *   }
     * @return error code or srs_success
     */
    virtual srs_error_t cycle() = 0;
};

class ISrsStartable
{
public:
    ISrsStartable();
    virtual ~ISrsStartable();

public:
    virtual srs_error_t start() = 0;
};

class ISrsInterruptable
{
public:
    ISrsInterruptable();
    virtual ~ISrsInterruptable();

public:
    virtual void interrupt() = 0;
    virtual srs_error_t pull() = 0;
};

class ISrsStoppable
{
public:
    ISrsStoppable();
    virtual ~ISrsStoppable();

public:
    virtual void stop() = 0;
};
""",
        "function": "coroutine_handler_st_event_loop",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_st.hpp",
    },
    # ── 6. RTMP packet type constants (protocol control + data packets) ────
    {
        "normalized_code": """\
#define SRS_FLV_TAG_HEADER_SIZE 11
#define SRS_FLV_PREVIOUS_TAG_SIZE 4

// Protocol control packets (RTMP spec: type IDs 1-7)
#define RTMP_MSG_SetChunkSize 0x01
#define RTMP_MSG_AbortPacket 0x02
#define RTMP_MSG_Acknowledgement 0x03
#define RTMP_MSG_UserControlPacket 0x04
#define RTMP_MSG_WindowAcknowledgementSize 0x05
#define RTMP_MSG_SetPeerBandwidth 0x06
#define RTMP_MSG_EdgeAndOriginServerCommand 0x07

// Command packets (AMF0 and AMF3)
#define RTMP_MSG_AMF3CommandPacket 17
#define RTMP_MSG_AMF0CommandPacket 20

// Data packets (metadata, onMetaData)
#define RTMP_MSG_AMF3DataPacket 15
#define RTMP_MSG_AMF0DataPacket 18

// Shared object packets
#define RTMP_MSG_AMF3SharedObject 16
#define RTMP_MSG_AMF0SharedObject 19

// Media packets
#define RTMP_MSG_AudioPacket 8
#define RTMP_MSG_VideoPacket 9

// Aggregate packet (batched subpackets)
#define RTMP_MSG_AggregatePacket 22

// Stream control constants
#define RTMP_CID_OverConnection 0x03
#define RTMP_CID_OverConnection2 0x04
""",
        "function": "rtmp_protocol_packet_types",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_flv.hpp",
    },
    # ── 7. Video codec enumeration (H.264, H.265, VP9, AV1, etc.) ──────────
    {
        "normalized_code": """\
#include <cstdint>
#include <string>

enum SrsVideoCodecId {
    SrsVideoCodecIdReserved = 0,
    SrsVideoCodecIdForbidden = 0,
    SrsVideoCodecIdDisabled = 8,
    SrsVideoCodecIdSorensonH263 = 2,
    SrsVideoCodecIdScreenVideo = 3,
    SrsVideoCodecIdOn2VP6 = 4,
    SrsVideoCodecIdOn2VP6WithAlphaChannel = 5,
    SrsVideoCodecIdScreenVideoVersion2 = 6,
    SrsVideoCodecIdAVC = 7,
    SrsVideoCodecIdHEVC = 12,
    SrsVideoCodecIdAV1 = 13,
    SrsVideoCodecIdVP9 = 14,
};

enum SrsVideoAvcFrameTrait {
    SrsVideoAvcFrameTraitReserved = 6,
    SrsVideoAvcFrameTraitForbidden = 6,
    SrsVideoAvcFrameTraitSequenceHeader = 0,
    SrsVideoAvcFrameTraitNALU = 1,
    SrsVideoAvcFrameTraitSequenceHeaderEOF = 2,
    SrsVideoHEVCFrameTraitPacketTypeSequenceStart = 0,
    SrsVideoHEVCFrameTraitPacketTypeCodedFrames = 1,
    SrsVideoHEVCFrameTraitPacketTypeSequenceEnd = 2,
    SrsVideoHEVCFrameTraitPacketTypeCodedFramesX = 3,
};

std::string srs_video_codec_id2str(SrsVideoCodecId codec);
SrsVideoCodecId srs_video_codec_str2id(const std::string &codec);
""",
        "function": "video_codec_identifier_enumeration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_codec.hpp",
    },
    # ── 8. FLV container frame structure (audio/video frame headers) ──────
    {
        "normalized_code": """\
#include <cstdint>

class SrsBuffer;

class SrsFlvFrame
{
public:
    uint8_t type_;
    uint32_t size_;
    uint32_t timestamp_;
    uint32_t stream_id_;
    char *data_;

public:
    SrsFlvFrame();
    virtual ~SrsFlvFrame();

public:
    /**
     * Check if frame is audio frame.
     * @return true if RTMP_MSG_AudioPacket
     */
    virtual bool is_audio();

    /**
     * Check if frame is video frame.
     * @return true if RTMP_MSG_VideoPacket
     */
    virtual bool is_video();

    /**
     * Encode FLV frame header + data into buffer.
     * @param buf target buffer
     * @return srs_success or error
     */
    virtual srs_error_t encode(SrsBuffer *buf);

    /**
     * Decode FLV frame header + data from buffer.
     * @param buf source buffer with FLV data
     * @return srs_success or error
     */
    virtual srs_error_t decode(SrsBuffer *buf);
};
""",
        "function": "flv_frame_container_audio_video",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_flv.hpp",
    },
    # ── 9. Stream publish/subscribe state machine pattern ──────────────────
    {
        "normalized_code": """\
#include <cstdint>

enum SrsStreamSourceType {
    SrsStreamSourceTypeUnknown = 0,
    SrsStreamSourceTypeRtmp = 1,
    SrsStreamSourceTypeHls = 2,
    SrsStreamSourceTypeDvr = 3,
    SrsStreamSourceTypeRtc = 4,
};

enum SrsConnectionState {
    SrsConnectionStateNew = 0,
    SrsConnectionStateConnecting = 1,
    SrsConnectionStateConnected = 2,
    SrsConnectionStatePublishing = 3,
    SrsConnectionStatePlaying = 4,
    SrsConnectionStateClosed = 5,
};

class SrsStreamContext
{
private:
    SrsStreamSourceType source_type_;
    SrsConnectionState state_;
    int64_t create_time_;
    int64_t start_time_;
    char *stream_name_;
    char *vhost_;

public:
    SrsStreamContext();
    virtual ~SrsStreamContext();

public:
    virtual void set_source_type(SrsStreamSourceType t);
    virtual SrsStreamSourceType source_type();

    virtual void transition_state(SrsConnectionState new_state);
    virtual SrsConnectionState current_state();

    virtual int64_t duration();
};
""",
        "function": "stream_context_state_machine",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/kernel/srs_kernel_stream.hpp",
    },
    # ── 10. AAC audio codec header + sample extraction ────────────────────
    {
        "normalized_code": """\
#include <cstdint>
#include <cstddef>

class SrsBuffer;

enum SrsAacProfile {
    SrsAacProfileMain = 1,
    SrsAacProfileLC = 2,
    SrsAacProfileSSR = 3,
    SrsAacProfileLTP = 4,
};

enum SrsAacSampleRate {
    SrsAacSampleRate8000 = 0,
    SrsAacSampleRate16000 = 1,
    SrsAacSampleRate32000 = 2,
    SrsAacSampleRate44100 = 3,
    SrsAacSampleRate48000 = 4,
    SrsAacSampleRate88200 = 5,
    SrsAacSampleRate96000 = 6,
};

class SrsAacCodec
{
private:
    SrsAacProfile profile_;
    SrsAacSampleRate sample_rate_;
    uint8_t channels_;

public:
    SrsAacCodec();
    virtual ~SrsAacCodec();

public:
    /**
     * Parse AAC audio specific config from RTMP/FLV header.
     * @param buf buffer with AudioSpecificConfig (2 bytes)
     * @return srs_success or error
     */
    virtual srs_error_t parse_audio_specific_config(SrsBuffer *buf);

    /**
     * Get sample rate in Hz.
     * @return sample rate (8000, 16000, 44100, 48000, etc.)
     */
    virtual uint32_t get_sample_rate();

    /**
     * Get number of channels (1=mono, 2=stereo).
     * @return channel count
     */
    virtual uint8_t get_channels();
};
""",
        "function": "aac_codec_audio_header_parsing",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_aac.hpp",
    },
    # ── 11. MPEG-TS muxer for HLS segmentation (packet scheduling) ─────────
    {
        "normalized_code": """\
#include <cstdint>
#include <cstddef>
#include <vector>

class SrsBuffer;
class SrsMediaPacket;

class SrsTsContextWriter
{
private:
    int32_t stream_id_;
    std::vector<char> buffer_;
    uint32_t sync_byte_count_;
    uint64_t bytes_written_;

public:
    SrsTsContextWriter();
    virtual ~SrsTsContextWriter();

public:
    /**
     * Write audio frame into TS (MPEG-TS) packet stream.
     * Handles packetization and PES (Packetized Elementary Stream) wrapping.
     * @param frame media frame with audio data
     * @return srs_success or error
     */
    virtual srs_error_t write_audio_frame(SrsMediaPacket *frame);

    /**
     * Write video frame into TS packet stream.
     * Handles PES header, adaptation field, and PSI (Program Specific Information).
     * @param frame media frame with video data
     * @return srs_success or error
     */
    virtual srs_error_t write_video_frame(SrsMediaPacket *frame);

    /**
     * Flush current TS segment buffer (call when segment boundary reached).
     * @return bytes written, or <0 on error
     */
    virtual int flush_segment();

    /**
     * Get current segment size in bytes.
     * @return number of bytes in current segment
     */
    virtual uint64_t segment_size();
};
""",
        "function": "ts_muxer_hls_segment_writer",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_ts.hpp",
    },
    # ── 12. GOP (Group of Pictures) cache for fast stream startup ──────────
    {
        "normalized_code": """\
#include <cstdint>
#include <deque>
#include <memory>

class SrsMediaPacket;

class SrsGopCache
{
private:
    std::deque<std::shared_ptr<SrsMediaPacket>> packets_;
    int64_t first_video_dts_;
    uint32_t max_frames_;

public:
    SrsGopCache(uint32_t max_size = 300);
    virtual ~SrsGopCache();

public:
    /**
     * Add media frame to GOP cache.
     * Maintains sliding window of I-frames + dependent B/P frames.
     * @param frame media frame (audio or video)
     */
    virtual void add_frame(SrsMediaPacket *frame);

    /**
     * Get all frames starting from last keyframe (video I-frame).
     * Used for fast startup: send GOP cache to newly connecting clients.
     * @return list of frames in GOP cache (or empty if no I-frame yet)
     */
    virtual std::deque<std::shared_ptr<SrsMediaPacket>> get_gop();

    /**
     * Clear cache (e.g., on source disconnect or config change).
     */
    virtual void clear();

    /**
     * Check if cache has valid I-frame (can start playback from here).
     * @return true if at least one I-frame is in cache
     */
    virtual bool has_keyframe();
};
""",
        "function": "gop_cache_fast_stream_startup",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/kernel/srs_kernel_kbps.hpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "RTMP protocol control packet types and chunk stream encoding",
    "read write interface for socket and file I/O streaming",
    "media packet timestamp NAL unit sample frame parsing",
    "coroutine handler ST event loop cycle pattern",
    "binary encoder decoder serialization protocol",
    "MPEG-TS muxer HLS segment writer audio video frames",
    "AAC audio codec header profile sample rate channels",
    "FLV container frame audio video frame serialization",
    "stream publish subscribe connection state machine",
    "GOP cache group of pictures fast startup keyframe",
    "simple stream buffer sliding window append erase",
    "video codec enumeration H264 H265 VP9 AV1",
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
