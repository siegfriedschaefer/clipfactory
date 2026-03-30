import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";

function ScoreBar({ value, label }) {
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <div className="score-bar-bg">
        <div className="score-bar-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="score-value">{(value * 100).toFixed(0)}</span>
    </div>
  );
}

export default function ClipDetailPage() {
  const { videoId, candidateId } = useParams();
  const [clip, setClip] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getRankedClips(videoId)
      .then((clips) => {
        const found = clips.find((c) => c.candidate_id === candidateId);
        setClip(found || null);
      })
      .catch(() => {});
  }, [videoId, candidateId]);

  async function handleFeedback(action) {
    try {
      await api.sendFeedback(videoId, candidateId, action);
      setFeedback(action);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      await api.exportClip(videoId, candidateId);
      setExportDone(true);
      await handleFeedback("exported");
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }

  if (!clip) return <div className="page"><p>Loading…</p></div>;

  return (
    <div className="page">
      <nav className="breadcrumb">
        <Link to="/">Home</Link> / <Link to={`/videos/${videoId}`}>Video</Link> / Clip #{clip.rank}
      </nav>

      <section className="card">
        <div className="clip-header">
          <span className="rank">#{clip.rank}</span>
          <span className="clip-type">{clip.candidate_type}</span>
          <span className="clip-time">
            {clip.start_time.toFixed(1)}s – {clip.end_time.toFixed(1)}s ({clip.duration.toFixed(1)}s)
          </span>
          <span className="viral-score">viral {(clip.viral_score * 100).toFixed(0)}</span>
        </div>

        <p className="preview-text">{clip.transcript_preview}</p>

        {clip.title_suggestions_v0?.length > 0 && (
          <div style={{ marginTop: "0.75rem" }}>
            <strong>Title suggestions:</strong>
            <ul>
              {clip.title_suggestions_v0.map((t) => <li key={t}>{t}</li>)}
            </ul>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Scores</h2>
        <ScoreBar value={clip.viral_score} label="viral (overall)" />
        <ScoreBar value={clip.hook_score} label="hook" />
        <ScoreBar value={clip.retention_score} label="retention" />
        <ScoreBar value={clip.share_score} label="share" />
        <ScoreBar value={clip.packaging_score} label="packaging" />
        <ScoreBar value={clip.risk_score} label="risk (lower = better)" />
      </section>

      <section className="card">
        <h2>Why this clip?</h2>
        <div className="reasons">
          {clip.reasons.map((r) => <span key={r} className="tag">{r}</span>)}
        </div>
      </section>

      <section className="card">
        <h2>Actions</h2>

        <div className="action-row">
          <button
            className="btn-primary"
            onClick={handleExport}
            disabled={exporting || exportDone}
          >
            {exporting ? "Exporting…" : exportDone ? "Exported ✓" : "Export as 9:16 MP4"}
          </button>
        </div>

        <div className="action-row" style={{ marginTop: "0.75rem" }}>
          <span style={{ marginRight: "0.5rem" }}>Feedback:</span>
          <button
            className={`btn-feedback ${feedback === "positive" ? "active" : ""}`}
            onClick={() => handleFeedback("positive")}
            disabled={!!feedback}
          >
            👍 Good
          </button>
          <button
            className={`btn-feedback ${feedback === "negative" ? "active" : ""}`}
            onClick={() => handleFeedback("negative")}
            disabled={!!feedback}
          >
            👎 Bad
          </button>
        </div>

        {feedback && <p className="muted" style={{ marginTop: "0.5rem" }}>Feedback saved: {feedback}</p>}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
