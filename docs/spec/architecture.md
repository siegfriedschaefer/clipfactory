# Architecture

## High-Level Pipeline

```text
                    ┌──────────────────────────┐
                    │      Frontend / UI       │
                    │  Vite + React · Port 3000│
                    │  Upload, Ranking, Export │
                    └────────────┬─────────────┘
                                 │ HTTP (nginx proxy)
                                 ▼
                    ┌──────────────────────────┐
                    │    API / Orchestrator    │
                    │  FastAPI · Port 8000     │
                    │  /health  /ready         │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
   ┌──────────────────┐ ┌────────────────┐ ┌────────────────┐
   │   worker_cpu     │ │     Redis      │ │   PostgreSQL   │
   │   ffmpeg         │ │   Job Queue    │ │   Metadata     │
   │   shot detect    │ │   Port 6379    │ │   Port 5432    │
   │   chunk split    │ └────────────────┘ └────────────────┘
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │   worker_gpu     │
   │   Moonshine ASR  │
   │   per-chunk ASR  │
   │   ts-stitching   │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Semantic Segmentation      │
   │   Pauses, rhetorical markers │
   │   shot-aligned boundaries    │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Candidate Generator        │
   │   30–100 clip candidates     │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Feature Extraction         │
   │   text (11) / audio (6) /    │
   │   video (5) features         │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Scoring Engine             │
   │   hook / retention / share   │
   │   packaging / risk           │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Meta Ranker                │
   │   Weighted sum → viral_score │
   │   Top-10 + reason tags       │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Packaging Engine           │
   │   9:16 crop (face-based)     │
   │   SRT subtitles, 1080×1920   │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │   Export + Feedback Store    │
   │   clip_variants, clip_score  │
   │   clip_feedback              │
   └──────────────────────────────┘
```

---

## Services & Containers

| Service | Image | Port | Purpose |
| --- | --- | --- | --- |
| `frontend` | `Dockerfile.frontend` | 3000 | Vite/React SPA served by nginx; proxies `/videos` to api |
| `api` | `Dockerfile.api` | 8000 | FastAPI app + Alembic migrations on startup |
| `worker_cpu` | `Dockerfile.worker_cpu` | — | ffmpeg ingestion, shot detection, 15-min audio chunk splitting |
| `worker_gpu` | `Dockerfile.worker_gpu` | — | Moonshine ASR (per chunk), timestamp stitching, segmentation, features, scoring |
| `postgres` | `postgres:16-alpine` | 5432 | Primary database |
| `redis` | `redis:7-alpine` | 6379 | Job queue |

All services share a `.env` file. `api`, `worker_cpu`, and `worker_gpu` depend on postgres and redis being healthy before starting.

**Shared volume:** `./storage` mounted at `/storage` in all three app containers.

```text
storage/
├── videos/{video_id}/
│   ├── normalized.mp4          # re-encoded source (always present)
│   ├── audio.wav               # 16kHz mono WAV — only for videos ≤ 15 min
│   ├── audio_chunks/           # only for videos > 15 min
│   │   ├── chunk_000.wav       # first 15-min slice, 16kHz mono
│   │   ├── chunk_001.wav       # second slice, etc.
│   │   └── …
│   └── keyframes/              # one JPG per shot
├── exports/{video_id}/         # 9:16 MP4 + SRT per exported clip
└── previews/{video_id}/        # 480×854 low-res preview MP4s
```

**Chunked ingestion:** Videos longer than 15 minutes are split into 15-minute audio chunks (`CHUNK_DURATION = 900 s`) after normalization. The GPU worker detects the `audio_chunks/` directory, transcribes each chunk with Moonshine, offsets every segment's `start_time` / `end_time` by `chunk_index × CHUNK_DURATION`, then writes all segments to `transcript_segments` as if the video were continuous. The `normalized.mp4` is never split — ffmpeg trims the source during export using absolute timestamps.

**ASR engine:** [Moonshine](https://github.com/usefulsensors/moonshine) (`moonshine-voice`).
Runs on CPU by default; the GPU worker Dockerfile contains commented instructions to switch to a CUDA base image if a GPU is available.

**Worker retry policy:** Both workers retry failed jobs up to 3 times before marking the job as `failed`. Retry count is stored in `jobs.retry_count`.

---

## Data Model

### `videos`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `filename` | String(512) | |
| `original_path` | String(1024) | path under `/storage/videos` |
| `duration_seconds` | Float | nullable |
| `resolution` | String(32) | e.g. `1920x1080` |
| `fps` | Float | nullable |
| `status` | String(64) | default `uploaded` |
| `created_at` | DateTime TZ | |

### `jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | indexed, cascade delete |
| `status` | Enum | see below |
| `error_message` | Text | nullable |
| `retry_count` | Integer | default 0; incremented on each retry |
| `created_at` | DateTime TZ | |
| `updated_at` | DateTime TZ | auto-updated |

**Job status flow:**

```text
uploaded → ingesting → ready_for_asr → transcribing → transcribed
                                                     ↘
                                                       failed
```

### `transcript_segments`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | indexed, cascade delete |
| `job_id` | UUID FK→jobs | indexed, cascade delete |
| `segment_index` | Integer | ordering |
| `start_time` | Float | seconds |
| `end_time` | Float | seconds |
| `text` | Text | transcribed words |
| `words` | JSONB | word-level timing (None — not available in Moonshine non-streaming mode) |
| `created_at` | DateTime TZ | |

### `shots`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | cascade delete |
| `shot_index` | Integer | |
| `start_time` / `end_time` | Float | seconds |
| `start_frame` / `end_frame` | Integer | |
| `keyframe_path` | String | nullable |

### `semantic_segments`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | cascade delete |
| `segment_index` | Integer | |
| `start_time` / `end_time` | Float | |
| `trigger_type` | String(64) | pause \| topic_shift \| rhetorical \| shot_aligned |
| `transcript_preview` | Text | nullable |

### `clip_candidates`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `video_id` | UUID FK→videos | cascade delete |
| `candidate_index` | Integer | |
| `start_time` / `end_time` / `duration` | Float | |
| `candidate_type` | String(64) | hook_to_payoff \| quick_lesson \| … |
| `trigger_marker` | String(64) | nullable |
| `transcript_preview` | Text | nullable |
| `status` | String(32) | active \| dismissed |

### `clip_features`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `candidate_id` | UUID FK→clip_candidates | cascade delete |
| `feature_type` | String(16) | text \| audio \| video |
| `feature_key` | String(64) | e.g. hook_strength |
| `feature_value` | Float | normalised to [0, 1] except duration |
| `computed_at` | DateTime TZ | |

### `clip_scores`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `candidate_id` | UUID FK→clip_candidates | unique, cascade delete |
| `hook_score` | Float | [0, 1] |
| `retention_score` | Float | [0, 1] |
| `share_score` | Float | [0, 1] |
| `packaging_score` | Float | [0, 1] |
| `risk_score` | Float | [0, 1] higher = riskier |
| `viral_score` | Float | weighted meta-score |
| `rank` | Integer | nullable; 1 = best |
| `reasons` | JSONB | list of 3–5 human-readable tags |
| `computed_at` | DateTime TZ | |

### `clip_variants`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `candidate_id` | UUID FK→clip_candidates | cascade delete |
| `variant_type` | String(16) | export \| preview |
| `file_path` | String(1024) | |
| `resolution` | String(32) | e.g. 1080x1920 |
| `title_suggestions` | JSONB | nullable |
| `overlay_text` | Text | nullable |
| `subtitle_path` | String(1024) | nullable |
| `created_at` | DateTime TZ | |

### `clip_feedback`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `candidate_id` | UUID FK→clip_candidates | cascade delete |
| `video_id` | UUID FK→videos | cascade delete |
| `action` | String(16) | positive \| negative \| exported |
| `created_at` | DateTime TZ | |

---

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (DB check) |
| POST | `/videos` | Upload video, start pipeline |
| GET | `/videos` | List all videos |
| DELETE | `/videos/{id}` | Delete video + all artefacts |
| GET | `/videos/{id}/status` | Current job status |
| GET | `/videos/{id}/transcript` | All transcript segments |
| GET | `/videos/{id}/candidates` | All clip candidates |
| GET | `/videos/{id}/ranked-clips` | Top-10 ranked clips with scores + reasons |
| POST | `/videos/{id}/candidates/{cid}/export` | Render 9:16 MP4 export |
| GET | `/videos/{id}/exports` | List all exports for a video |
| POST | `/videos/{id}/candidates/{cid}/feedback` | Submit positive/negative/exported feedback |

---

## AI Components

### Schemas (`ai/schemas/`)

| File | Fields |
| --- | --- |
| `clip_candidate.json` | `clip_id`, `start`, `end`, `type`, `features` |
| `clip_score.json` | `clip_id`, `hook_score`, `retention_score`, `share_score`, `viral_score`, `reasons` |
| `video_metadata.json` | stub |

---

## Implementation Status

| Component | Status |
| --- | --- |
| Docker Compose stack (6 services) | Done |
| PostgreSQL schema + Alembic migrations | Done |
| FastAPI + health/ready endpoints | Done |
| CPU worker — ffmpeg ingestion + shot detection | Done |
| CPU worker — 15-min audio chunk splitting | Planned |
| GPU worker — Moonshine ASR | Done |
| GPU worker — per-chunk ASR + timestamp stitching | Planned |
| Redis job queue + retry logic (3 attempts) | Done |
| Semantic segmentation | Done |
| Candidate generator | Done |
| Text / audio / video feature extraction | Done |
| Specialist scoring (5 scores) | Done |
| Meta ranker — weighted sum + viral_score | Done |
| Score explanations — reason tags | Done |
| Ranking endpoint (Top-10) | Done |
| Packaging engine — 9:16 crop + SRT | Done |
| Export endpoint + clip_variants | Done |
| Preview generation (480×854) | Done |
| Feedback endpoint + clip_feedback | Done |
| Vite + React frontend (5 views) | Done |
| Structured JSON logging (all services) | Done |
