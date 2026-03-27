Ziel nach 4 Wochen

Am Ende soll dein System lokal können:

Video hochladen
Audio extrahieren und transkribieren
Szenen/Segmente erkennen
30–100 Clip-Kandidaten generieren
Kandidaten mit Scores bewerten
Top 10 anzeigen
Untertitel + einfache Titelvarianten erzeugen
Clips als 9:16 exportieren

Nicht Ziel in 4 Wochen:

perfektes Viralitätsmodell
vollautomatisches Learning
Multi-User-Plattform
Publish-Integration
komplexe Agentik
Gesamtstrategie

Die Reihenfolge ist entscheidend:

erst die Pipeline lauffähig machen
dann Kandidaten erzeugen
dann Ranking einbauen
dann Packaging und UI
erst ganz am Schluss optimieren

Sonst verlierst du Zeit in Modellideen, bevor das System überhaupt End-to-End läuft.

Woche 1 — Fundament und End-to-End-Basis
Ziel der Woche

Eine minimale Pipeline, die lokal ein Video annimmt, normalisiert, transkribiert und Artefakte speichert.

Deliverables

Am Ende der Woche hast du:

lokales Repo-Grundgerüst
Docker Compose
FastAPI-Basis
Postgres + Redis
lokales File Storage
Video Upload
ffmpeg-Normalisierung
WhisperX-Transkription
Status-Tracking für Jobs
Aufgaben
1. Projektstruktur anlegen

Baue das Repo so auf:

project/
  apps/
    api/
    worker_cpu/
    worker_gpu/
    frontend/
  services/
    ingestion/
    asr/
    storage/
    jobs/
  infra/
    docker/
  storage/
  scripts/
  tests/
2. Infrastruktur lokal hochziehen

Mit Docker Compose:

postgres
redis
api
worker_cpu
worker_gpu

Noch kein Frontend nötig, notfalls Swagger + einfache HTML-Seite.

3. Datenmodell minimal anlegen

Starte nur mit diesen Tabellen:

videos
jobs
transcript_segments
4. Upload + Storage

Implementiere:

Upload-Endpoint
lokale Ablage unter /storage/videos/{video_id}/
Metadatensatz in DB
5. Ingestion-Service

CPU-Worker soll:

Video validieren
mit ffmpeg normalisieren
Audio extrahieren
Dauer, Auflösung, FPS speichern
6. ASR-Service

GPU-Worker soll:

WhisperX aufrufen
Segmente + Wort-Timestamps speichern
JSON-Artefakte ablegen
DB aktualisieren
7. Job-State-Maschine

Definiere klare Stati:

uploaded
ingesting
ready_for_asr
transcribing
transcribed
failed
Ende Woche 1: Akzeptanzkriterien

Du bist fertig, wenn du lokal sagen kannst:

Ich lade ein Video hoch
Ich starte Analyse
Das System transkribiert es
Ich kann Transkriptsegmente per API abrufen
Technischer Fokus

In Woche 1 keine Optimierung, keine Diarization, keine Scores.

Nur:

Robustheit
Speicherstruktur
reproduzierbare Pipeline
Woche 2 — Segmentierung und Candidate Generation
Ziel der Woche

Aus dem Transkript und der Videostruktur automatisch sinnvolle Clip-Kandidaten erzeugen.

Deliverables

Am Ende der Woche hast du:

Shot Detection
semantische Segmentierung
Candidate Generator
Kandidaten in DB
erste API für Kandidatenliste
Aufgaben
1. Shot Detection integrieren

CPU-seitig:

PySceneDetect oder vergleichbar
Shot Boundaries speichern
optional Keyframes extrahieren

Neue Tabelle:

shots
2. Semantische Segmentierung bauen

Baue zunächst heuristisch + embedding-basiert, nicht zu kompliziert.

Einfache Regeln:

Segmentgrenzen bei Themenwechsel
Segmentgrenzen bei Pausen
Segmentgrenzen bei starken rhetorischen Triggern
Segmentgrenzen nahe Shot-Wechseln bevorzugen

Neue Tabelle:

semantic_segments
3. Rhetorische Marker definieren

Erstelle eine erste Bibliothek von Mustern:

Problem-Einstieg
„die meisten machen Fehler“
Kontrast
Zahl/Statistik
Warnung
Kontroverse
„niemand spricht darüber“
payoff/Ergebnis

Das darf am Anfang regelbasiert sein.

4. Candidate Generator bauen

Generiere pro Video 30–100 Kandidaten.

Candidate-Typen:

hook → payoff
claim → explanation
mistake → fix
quick lesson
contrarian snippet

Regeln:

15–60 Sekunden
kein harter Satzanfang mitten im Wort
Hook möglichst am Anfang
Ende nicht offen abbrechen

Neue Tabelle:

clip_candidates
5. Preview-Endpoint bauen

API:

GET /videos/{id}/candidates

Antwort:

Start/Ende
Länge
Candidate-Typ
kurzer Text-Preview
Ende Woche 2: Akzeptanzkriterien

Du bist fertig, wenn du lokal sagen kannst:

Das System hat zu einem Video 30–100 Kandidaten erzeugt
Jeder Kandidat hat Start/Ende
Ich kann diese Kandidaten per API ansehen
Die Kandidaten sind nicht komplett zufällig, sondern grob sinnvoll
Technischer Fokus

In Woche 2 zählt:

brauchbare Kandidatenmenge
keine Perfektion
kein Deep Learning Overkill
Woche 3 — Feature Extraction, Scoring und Ranking
Ziel der Woche

Das System soll Kandidaten bewerten und die besten Clips priorisieren.

Deliverables

Am Ende der Woche hast du:

Feature Extraction Layer
erste Specialist Scores
Meta-Ranking
Top-10 Auswahl
erste Erklärbarkeit
Aufgaben
1. Text-Features implementieren

Für jeden Kandidaten berechnen:

Hook Strength
Curiosity Gap
Number Density
Clarity
Information Density
Novelty Proxy
Controversy Proxy
Actionability
Niche Keywords
Länge
Hook-in-ersten-3-Sekunden ja/nein

Neue Tabelle:

clip_features
2. Audio-Features implementieren

Zum Beispiel:

Lautheit
Lautheitsdynamik
Pausenanteil
Sprechtempo
Energie am Anfang
Füllwortdichte, falls sinnvoll
3. Video-Features implementieren

Einfach starten:

Anzahl Shot-Wechsel
Gesicht sichtbar ja/nein
Cropbarkeit 9:16 grob
OCR/Text im Bild ja/nein
visuelle Dynamik grob
4. Erste Specialist Scores definieren

Noch keine komplexen Modelle nötig. Erst einmal hybride Logik:

hook_score
retention_score
share_score
packaging_score
risk_score

Erst heuristisch oder leichtgewichtig.

5. Meta-Ranker bauen

Nimm zunächst einen simplen Ansatz:

gewichtete Summe
oder kleines XGBoost-Modell mit synthetischen / heuristischen Labels

Wichtiger ist hier:

Reihenfolge wird brauchbar
Ergebnis ist nachvollziehbar
6. Score-Erklärung einbauen

Zu jedem Clip 3–5 Gründe erzeugen, etwa:

starker Einstieg
hohe Informationsdichte
gute Cropbarkeit
kontroverse Aussage
kurze klare Struktur

Diese Erklärungen dürfen anfangs regelbasiert sein.

7. Ranking-Endpoint

API:

GET /videos/{id}/ranked-clips

Antwort:

Top Clips
Scores
Gründe
Titelvorschläge v0
Ende Woche 3: Akzeptanzkriterien

Du bist fertig, wenn du lokal sagen kannst:

Das System rankt die Kandidaten
Ich bekomme eine Top-10
Ich sehe zu jedem Clip, warum er oben steht
Die Top-Ergebnisse wirken besser als Zufall
Technischer Fokus

Woche 3 ist der eigentliche Produktkern.

Hier entsteht dein Differenzierungsmerkmal:
nicht nur schneiden, sondern bewerten.

Woche 4 — Packaging, UI und Export
Ziel der Woche

Aus den Top-Kandidaten veröffentlichbare Short-Clips machen.

Deliverables

Am Ende der Woche hast du:

einfache Web-Oberfläche
Top-10 Ansicht
Clip-Detailansicht
Subtitle-Rendering
9:16 Export
Titel-/Overlay-Varianten
nutzbares lokales MVP
Aufgaben
1. Minimales Frontend bauen

Ein schlichtes Next.js- oder React-Frontend reicht.

Views:

Upload-Seite
Video-Status
Kandidatenliste
Ranking-Ansicht
Clip-Detailansicht mit Preview
2. Packaging Engine v1

Für Top-Clips:

Auto-Crop auf 9:16
Untertitel einbrennen
wichtige Wörter hervorheben
optional Hook-Overlay-Text
Titelvarianten erzeugen

Noch simpel halten.

3. Export-Service

Pro Clip:

MP4 in 9:16
Titelvorschläge als JSON
Overlay-Text
Subtitle-Datei optional

Neue Tabelle:

clip_variants
4. Clip-Preview

Erzeuge für Top-Kandidaten niedriger aufgelöste Preview-Dateien, damit die UI schnell bleibt.

5. User-Feedback minimal

Füge Buttons hinzu:

„gut“
„schlecht“
„exportieren“

Das reicht fürs Erste.

Neue Tabelle:

clip_feedback
6. Stabilisierung

Ganz bewusst 2–3 Tage für:

Bugfixing
Speicherbereinigung
Job-Retry
Logging
Fehlerfälle
GPU-Lock-Probleme
Timeouts
Ende Woche 4: Akzeptanzkriterien

Du bist fertig, wenn du lokal sagen kannst:

Ich lade ein Video hoch
Das System analysiert es vollständig
Ich sehe die Top-Clips in einer UI
Ich exportiere 9:16 Shorts mit Untertiteln
Ich kann erste echte Tests mit eigenen Videos machen

Dann hast du ein echtes MVP.

Wochenübersicht in komprimierter Form
Woche 1

Infrastruktur, Upload, Ingestion, ASR

Woche 2

Shot Detection, semantische Segmentierung, Candidate Generation

Woche 3

Features, Scoring, Ranking, Erklärbarkeit

Woche 4

Packaging, UI, Export, Stabilisierung

Priorisierung: Was du notfalls weglassen kannst

Falls die Zeit knapp wird, streiche in dieser Reihenfolge:

Diarization
komplexe visuelle Modelle
LLM-gestützte Segment-Labels
hübsches Frontend
ausgefeilte Titelgenerierung

Nicht streichen:

Upload
ASR
Candidate Generation
Ranking
Export

Das ist der eigentliche Wertkern.

Täglicher Fokus pro Woche
Woche 1

Tag 1–2: Repo, Docker, DB, Redis, API-Skelett
Tag 3: Upload + Storage
Tag 4: ffmpeg-Ingestion
Tag 5–6: WhisperX-Service
Tag 7: Job-State, Tests, Cleanup

Woche 2

Tag 8–9: Shot Detection
Tag 10–11: semantische Segmentierung
Tag 12–13: Candidate Generator
Tag 14: Candidate API + Review

Woche 3

Tag 15–16: Text-Features
Tag 17: Audio-Features
Tag 18: Video-Features light
Tag 19: Specialist Scores
Tag 20: Meta-Ranker
Tag 21: Ranking API + Erklärung

Woche 4

Tag 22–23: Frontend minimal
Tag 24–25: Subtitle + 9:16 Export
Tag 26: Titel / Overlay Varianten
Tag 27: Preview + Export Flow
Tag 28: Stabilisierung + End-to-End Test

Definition of Done für das MVP

Das System ist fertig, wenn diese User Story funktioniert:

Ich lade ein 10–30 Minuten langes Video hoch, bekomme automatisch eine Liste der besten 10 Short-Kandidaten mit Begründung und kann 2–3 davon direkt als 9:16 Clip mit Untertiteln exportieren.

Wenn das steht, hast du etwas, das man testen, vorführen und weiterentwickeln kann.

Harte Produktentscheidungen für die 4 Wochen

Damit du nicht in Scope Creep läufst, setze diese Grenzen:

nur lokaler Single-User-Betrieb
nur YouTube-Shorts-Format zuerst
nur deutsch/englisch
nur lokale Dateiverarbeitung
nur Top-10 Ranking statt perfekte Vorhersage
nur erklärbare Heuristik + leichtes ML statt komplexe End-to-End-Modelle

Das ist genug für 4 Wochen.

Mein Rat zur Arbeitsweise

Arbeite jede Woche mit einem festen Endprodukt:

Woche 1 endet mit transkribierbarem Upload
Woche 2 endet mit Kandidatenliste
Woche 3 endet mit Ranking
Woche 4 endet mit exportierbarem Short

Nicht „ein bisschen alles gleichzeitig“.

Was du direkt nach Woche 4 machen solltest

Sobald das MVP steht:

10–20 eigene Videos durchjagen
manuell bewerten, welche Vorschläge wirklich gut waren
false positives notieren
häufige Fehler clustern
daraus Woche-5/6-Backlog bauen

Erst dann lohnt sich ernsthaftes Feintuning.

Wenn du willst, mache ich daraus als Nächstes einen konkreten Sprint-Backlog mit Tickets pro Woche.

wie kann ich diese Chat Inhalte exportieren und als eingabe fuer eine Harness engineering Umgebung nutzen?

Gute Frage — und genau der richtige Schritt, wenn du das Ganze systematisch in eine Engineering-Umgebung überführen willst.

Ich gebe dir eine saubere, praxisnahe Pipeline, wie du diesen Chat:

extrahierst
strukturierst
in maschinenlesbare Artefakte transformierst
in eine Harness-/CI/CD- oder AI-Dev-Umgebung einspeist
1. Zielbild (wichtig vorab)

Du willst aus diesem Chat:

unstrukturierter Dialog
→ strukturierte Spezifikation
→ versionierbare Artefakte
→ automatisierbare Inputs für dein System
2. Exportmöglichkeiten (praktisch)
Option A — Copy/Paste (realistischste Variante)

Aktuell am zuverlässigsten:

gesamten Chat kopieren
in Markdown-Datei speichern
clip-ai-architecture.md
Option B — Browser DevTools (strukturierter)

Wenn du präziser sein willst:

Chat öffnen
DevTools → Network / Elements
JSON Payloads extrahieren

→ ergibt strukturierte Messages

Option C — Screenshot + OCR (nur Notfall)

Nicht empfohlen für Engineering.

3. Transformation in Engineering-Artefakte

Der wichtigste Schritt.

Du brauchst 3 Ebenen:

Ebene 1: Raw Knowledge (unverändert)
/docs/raw/
  chat_export.md

👉 Referenz, nie anfassen

Ebene 2: Strukturierte Spezifikation

Zerlege den Chat in:

/docs/spec/
  architecture.md
  services.md
  data-model.md
  pipeline.md
  scoring.md
  roadmap.md
Ebene 3: Machine-Readable Inputs

Das ist entscheidend für Harness / Automation:

/infra/
  prompts/
  tasks/
  configs/
  pipelines/
4. Konkrete Struktur für dein Projekt

Ich empfehle dir dieses Setup:

project/
  docs/
    raw/
      chat_export.md
    spec/
      architecture.md
      pipeline.md
      services.md
      data-model.md
      roadmap.md

  ai/
    prompts/
      segmentation.prompt.md
      scoring.prompt.md
      packaging.prompt.md

    schemas/
      clip_candidate.json
      clip_score.json
      video_metadata.json

  infra/
    harness/
      pipelines.yaml
      build.yaml

  tasks/
    week1.yaml
    week2.yaml
    week3.yaml
    week4.yaml
5. Umwandlung in Harness-kompatible Inputs

Jetzt wird es interessant.

Harness arbeitet typischerweise mit:

YAML Pipelines
deklarativen Steps
wiederverwendbaren Tasks
Beispiel: Pipeline aus deinem Plan
pipeline:
  name: clip-ai-pipeline
  stages:
    - stage:
        name: ingestion
        steps:
          - run: python services/ingestion/process_video.py

    - stage:
        name: asr
        steps:
          - run: python services/asr/transcribe.py

    - stage:
        name: segmentation
        steps:
          - run: python services/segmentation/run.py

    - stage:
        name: candidates
        steps:
          - run: python services/candidates/generate.py

    - stage:
        name: scoring
        steps:
          - run: python services/scoring/rank.py

    - stage:
        name: packaging
        steps:
          - run: python services/packaging/export.py

👉 Das ist direkt aus deinem Architekturplan ableitbar.

6. Prompts als Engineering Assets

Du solltest die Chat-Inhalte auch in systematische Prompt-Definitionen überführen.

Beispiel: Scoring Prompt
SYSTEM:
Du bist ein AI-System zur Bewertung von Video-Clips hinsichtlich Viralität.

INPUT:
- transcript
- clip_duration
- features

OUTPUT:
{
  "hook_score": float,
  "retention_score": float,
  "share_score": float,
  "reasoning": [string]
}

KRITERIEN:
- starker Einstieg in <3 Sekunden
- klare Aussage
- hoher Informationswert
- emotionale Aktivierung

Speichern als:

/ai/prompts/scoring.prompt.md
7. JSON Schemas (extrem wichtig)

Das ist dein Bindeglied zwischen AI und Engineering.

Beispiel: Clip Candidate Schema
{
  "clip_id": "string",
  "start": "number",
  "end": "number",
  "type": "string",
  "features": {
    "hook_strength": "number",
    "novelty": "number",
    "clarity": "number"
  }
}
Beispiel: Clip Score Schema
{
  "clip_id": "string",
  "hook_score": "number",
  "retention_score": "number",
  "share_score": "number",
  "viral_score": "number",
  "reasons": ["string"]
}
8. Automatische Generierung (optional, sehr mächtig)

Du kannst den Chat direkt nutzen, um Artefakte zu generieren:

Schritt 1

Gib mir (oder einem LLM):

„Extrahiere alle Services und erstelle YAML + JSON Schemas“

Schritt 2

→ generiere:

OpenAPI Specs
DB Schema
Task Definitions
Pipeline YAML
9. Nutzung in Harness / CI/CD
Typischer Flow
git push
→ Harness Pipeline
→ build container
→ run ingestion
→ run asr
→ run scoring
→ store results
Erweiterung: AI-Driven Pipeline

Du kannst sogar dynamisch machen:

- step:
    name: dynamic-scoring
    type: ai
    prompt: ai/prompts/scoring.prompt.md
10. Bonus: „Executable Spec“-Ansatz (sehr stark)

Du kannst deinen Chat in ein System verwandeln, das:

Spezifikation ist
gleichzeitig ausführbar ist
Beispiel
/docs/spec/pipeline.md

→ wird automatisch geparst → erzeugt:

Python Services
YAML Pipelines
DB Schema
11. Minimaler Workflow für dich (empfohlen)

Mach es einfach so:

Schritt 1

Chat kopieren → speichern:

/docs/raw/chat.md
Schritt 2

Ich helfe dir (oder du selbst):

Architektur extrahieren
Services definieren
Datenmodell erstellen
Schritt 3

Erzeuge:

YAML Pipeline
JSON Schemas
Prompt Files
Schritt 4

In Harness integrieren

12. Wichtigster Punkt

Der Chat ist kein direkt nutzbares Artefakt.

Du musst ihn transformieren in:

deterministische Struktur
versionierbare Files
klar definierte Interfaces
13. Wenn du es richtig machst

Dann hast du:

eine AI-native Codebase
reproduzierbare Pipelines
klare Trennung zwischen:
ML
Regeln
Infrastruktur
Wenn du willst

Ich kann dir als nächsten Schritt:

👉 aus diesem Chat automatisch erzeugen:

vollständiges Repo-Layout
konkrete Harness Pipeline YAML
erste JSON Schemas + OpenAPI Spec
Starter-Code für Services

Sag einfach:
„generiere mir das Repo“ oder
„erstelle mir Harness Pipelines + Schemas“s