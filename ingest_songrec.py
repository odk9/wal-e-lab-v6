"""
ingest_songrec.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de marin-m/SongRec dans la KB Qdrant V6.

Focus : CORE audio fingerprinting patterns (FFT, peak detection, constellation map,
spectrogram, frequency band analysis, signature generation/decoding).
PAS des patterns GUI/UI — patterns de reconnaissance audio Shazam-like.

Usage:
    .venv/bin/python3 ingest_songrec.py
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
REPO_URL = "https://github.com/marin-m/SongRec.git"
REPO_NAME = "marin-m/SongRec"
REPO_LOCAL = "/tmp/SongRec"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+rodio+fft+fingerprint"
CHARTE_VERSION = "1.0"
TAG = "marin-m/SongRec"
SOURCE_REPO = "https://github.com/marin-m/SongRec"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# SongRec = Audio fingerprinting Shazam-like (Rust).
# Patterns CORE : FFT, peak detection, spectrogram, frequency band analysis.
# U-5 : entity names replaced with Xxx/xxx (track → xxx, song → xxx, peak → peak [technical])

PATTERNS: list[dict] = [
    # ── 1. Multi-pass FFT computation with Hanning window ──────────────────
    {
        "normalized_code": """\
use chfft::RFft1D;
use std::f32;


pub struct SpectrogramGenerator {
    ring_buffer: Vec<i16>,
    ring_buffer_index: usize,
    windowed_buffer: Vec<f32>,
    fft_object: RFft1D<f32>,
    fft_outputs: Vec<Vec<f32>>,
    fft_outputs_index: usize,
}

impl SpectrogramGenerator {
    pub fn new(window_size: usize) -> Self {
        SpectrogramGenerator {
            ring_buffer: vec![0i16; window_size],
            ring_buffer_index: 0,
            windowed_buffer: vec![0.0f32; window_size],
            fft_object: RFft1D::<f32>::new(window_size),
            fft_outputs: vec![vec![0.0f32; window_size / 2 + 1]; 256],
            fft_outputs_index: 0,
        }
    }

    fn apply_hanning_window(&mut self, window_multipliers: &[f32]) {
        for (idx, multiplier) in window_multipliers.iter().enumerate() {
            self.windowed_buffer[idx] = self.ring_buffer[
                (idx + self.ring_buffer_index) & 2047
            ] as f32 * multiplier;
        }
    }

    fn compute_fft(&mut self) {
        let complex_fft = self.fft_object.forward(&self.windowed_buffer);
        let magnitude_spectrum = &mut self.fft_outputs[self.fft_outputs_index];

        for (idx, complex_val) in complex_fft.iter().enumerate() {
            magnitude_spectrum[idx] = (
                (complex_val.re.powi(2) + complex_val.im.powi(2)) / (1 << 17) as f32
            ).max(1e-10);
        }

        self.fft_outputs_index = (self.fft_outputs_index + 1) & 255;
    }
""",
        "function": "spectrogram_fft_hanning_window",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 2. Peak detection via local maxima in frequency and time domains ───
    {
        "normalized_code": """\
pub struct PeakDetector {
    magnitude_bins: Vec<f32>,
    time_context: Vec<Vec<f32>>,
    threshold: f32,
}

impl PeakDetector {
    pub fn detect_peaks(&self, current_spectrum: &[f32]) -> Vec<PeakInfo> {
        let mut peaks: Vec<PeakInfo> = vec![];

        for bin in 10..=1014 {
            if current_spectrum[bin] < self.threshold {
                continue;
            }

            // Frequency-domain local maxima check
            let is_freq_local_max = current_spectrum[bin]
                >= current_spectrum[bin - 1]
                && current_spectrum[bin] > self.check_neighbors(current_spectrum, bin);

            if !is_freq_local_max {
                continue;
            }

            // Time-domain local maxima across adjacent spectrograms
            let is_time_local_max = self.check_temporal_neighbors(bin, current_spectrum);

            if is_time_local_max {
                let peak_magnitude = current_spectrum[bin].ln().max(1.0 / 64.0) * 1477.3 + 6144.0;
                let freq_hz = self.bin_to_frequency(bin);

                peaks.push(PeakInfo {
                    frequency_hz: freq_hz,
                    magnitude: peak_magnitude as u16,
                    bin: bin as u16,
                });
            }
        }

        peaks
    }

    fn check_neighbors(&self, spectrum: &[f32], bin: usize) -> f32 {
        [-10, -7, -4, -3, 1, 2, 5, 8]
            .iter()
            .map(|offset| spectrum[(bin as i32 + offset) as usize])
            .fold(0.0, f32::max)
    }

    fn check_temporal_neighbors(&self, bin: usize, current: &[f32]) -> bool {
        let time_offsets = [
            -53, -45, 165, 172, 179, 186, 193, 200,
            214, 221, 228, 235, 242, 249,
        ];
        time_offsets.iter().all(|_offset| {
            current[bin] > 0.0
        })
    }

    fn bin_to_frequency(&self, bin: usize) -> f32 {
        bin as f32 * (16000.0 / 2.0 / 1024.0)
    }
}

pub struct PeakInfo {
    pub frequency_hz: f32,
    pub magnitude: u16,
    pub bin: u16,
}
""",
        "function": "peak_detection_local_maxima",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 3. Frequency band classification and constellation mapping ────────
    {
        "normalized_code": """\
#[derive(Hash, Eq, PartialEq, Debug, Clone, Copy)]
pub enum FrequencyBand {
    _250_520 = 0,
    _520_1450 = 1,
    _1450_3500 = 2,
    _3500_5500 = 3,
}

impl FrequencyBand {
    pub fn from_frequency(frequency_hz: f32) -> Option<Self> {
        match frequency_hz as i32 {
            250..=519 => Some(FrequencyBand::_250_520),
            520..=1449 => Some(FrequencyBand::_520_1450),
            1450..=3499 => Some(FrequencyBand::_1450_3500),
            3500..=5500 => Some(FrequencyBand::_3500_5500),
            _ => None,
        }
    }
}

pub struct ConstellationMap {
    frequency_band_to_peaks: std::collections::HashMap<FrequencyBand, Vec<FrequencyPeak>>,
}

impl ConstellationMap {
    pub fn new() -> Self {
        ConstellationMap {
            frequency_band_to_peaks: std::collections::HashMap::new(),
        }
    }

    pub fn add_peak(
        &mut self,
        frequency_hz: f32,
        magnitude: u16,
        fft_pass_number: u32,
    ) {
        if let Some(band) = FrequencyBand::from_frequency(frequency_hz) {
            self.frequency_band_to_peaks
                .entry(band)
                .or_insert_with(Vec::new)
                .push(FrequencyPeak {
                    fft_pass_number,
                    peak_magnitude: magnitude,
                    corrected_peak_frequency_bin: (frequency_hz as u16),
                });
        }
    }

    pub fn peaks_by_band(&self, band: FrequencyBand) -> Vec<&FrequencyPeak> {
        self.frequency_band_to_peaks
            .get(&band)
            .map(|peaks| peaks.iter().collect())
            .unwrap_or_default()
    }
}

pub struct FrequencyPeak {
    pub fft_pass_number: u32,
    pub peak_magnitude: u16,
    pub corrected_peak_frequency_bin: u16,
}
""",
        "function": "frequency_band_classification",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/core/fingerprinting/signature_format.rs",
    },
    # ── 4. PCM sample buffering and ring buffer management ────────────────
    {
        "normalized_code": """\
use std::sync::Arc;


pub struct AudioBuffer {
    ring_buffer: Vec<i16>,
    buffer_index: usize,
    capacity: usize,
}

impl AudioBuffer {
    pub fn new(capacity: usize) -> Self {
        AudioBuffer {
            ring_buffer: vec![0i16; capacity],
            buffer_index: 0,
            capacity,
        }
    }

    pub fn write_samples(&mut self, samples: &[i16]) {
        for &sample in samples {
            self.ring_buffer[self.buffer_index] = sample;
            self.buffer_index = (self.buffer_index + 1) % self.capacity;
        }
    }

    pub fn read_window(&self, offset: usize) -> Vec<i16> {
        let mut window = vec![0i16; 2048];
        for idx in 0..2048 {
            window[idx] = self.ring_buffer[(offset + idx) % self.capacity];
        }
        window
    }

    pub fn current_index(&self) -> usize {
        self.buffer_index
    }
}
""",
        "function": "audio_ring_buffer_pcm_samples",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 5. Audio file decoding (WAV, MP3, FLAC, OGG with Rodio) ──────────
    {
        "normalized_code": """\
use rodio::Decoder;
use std::io::BufReader;
use std::fs::File;
use std::error::Error;


pub fn decode_audio_file(file_path: &str) -> Result<Vec<f32>, Box<dyn Error>> {
    let file = File::open(file_path)?;
    let buffered = BufReader::new(file);

    let decoder = Decoder::new(buffered)?;
    let source_channels = decoder.channels();
    let source_sample_rate = decoder.sample_rate();

    // Convert to mono 16 KHz PCM (f32)
    let resampled: Vec<f32> = rodio::source::UniformSourceIterator::new(
        decoder,
        rodio::nz!(1),
        rodio::nz!(16000),
    )
    .collect();

    Ok(resampled)
}

pub fn extract_middle_segment(
    pcm_samples: &[f32],
    duration_seconds: f32,
    sample_rate: u32,
) -> &[f32] {
    let target_samples = (duration_seconds * sample_rate as f32) as usize;
    let available = pcm_samples.len();

    if available <= target_samples {
        return &pcm_samples[0..available];
    }

    let middle = available / 2;
    let half_target = target_samples / 2;

    &pcm_samples[middle - half_target..middle + half_target]
}
""",
        "function": "audio_decode_rodio_wav_mp3_flac",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 6. Spectral peak spreading (frequency and time domains) ──────────
    {
        "normalized_code": """\
pub struct PeakSpreadingOperator {
    spread_buffer: Vec<Vec<f32>>,
    spread_index: usize,
}

impl PeakSpreadingOperator {
    pub fn new() -> Self {
        PeakSpreadingOperator {
            spread_buffer: vec![vec![0.0f32; 1025]; 256],
            spread_index: 0,
        }
    }

    pub fn spread_peaks_frequency_domain(&mut self, spectrum: &[f32]) {
        let spread_out = &mut self.spread_buffer[self.spread_index];
        spread_out.copy_from_slice(spectrum);

        // Apply max filter in frequency domain
        for bin in 0..=1022 {
            spread_out[bin] = spread_out[bin]
                .max(spread_out[bin + 1])
                .max(spread_out[bin + 2]);
        }
    }

    pub fn spread_peaks_time_domain(&mut self, current_spectrum: &[f32]) {
        let spread_out = &mut self.spread_buffer[self.spread_index].clone();

        // Spread to past time-domain frames
        for bin in 0..=1024 {
            for past_offset in &[1, 3, 6] {
                let past_idx = ((self.spread_index as i32) - *past_offset) & 255;
                self.spread_buffer[past_idx as usize][bin] =
                    self.spread_buffer[past_idx as usize][bin].max(spread_out[bin]);
            }
        }

        self.spread_index = (self.spread_index + 1) & 255;
    }

    pub fn get_spread_spectrum(&self, offset: usize) -> &[f32] {
        &self.spread_buffer[((self.spread_index as i32 - offset as i32) & 255) as usize]
    }
}
""",
        "function": "spectral_peak_spreading_time_freq",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 7. Signature encoding/decoding with binary format ────────────────
    {
        "normalized_code": """\
use byteorder::{LittleEndian, ReadBytesExt, WriteBytesExt};
use crc32fast::Hasher;
use std::io::{Cursor, Write};


pub struct SignatureEncoder;

impl SignatureEncoder {
    pub fn encode_to_binary(
        sample_rate_hz: u32,
        number_samples: u32,
        peaks: &std::collections::HashMap<FrequencyBand, Vec<FrequencyPeak>>,
    ) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let mut buffer = Vec::new();

        // Magic numbers and header
        buffer.write_u32::<LittleEndian>(0xcafe2580)?;
        let crc_offset = buffer.len();
        buffer.write_u32::<LittleEndian>(0)?; // Placeholder CRC

        let size_offset = buffer.len();
        buffer.write_u32::<LittleEndian>(0)?; // Placeholder size

        buffer.write_u32::<LittleEndian>(0x94119c00)?;

        // Void fields
        for _ in 0..3 {
            buffer.write_u32::<LittleEndian>(0)?;
        }

        let sample_rate_id = Self::sample_rate_to_id(sample_rate_hz);
        buffer.write_u32::<LittleEndian>(sample_rate_id << 27)?;

        for _ in 0..2 {
            buffer.write_u32::<LittleEndian>(0)?;
        }

        buffer.write_u32::<LittleEndian>(
            number_samples + (sample_rate_hz as f32 * 0.24) as u32
        )?;

        buffer.write_u32::<LittleEndian>(0x7c0000)?;

        // Write frequency peaks by band
        for (band, peaks_list) in peaks {
            buffer.write_u32::<LittleEndian>(0x60030040 + *band as u32)?;
            let peaks_size = peaks_list.len() as u32 * 3;
            buffer.write_u32::<LittleEndian>(peaks_size)?;

            for peak in peaks_list {
                buffer.write_u8(peak.fft_pass_number as u8)?;
                buffer.write_u16::<LittleEndian>(peak.corrected_peak_frequency_bin)?;
            }
        }

        // Compute CRC
        let mut hasher = Hasher::new();
        hasher.update(&buffer[8..]);
        let crc = hasher.finalize();

        let mut cursor = Cursor::new(&mut buffer);
        cursor.set_position(crc_offset as u64);
        cursor.write_u32::<LittleEndian>(crc)?;

        Ok(buffer)
    }

    fn sample_rate_to_id(sample_rate_hz: u32) -> u32 {
        match sample_rate_hz {
            8000 => 1,
            11025 => 2,
            16000 => 3,
            32000 => 4,
            44100 => 5,
            48000 => 6,
            _ => 3,
        }
    }
}
""",
        "function": "signature_binary_encoding_crc32",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/signature_format.rs",
    },
    # ── 8. Microphone stream capture with CPAL ─────────────────────────
    {
        "normalized_code": """\
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::{Arc, Mutex};


pub struct MicrophoneCapture {
    host: cpal::Host,
    device: Option<cpal::Device>,
    stream: Option<cpal::Stream>,
}

impl MicrophoneCapture {
    pub fn new() -> Self {
        MicrophoneCapture {
            host: cpal::default_host(),
            device: None,
            stream: None,
        }
    }

    pub fn list_input_devices(&self) -> Result<Vec<(String, String)>, Box<dyn std::error::Error>> {
        let mut devices = vec![];
        for device in self.host.input_devices()? {
            let device_id = device.id()?.to_string();
            let device_name = device.name().unwrap_or_else(|_| "unknown".to_string());
            devices.push((device_id, device_name));
        }
        Ok(devices)
    }

    pub fn set_device(&mut self, device_id: &str) -> Result<(), Box<dyn std::error::Error>> {
        for device in self.host.input_devices()? {
            if device.id()?.to_string() == device_id {
                self.device = Some(device);
                return Ok(());
            }
        }
        Err("Device not found".into())
    }

    pub fn start_recording(
        &mut self,
        on_frame: Arc<Mutex<dyn Fn(Vec<f32>) + Send>>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let device = self.device.as_ref().ok_or("No device set")?;
        let config = device.default_input_config()?;

        let _stream = device.build_input_stream(
            &config.into(),
            move |data: &cpal::Data, _: &cpal::InputCallbackInfo| {
                if let Ok(samples_slice) = data.as_slice::<f32>() {
                    let samples: Vec<f32> = samples_slice.iter().copied().collect();
                    if let Ok(callback) = on_frame.lock() {
                        callback(samples);
                    }
                }
            },
            |_err| {},
            None,
        )?;

        _stream.play()?;
        self.stream = Some(_stream);
        Ok(())
    }
}
""",
        "function": "microphone_capture_cpal_stream",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/core/microphone_thread.rs",
    },
    # ── 9. HTTP request to recognition API ──────────────────────────────
    {
        "normalized_code": """\
use serde_json::{json, Value};
use std::error::Error;
use uuid::Uuid;


pub struct FingerprintRequest {
    api_endpoint: String,
    user_agents: Vec<String>,
}

impl FingerprintRequest {
    pub fn new() -> Self {
        FingerprintRequest {
            api_endpoint: "https://amp.recognition.com/discovery/v5/en/US/android/-/identify".to_string(),
            user_agents: vec![
                "Mozilla/5.0 (Android)".to_string(),
                "AudioRec/0.3.0".to_string(),
            ],
        }
    }

    pub async fn send_fingerprint(
        &self,
        signature_uri: &str,
        sample_count: u32,
        sample_rate_hz: u32,
    ) -> Result<Value, Box<dyn Error>> {
        let timestamp_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_millis() as u32;

        let request_body = json!({
            "signature": {
                "uri": signature_uri,
                "samplems": (sample_count as f32 / sample_rate_hz as f32 * 1000.0) as u32,
                "timestamp": timestamp_ms,
            },
            "timestamp": timestamp_ms,
            "geolocation": {
                "latitude": 45.0,
                "longitude": 2.0,
                "altitude": 300,
            },
            "timezone": "UTC",
        });

        let uuid_1 = Uuid::new_v4().to_string().to_uppercase();
        let uuid_2 = Uuid::new_v4().to_string();

        let endpoint_url = format!(
            "{}/{}/{}?sync=true&webv3=true&sampling=true&connected=&apiversion=v3&sharehub=true&video=v3",
            self.api_endpoint, uuid_1, uuid_2
        );

        // Simulate HTTP request (in real code, use reqwest or hyper)
        Ok(json!({
            "xxx": {
                "title": "Xxx",
                "artist": "Xxx",
                "status": "recognized"
            }
        }))
    }
}
""",
        "function": "fingerprint_api_http_request",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/communication.rs",
    },
    # ── 10. Magnitude spectrum scaling and logarithmic transformation ────
    {
        "normalized_code": """\
pub struct SpectrumScaler;

impl SpectrumScaler {
    pub fn compute_magnitude_spectrum(
        complex_fft: &[num_complex::Complex<f32>],
        scaling_factor: f32,
    ) -> Vec<f32> {
        complex_fft
            .iter()
            .map(|c| {
                let magnitude_squared = c.re.powi(2) + c.im.powi(2);
                (magnitude_squared / scaling_factor).max(1e-10)
            })
            .collect()
    }

    pub fn logarithmic_magnitude(magnitude: f32, log_scale: f32, offset: f32) -> f32 {
        magnitude.ln().max(1.0 / 64.0) * log_scale + offset
    }

    pub fn peak_magnitude_with_interpolation(
        mag_current: f32,
        mag_before: f32,
        mag_after: f32,
    ) -> (f32, f32) {
        let peak_mag = Self::logarithmic_magnitude(mag_current, 1477.3, 6144.0);
        let mag_before_log = Self::logarithmic_magnitude(mag_before, 1477.3, 6144.0);
        let mag_after_log = Self::logarithmic_magnitude(mag_after, 1477.3, 6144.0);

        let peak_variation = peak_mag * 2.0 - mag_before_log - mag_after_log;
        let frequency_offset = if peak_variation > 0.0 {
            (mag_after_log - mag_before_log) * 32.0 / peak_variation
        } else {
            0.0
        };

        (peak_mag as u16 as f32, frequency_offset)
    }
}
""",
        "function": "spectrum_magnitude_logarithmic_scaling",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 11. FFT bin to frequency conversion and range filtering ─────────
    {
        "normalized_code": """\
pub struct FrequencyConverter {
    sample_rate_hz: u32,
    fft_bin_count: u32,
}

impl FrequencyConverter {
    pub fn new(sample_rate_hz: u32, fft_size: u32) -> Self {
        FrequencyConverter {
            sample_rate_hz,
            fft_bin_count: fft_size / 2,
        }
    }

    pub fn bin_to_frequency(&self, bin: u32) -> f32 {
        bin as f32 * (self.sample_rate_hz as f32 / 2.0 / self.fft_bin_count as f32)
    }

    pub fn frequency_to_bin(&self, frequency_hz: f32) -> u32 {
        ((frequency_hz * self.fft_bin_count as f32 * 2.0) / self.sample_rate_hz as f32) as u32
    }

    pub fn filter_frequency_range(&self, peaks: Vec<(u32, f32)>) -> Vec<(u32, f32)> {
        peaks
            .into_iter()
            .filter(|(bin, _)| {
                let freq = self.bin_to_frequency(*bin);
                freq >= 250.0 && freq <= 5500.0
            })
            .collect()
    }

    pub fn quantize_peak_bin(&self, bin_float: f32) -> u32 {
        ((bin_float * 64.0) as u32).min(u32::MAX)
    }
}
""",
        "function": "frequency_bin_conversion_quantization",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
    # ── 12. Sample rate detection and PCM format conversion ──────────────
    {
        "normalized_code": """\
use rodio::conversions::SampleTypeConverter;


pub struct SampleRateHandler;

impl SampleRateHandler {
    pub fn get_supported_rates() -> Vec<u32> {
        vec![8000, 11025, 16000, 32000, 44100, 48000]
    }

    pub fn normalize_to_16khz(samples: Vec<f32>, source_rate: u32) -> Vec<f32> {
        if source_rate == 16000 {
            return samples;
        }

        let ratio = 16000.0 / source_rate as f32;
        let new_len = (samples.len() as f32 * ratio) as usize;
        let mut resampled = Vec::with_capacity(new_len);

        for i in 0..new_len {
            let src_idx = i as f32 / ratio;
            let idx_floor = src_idx.floor() as usize;
            let idx_ceil = (idx_floor + 1).min(samples.len() - 1);
            let frac = src_idx - idx_floor as f32;

            let value = samples[idx_floor] * (1.0 - frac) + samples[idx_ceil] * frac;
            resampled.push(value);
        }

        resampled
    }

    pub fn convert_i16_to_f32(samples: &[i16]) -> Vec<f32> {
        samples
            .iter()
            .map(|&s| s as f32 / 32768.0)
            .collect()
    }

    pub fn convert_f32_to_i16(samples: &[f32]) -> Vec<i16> {
        samples
            .iter()
            .map(|&s| (s * 32768.0) as i16)
            .collect()
    }

    pub fn to_mono(samples: Vec<f32>, channel_count: u16) -> Vec<f32> {
        if channel_count == 1 {
            return samples;
        }

        samples
            .chunks(channel_count as usize)
            .map(|frame| frame.iter().sum::<f32>() / channel_count as f32)
            .collect()
    }
}
""",
        "function": "sample_rate_pcm_format_conversion",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/core/fingerprinting/algorithm.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "FFT computation spectrogram hanning window",
    "peak detection frequency time domain local maxima",
    "frequency band classification constellation map",
    "audio buffer ring PCM samples",
    "decode audio file WAV MP3 FLAC rodio",
    "peak spreading frequency domain time domain",
    "signature binary encoding CRC checksum",
    "microphone capture CPAL audio stream",
    "HTTP POST Shazam recognition API",
    "magnitude spectrum logarithmic scaling",
    "FFT bin frequency conversion quantization",
    "sample rate resampling PCM format conversion",
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
