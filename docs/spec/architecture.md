
# Architecture - High level

                    ┌──────────────────────────┐
                    │      Frontend / UI       │
                    │  Upload, Timeline, Rank  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │      API / Orchestrator  │
                    │ FastAPI + Job Controller │
                    └────────────┬─────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌────────────────┐     ┌──────────────────┐    ┌──────────────────┐
│ Ingestion      │     │ Processing Queue │    │ Metadata Store   │
│ ffmpeg, OCR,   │     │ Redis / Jobs     │    │ PostgreSQL       │
│ shot detect    │     └──────────────────┘    └──────────────────┘
└───────┬────────┘
        │
        ▼
┌───────────────────────────────┐
│ ASR + Alignment Layer         │
│ WhisperX                      │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Semantic Segmentation         │
│ Topic shifts, rhetorical cuts │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Candidate Generator           │
│ 50–150 Clip-Kandidaten        │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Feature Extraction Layer      │
│ text/audio/video/channel      │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Scoring Engine                │
│ hook/retention/share/etc.     │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Meta Ranker                   │
│ XGBoost / LightGBM            │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Packaging Engine              │
│ subtitles, titles, overlays   │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Export + Feedback Store       │
│ publish metrics, retraining   │
└───────────────────────────────┘

