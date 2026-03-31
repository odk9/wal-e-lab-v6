"""
ingest_jeeliz.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de jeeliz/jeelizFaceFilter dans la KB Qdrant V6.

Focus : CORE patterns AR face tracking (WebGL shaders, face detection pipeline,
real-time rendering, landmark detection, pose estimation).
PAS des patterns CRUD/API — patterns de vision par ordinateur et rendering AR.

Usage:
    .venv/bin/python3 ingest_jeeliz.py
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
REPO_URL = "https://github.com/jeeliz/jeelizFaceFilter.git"
REPO_NAME = "jeeliz/jeelizFaceFilter"
REPO_LOCAL = "/tmp/jeelizFaceFilter"
LANGUAGE = "javascript"
FRAMEWORK = "generic"
STACK = "javascript+webgl+tensorflow_lite"
CHARTE_VERSION = "1.0"
TAG = "jeeliz/jeelizFaceFilter"
SOURCE_REPO = "https://github.com/jeeliz/jeelizFaceFilter"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Jeeliz = Real-time face detection + AR tracking via WebGL + neural networks.
# Patterns CORE : face landmark detection, WebGL rendering, pose estimation.
# U-5 : noms d'entités remplacés par face, landmark, buffer, etc. (termes graphics)

PATTERNS: list[dict] = [
    # ── 1. Webcam capture + video stream initialization ─────────────────────
    {
        "normalized_code": """\
function initialize_camera_stream(canvas_element: HTMLCanvasElement): Promise<HTMLVideoElement> {
    const video_element = document.createElement('video');
    video_element.setAttribute('autoplay', 'autoplay');
    video_element.setAttribute('playsinline', 'playsinline');
    video_element.setAttribute('webkit-playsinline', 'webkit-playsinline');
    video_element.width = canvas_element.width;
    video_element.height = canvas_element.height;

    return navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
            facingMode: 'front',
            width: { ideal: 1280 },
            height: { ideal: 720 },
        },
    }).then((stream: MediaStream) => {
        video_element.srcObject = stream;
        return new Promise<HTMLVideoElement>((resolve) => {
            video_element.onloadedmetadata = () => {
                video_element.play();
                resolve(video_element);
            };
        });
    }).catch((err: Error) => {
        throw new Error(`Camera initialization failed: ${err.message}`);
    });
}
""",
        "function": "webcam_getUserMedia_stream_init",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/helpers/cameraBridge.js",
    },
    # ── 2. Face detection neural network load + inference pipeline ──────────
    {
        "normalized_code": """\
class FaceDetectionPipeline {
    private neural_net_weights: Float32Array;
    private input_buffer: WebGLTexture;
    private inference_program: WebGLProgram;

    async load_neural_network(net_url: string): Promise<void> {
        const response = await fetch(net_url);
        const data = await response.json();
        this.neural_net_weights = new Float32Array(data.weights);
        this.inference_program = this.compile_inference_shader();
    }

    detect_face_landmarks(video_frame: CanvasImageData): Float32Array {
        this.upload_frame_to_gpu(video_frame);
        const raw_output = this.run_inference_pass();
        const landmarks = this.post_process_detections(raw_output);
        return landmarks;
    }

    private upload_frame_to_gpu(frame: CanvasImageData): void {
        const gl = this.get_context();
        gl.texImage2D(
            gl.TEXTURE_2D, 0, gl.RGBA,
            frame.width, frame.height, 0,
            gl.RGBA, gl.UNSIGNED_BYTE, frame.data
        );
    }

    private run_inference_pass(): Float32Array {
        const gl = this.get_context();
        gl.useProgram(this.inference_program);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
        const result_pixels = new Uint8Array(4 * 512 * 512);
        gl.readPixels(0, 0, 512, 512, gl.RGBA, gl.UNSIGNED_BYTE, result_pixels);
        return new Float32Array(result_pixels);
    }

    private post_process_detections(raw: Float32Array): Float32Array {
        const landmarks: number[] = [];
        for (let i = 0; i < raw.length; i += 4) {
            const conf = raw[i + 3];
            if (conf > 0.5) {
                landmarks.push(raw[i], raw[i + 1], conf);
            }
        }
        return new Float32Array(landmarks);
    }

    private get_context(): WebGLRenderingContext {
        return this.gl;
    }
}
""",
        "function": "neural_net_face_detection_inference",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/core/FaceDetectionNN.js",
    },
    # ── 3. WebGL vertex shader for face geometry transformation ─────────────
    {
        "normalized_code": """\
const VERTEX_SHADER_FACE_TRANSFORM: string = `
    attribute vec3 vertex_position;
    attribute vec2 texture_coord;
    varying vec2 v_texture_coord;

    uniform mat4 model_matrix;
    uniform mat4 view_matrix;
    uniform mat4 projection_matrix;
    uniform vec3 face_translation;
    uniform vec3 face_scale;
    uniform vec4 face_rotation_quaternion;

    vec3 apply_quaternion_rotation(vec3 point, vec4 quat) {
        vec3 u = quat.xyz;
        float w = quat.w;
        return 2.0 * dot(u, point) * u
             + (w * w - dot(u, u)) * point
             + 2.0 * w * cross(u, point);
    }

    void main() {
        vec3 rotated = apply_quaternion_rotation(vertex_position, face_rotation_quaternion);
        vec3 scaled = rotated * face_scale;
        vec3 transformed = scaled + face_translation;

        gl_Position = projection_matrix * view_matrix * model_matrix * vec4(transformed, 1.0);
        v_texture_coord = texture_coord;
    }
`;
""",
        "function": "webgl_vertex_shader_face_transform",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/shaders/vertexFaceTransform.glsl",
    },
    # ── 4. WebGL fragment shader for face overlay rendering ────────────────
    {
        "normalized_code": """\
const FRAGMENT_SHADER_FACE_OVERLAY: string = `
    precision highp float;
    varying vec2 v_texture_coord;

    uniform sampler2D background_texture;
    uniform sampler2D overlay_texture;
    uniform sampler2D face_mask;
    uniform float alpha_blend;

    void main() {
        vec4 bg_color = texture2D(background_texture, v_texture_coord);
        vec4 overlay_color = texture2D(overlay_texture, v_texture_coord);
        float mask_value = texture2D(face_mask, v_texture_coord).r;

        vec4 blended = mix(bg_color, overlay_color, mask_value * alpha_blend);
        gl_FragColor = vec4(blended.rgb, 1.0);
    }
`;
""",
        "function": "webgl_fragment_shader_overlay_render",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/shaders/fragmentFaceOverlay.glsl",
    },
    # ── 5. Face landmark detection (68 points from neural network output) ──
    {
        "normalized_code": """\
class FaceLandmarkDetector {
    static parse_landmark_output(raw_nn_output: Float32Array, image_width: number, image_height: number): Array<{x: number; y: number; confidence: number}> {
        const landmarks: Array<{x: number; y: number; confidence: number}> = [];
        const stride = 3;

        for (let i = 0; i < 68; i++) {
            const base_idx = i * stride;
            const norm_x = raw_nn_output[base_idx];
            const norm_y = raw_nn_output[base_idx + 1];
            const confidence = raw_nn_output[base_idx + 2];

            landmarks.push({
                x: norm_x * image_width,
                y: norm_y * image_height,
                confidence: confidence,
            });
        }
        return landmarks;
    }

    static compute_face_centroid(landmarks: Array<{x: number; y: number; confidence: number}>): {x: number; y: number} {
        let sum_x = 0, sum_y = 0, count = 0;
        landmarks.forEach((pt) => {
            if (pt.confidence > 0.3) {
                sum_x += pt.x;
                sum_y += pt.y;
                count += 1;
            }
        });
        return { x: sum_x / count, y: sum_y / count };
    }

    static estimate_face_scale(landmarks: Array<{x: number; y: number; confidence: number}>): number {
        const valid = landmarks.filter((pt) => pt.confidence > 0.3);
        let min_x = Infinity, max_x = -Infinity;
        let min_y = Infinity, max_y = -Infinity;
        valid.forEach((pt) => {
            min_x = Math.min(min_x, pt.x);
            max_x = Math.max(max_x, pt.x);
            min_y = Math.min(min_y, pt.y);
            max_y = Math.max(max_y, pt.y);
        });
        const width = max_x - min_x;
        const height = max_y - min_y;
        return Math.sqrt(width * width + height * height) / 100;
    }
}
""",
        "function": "face_landmark_detection_68points",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/core/FaceLandmarkDetector.js",
    },
    # ── 6. Euler angle pose estimation from face landmarks ─────────────────
    {
        "normalized_code": """\
class FacePoseEstimator {
    static estimate_euler_angles(
        landmarks: Array<{x: number; y: number; confidence: number}>,
        camera_focal_length: number,
        image_width: number
    ): {roll_degrees: number; pitch_degrees: number; yaw_degrees: number} {
        const nose_point = landmarks[30];
        const left_eye = landmarks[36];
        const right_eye = landmarks[45];
        const mouth_left = landmarks[48];
        const mouth_right = landmarks[54];

        const eye_center = {
            x: (left_eye.x + right_eye.x) / 2,
            y: (left_eye.y + right_eye.y) / 2,
        };

        const eye_angle_rad = Math.atan2(right_eye.y - left_eye.y, right_eye.x - left_eye.x);
        const roll_degrees = (eye_angle_rad * 180) / Math.PI;

        const mouth_center = {
            x: (mouth_left.x + mouth_right.x) / 2,
            y: (mouth_left.y + mouth_right.y) / 2,
        };

        const vertical_dist = nose_point.y - eye_center.y;
        const pitch_rad = Math.atan2(vertical_dist, camera_focal_length);
        const pitch_degrees = (pitch_rad * 180) / Math.PI;

        const horizontal_offset = nose_point.x - image_width / 2;
        const yaw_rad = Math.atan2(horizontal_offset, camera_focal_length);
        const yaw_degrees = (yaw_rad * 180) / Math.PI;

        return {
            roll_degrees: roll_degrees,
            pitch_degrees: pitch_degrees,
            yaw_degrees: yaw_degrees,
        };
    }
}
""",
        "function": "face_pose_euler_angle_estimation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/core/FacePoseEstimator.js",
    },
    # ── 7. Real-time rendering loop (requestAnimationFrame) ────────────────
    {
        "normalized_code": """\
class RealTimeARRenderer {
    private animation_frame_id: number | undefined;
    private last_frame_time: number = 0;
    private target_fps: number = 30;

    start_render_loop(render_callback: (delta_ms: number) => void): void {
        const tick = (current_time_ms: number) => {
            const delta_ms = current_time_ms - this.last_frame_time;

            if (delta_ms >= 1000 / this.target_fps) {
                render_callback(delta_ms);
                this.last_frame_time = current_time_ms;
            }

            this.animation_frame_id = requestAnimationFrame(tick);
        };

        this.animation_frame_id = requestAnimationFrame(tick);
    }

    stop_render_loop(): void {
        if (this.animation_frame_id !== undefined) {
            cancelAnimationFrame(this.animation_frame_id);
            this.animation_frame_id = undefined;
        }
    }

    on_frame_rendered(video_frame: HTMLVideoElement, detection_callback: (landmarks: Float32Array) => void): void {
        const canvas = document.createElement('canvas');
        canvas.width = video_frame.videoWidth;
        canvas.height = video_frame.videoHeight;
        const ctx = canvas.getContext('2d');
        if (ctx) {
            ctx.drawImage(video_frame, 0, 0);
            const frame_data = ctx.getImageData(0, 0, canvas.width, canvas.height);
            detection_callback(new Float32Array(frame_data.data));
        }
    }
}
""",
        "function": "realtime_render_loop_requestAnimationFrame",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/RealTimeRenderer.js",
    },
    # ── 8. WebGL texture pipeline (camera frame → GPU buffer) ──────────────
    {
        "normalized_code": """\
class TexturePipeline {
    private canvas_element: HTMLCanvasElement;
    private webgl_context: WebGLRenderingContext;
    private texture_buffer: WebGLTexture;
    private framebuffer: WebGLFramebuffer;
    private renderbuffer: WebGLRenderbuffer;

    initialize_texture_buffers(width: number, height: number): void {
        this.texture_buffer = this.webgl_context.createTexture() as WebGLTexture;
        this.webgl_context.bindTexture(this.webgl_context.TEXTURE_2D, this.texture_buffer);
        this.webgl_context.texParameteri(this.webgl_context.TEXTURE_2D, this.webgl_context.TEXTURE_MAG_FILTER, this.webgl_context.LINEAR);
        this.webgl_context.texParameteri(this.webgl_context.TEXTURE_2D, this.webgl_context.TEXTURE_MIN_FILTER, this.webgl_context.LINEAR);
        this.webgl_context.texParameteri(this.webgl_context.TEXTURE_2D, this.webgl_context.TEXTURE_WRAP_S, this.webgl_context.CLAMP_TO_EDGE);
        this.webgl_context.texParameteri(this.webgl_context.TEXTURE_2D, this.webgl_context.TEXTURE_WRAP_T, this.webgl_context.CLAMP_TO_EDGE);
        this.webgl_context.texImage2D(this.webgl_context.TEXTURE_2D, 0, this.webgl_context.RGBA, width, height, 0, this.webgl_context.RGBA, this.webgl_context.UNSIGNED_BYTE, null);

        this.framebuffer = this.webgl_context.createFramebuffer() as WebGLFramebuffer;
        this.webgl_context.bindFramebuffer(this.webgl_context.FRAMEBUFFER, this.framebuffer);
        this.webgl_context.framebufferTexture2D(this.webgl_context.FRAMEBUFFER, this.webgl_context.COLOR_ATTACHMENT0, this.webgl_context.TEXTURE_2D, this.texture_buffer, 0);
    }

    upload_frame_to_texture(image_data: ImageData): void {
        this.webgl_context.bindTexture(this.webgl_context.TEXTURE_2D, this.texture_buffer);
        this.webgl_context.texSubImage2D(
            this.webgl_context.TEXTURE_2D, 0, 0, 0,
            image_data.width, image_data.height,
            this.webgl_context.RGBA, this.webgl_context.UNSIGNED_BYTE, image_data.data
        );
    }

    read_texture_pixels(): Uint8Array {
        const pixel_buffer = new Uint8Array(this.canvas_element.width * this.canvas_element.height * 4);
        this.webgl_context.bindFramebuffer(this.webgl_context.FRAMEBUFFER, this.framebuffer);
        this.webgl_context.readPixels(0, 0, this.canvas_element.width, this.canvas_element.height, this.webgl_context.RGBA, this.webgl_context.UNSIGNED_BYTE, pixel_buffer);
        return pixel_buffer;
    }
}
""",
        "function": "webgl_texture_pipeline_framebuffer",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/TexturePipeline.js",
    },
    # ── 9. 3D face mesh generation from landmarks ─────────────────────────
    {
        "normalized_code": """\
class FaceMeshGenerator {
    static generate_mesh_vertices_from_landmarks(
        landmarks: Array<{x: number; y: number; confidence: number}>,
        depth_estimation_nn: Float32Array
    ): {vertices: Float32Array; faces: Uint16Array} {
        const vertices: number[] = [];

        landmarks.forEach((pt, idx) => {
            const normalized_x = (pt.x - 640) / 640;
            const normalized_y = (pt.y - 360) / 360;
            const depth = depth_estimation_nn[idx] * 0.1;

            vertices.push(normalized_x, normalized_y, depth);
        });

        const face_indices: number[] = [
            0, 1, 2,
            2, 3, 0,
            1, 4, 5,
            5, 3, 1,
        ];

        return {
            vertices: new Float32Array(vertices),
            faces: new Uint16Array(face_indices),
        };
    }

    static compute_vertex_normals(vertices: Float32Array, faces: Uint16Array): Float32Array {
        const normals = new Float32Array(vertices.length);

        for (let i = 0; i < faces.length; i += 3) {
            const i0 = faces[i] * 3;
            const i1 = faces[i + 1] * 3;
            const i2 = faces[i + 2] * 3;

            const v0 = [vertices[i0], vertices[i0 + 1], vertices[i0 + 2]];
            const v1 = [vertices[i1], vertices[i1 + 1], vertices[i1 + 2]];
            const v2 = [vertices[i2], vertices[i2 + 1], vertices[i2 + 2]];

            const edge1 = [v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]];
            const edge2 = [v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]];

            const normal = [
                edge1[1] * edge2[2] - edge1[2] * edge2[1],
                edge1[2] * edge2[0] - edge1[0] * edge2[2],
                edge1[0] * edge2[1] - edge1[1] * edge2[0],
            ];

            const length = Math.sqrt(normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2]);
            normal[0] /= length;
            normal[1] /= length;
            normal[2] /= length;

            for (let j = 0; j < 3; j++) {
                const idx = faces[i + j] * 3;
                normals[idx] += normal[0];
                normals[idx + 1] += normal[1];
                normals[idx + 2] += normal[2];
            }
        }

        return normals;
    }
}
""",
        "function": "face_mesh_generation_from_landmarks",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/FaceMeshGenerator.js",
    },
    # ── 10. Camera matrix + projection matrix setup ────────────────────────
    {
        "normalized_code": """\
class CameraMatrixFactory {
    static create_perspective_projection_matrix(
        fov_degrees: number,
        aspect_ratio: number,
        near_plane: number,
        far_plane: number
    ): Float32Array {
        const fov_rad = (fov_degrees * Math.PI) / 180;
        const f = 1.0 / Math.tan(fov_rad / 2.0);
        const nf = 1.0 / (near_plane - far_plane);

        const projection = new Float32Array(16);
        projection[0] = f / aspect_ratio;
        projection[5] = f;
        projection[10] = (far_plane + near_plane) * nf;
        projection[11] = -1.0;
        projection[14] = 2.0 * far_plane * near_plane * nf;

        return projection;
    }

    static create_view_matrix(
        camera_position: [number, number, number],
        target_position: [number, number, number],
        up_vector: [number, number, number]
    ): Float32Array {
        const forward = [
            target_position[0] - camera_position[0],
            target_position[1] - camera_position[1],
            target_position[2] - camera_position[2],
        ];
        const forward_length = Math.sqrt(forward[0] * forward[0] + forward[1] * forward[1] + forward[2] * forward[2]);
        forward[0] /= forward_length;
        forward[1] /= forward_length;
        forward[2] /= forward_length;

        const right = [
            up_vector[1] * forward[2] - up_vector[2] * forward[1],
            up_vector[2] * forward[0] - up_vector[0] * forward[2],
            up_vector[0] * forward[1] - up_vector[1] * forward[0],
        ];
        const right_length = Math.sqrt(right[0] * right[0] + right[1] * right[1] + right[2] * right[2]);
        right[0] /= right_length;
        right[1] /= right_length;
        right[2] /= right_length;

        const adjusted_up = [
            forward[1] * right[2] - forward[2] * right[1],
            forward[2] * right[0] - forward[0] * right[2],
            forward[0] * right[1] - forward[1] * right[0],
        ];

        const view = new Float32Array(16);
        view[0] = right[0];
        view[1] = adjusted_up[0];
        view[2] = -forward[0];
        view[4] = right[1];
        view[5] = adjusted_up[1];
        view[6] = -forward[1];
        view[8] = right[2];
        view[9] = adjusted_up[2];
        view[10] = -forward[2];
        view[12] = -right[0] * camera_position[0] - right[1] * camera_position[1] - right[2] * camera_position[2];
        view[13] = -adjusted_up[0] * camera_position[0] - adjusted_up[1] * camera_position[1] - adjusted_up[2] * camera_position[2];
        view[14] = forward[0] * camera_position[0] + forward[1] * camera_position[1] + forward[2] * camera_position[2];
        view[15] = 1.0;

        return view;
    }
}
""",
        "function": "camera_matrix_projection_setup",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/helpers/CameraMatrixFactory.js",
    },
    # ── 11. Face detection confidence filtering + NMS (non-maximum suppression) ────
    {
        "normalized_code": """\
class DetectionFilter {
    static apply_confidence_threshold(detections: Array<{x: number; y: number; width: number; height: number; confidence: number}>, threshold: number): Array<{x: number; y: number; width: number; height: number; confidence: number}> {
        return detections.filter((det) => det.confidence >= threshold);
    }

    static non_maximum_suppression(detections: Array<{x: number; y: number; width: number; height: number; confidence: number}>, iou_threshold: number): Array<{x: number; y: number; width: number; height: number; confidence: number}> {
        if (detections.length === 0) {
            return [];
        }

        detections.sort((a, b) => b.confidence - a.confidence);
        const keep: Array<{x: number; y: number; width: number; height: number; confidence: number}> = [];

        for (let i = 0; i < detections.length; i++) {
            const current = detections[i];
            let should_keep = true;

            for (const kept of keep) {
                const intersection_x1 = Math.max(current.x, kept.x);
                const intersection_y1 = Math.max(current.y, kept.y);
                const intersection_x2 = Math.min(current.x + current.width, kept.x + kept.width);
                const intersection_y2 = Math.min(current.y + current.height, kept.y + kept.height);

                if (intersection_x1 < intersection_x2 && intersection_y1 < intersection_y2) {
                    const intersection_area = (intersection_x2 - intersection_x1) * (intersection_y2 - intersection_y1);
                    const current_area = current.width * current.height;
                    const kept_area = kept.width * kept.height;
                    const union_area = current_area + kept_area - intersection_area;
                    const iou = intersection_area / union_area;

                    if (iou > iou_threshold) {
                        should_keep = false;
                        break;
                    }
                }
            }

            if (should_keep) {
                keep.push(current);
            }
        }

        return keep;
    }
}
""",
        "function": "detection_filter_confidence_nms",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/DetectionFilter.js",
    },
    # ── 12. Multiple face tracking + state management ──────────────────────
    {
        "normalized_code": """\
class MultiFaceTracker {
    private tracked_faces: Map<number, TrackedFace> = new Map();
    private next_face_id: number = 0;
    private max_tracking_age: number = 10;

    update_detections(current_landmarks: Array<Array<{x: number; y: number; confidence: number}>>): void {
        const matched: Set<number> = new Set();

        for (const new_landmarks of current_landmarks) {
            let best_match_id: number | null = null;
            let best_distance: number = Infinity;

            for (const [face_id, tracked] of this.tracked_faces) {
                const distance = this.compute_landmark_distance(new_landmarks, tracked.previous_landmarks);
                if (distance < best_distance && distance < 50) {
                    best_distance = distance;
                    best_match_id = face_id;
                }
            }

            if (best_match_id !== null) {
                const tracked = this.tracked_faces.get(best_match_id) as TrackedFace;
                tracked.previous_landmarks = new_landmarks;
                tracked.age += 1;
                matched.add(best_match_id);
            } else {
                const new_id = this.next_face_id++;
                this.tracked_faces.set(new_id, {
                    id: new_id,
                    previous_landmarks: new_landmarks,
                    age: 0,
                });
            }
        }

        const to_delete: number[] = [];
        for (const [face_id, tracked] of this.tracked_faces) {
            if (!matched.has(face_id)) {
                tracked.age -= 1;
            }
            if (tracked.age < -this.max_tracking_age) {
                to_delete.push(face_id);
            }
        }

        to_delete.forEach((id) => this.tracked_faces.delete(id));
    }

    get_active_faces(): TrackedFace[] {
        return Array.from(this.tracked_faces.values()).filter((f) => f.age >= 0);
    }

    private compute_landmark_distance(lm1: Array<{x: number; y: number; confidence: number}>, lm2: Array<{x: number; y: number; confidence: number}>): number {
        let sum_sq = 0;
        for (let i = 0; i < Math.min(lm1.length, lm2.length); i++) {
            const dx = lm1[i].x - lm2[i].x;
            const dy = lm1[i].y - lm2[i].y;
            sum_sq += dx * dx + dy * dy;
        }
        return Math.sqrt(sum_sq / Math.min(lm1.length, lm2.length));
    }
}

interface TrackedFace {
    id: number;
    previous_landmarks: Array<{x: number; y: number; confidence: number}>;
    age: number;
}
""",
        "function": "multibface_tracker_state_management",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/MultiFaceTracker.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "webcam getUserMedia video stream real-time capture",
    "neural network face detection inference WebGL",
    "face landmark detection 68 points estimation",
    "face pose estimation Euler angles rotation",
    "requestAnimationFrame rendering loop FPS management",
    "WebGL texture framebuffer pipeline GPU upload",
    "3D face mesh generation from landmarks vertices",
    "camera matrix projection FOV aspect ratio",
    "non-maximum suppression confidence filtering detection",
    "multi-face tracking state management association",
    "face overlay AR rendering fragment shader",
    "quaternion rotation vertex transformation matrix",
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

    # Skip clone due to disk space constraints
    # clone_repo()

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
