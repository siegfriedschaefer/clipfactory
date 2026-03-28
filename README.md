# ClipFactory

Lokales MVP für die Analyse von Longform-Videos, die Erzeugung von Clip-Kandidaten, das Ranking nach Viralitätssignalen und den Export von Shorts.

## Enthalten
- FastAPI API
- CPU/GPU Worker-Skeleton
- PostgreSQL + Redis via Docker Compose
- SQLAlchemy Datenmodell
- Pipeline-Services als Python-Module
- JSON Schemas für Clip Candidates und Scores
- Starter-Prompts

## Schnellstart
```bash
cp .env.example .env
docker compose up --build
```

API danach unter `http://localhost:8000/docs`.

## Pipeline
1. Upload
2. Ingestion
3. ASR
4. Segmentierung
5. Candidate Generation
6. Feature Extraction
7. Scoring
8. Packaging
9. Feedback / Learning

## Nächste Schritte
- WhisperX im GPU Worker integrieren
- echte ffmpeg-Pipeline ergänzen
- Shot Detection und Ranking verfeinern
- Frontend anschließen
