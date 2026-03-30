import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../api";

const STATUS_ORDER = ["uploaded", "ingesting", "ready_for_asr", "transcribing", "transcribed", "failed"];

function StatusBar({ status }) {
  const steps = ["uploaded", "ingesting", "transcribing", "transcribed"];
  const idx = steps.indexOf(status);
  return (
    <div className="status-bar">
      {steps.map((s, i) => (
        <div key={s} className={`status-step ${i <= idx ? "done" : ""} ${status === "failed" && s === steps[idx === -1 ? 0 : idx] ? "failed" : ""}`}>
          {s}
        </div>
      ))}
    </div>
  );
}

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

export default function VideoPage() {
  const { videoId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("ranking");
  const [status, setStatus] = useState(null);
  const [ranked, setRanked] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.getStatus(videoId);
      setStatus(s);
      if (s.status === "transcribed") {
        try { setRanked(await api.getRankedClips(videoId)); } catch {}
        try { setCandidates(await api.getCandidates(videoId)); } catch {}
        setPolling(false);
      } else if (s.status !== "failed") {
        setPolling(true);
      }
    } catch {}
    setLoading(false);
  }, [videoId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!polling) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [polling, load]);

  if (loading) return <div className="page"><p>Loading…</p></div>;

  return (
    <div className="page">
      <nav className="breadcrumb">
        <Link to="/">Home</Link> / {status?.video_id?.slice(0, 8)}…
      </nav>

      <section className="card">
        <h2>Pipeline Status</h2>
        <StatusBar status={status?.status || "uploaded"} />
        {status?.status === "failed" && (
          <p className="error">Error: {status.error_message}</p>
        )}
        {polling && <p className="muted">Processing… auto-refreshing every 4s</p>}
      </section>

      {status?.status === "transcribed" && (
        <>
          <div className="tabs">
            {["ranking", "candidates"].map((t) => (
              <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
                {t === "ranking" ? `Top-10 Ranking (${ranked.length})` : `All Candidates (${candidates.length})`}
              </button>
            ))}
          </div>

          {tab === "ranking" && (
            ranked.length === 0
              ? <div className="card"><p className="muted">No ranking available yet.</p></div>
              : ranked.map((clip) => (
                <div
                  key={clip.candidate_id}
                  className="card clip-card clickable"
                  onClick={() => navigate(`/videos/${videoId}/clips/${clip.candidate_id}`)}
                >
                  <div className="clip-header">
                    <span className="rank">#{clip.rank}</span>
                    <span className="clip-type">{clip.candidate_type}</span>
                    <span className="clip-time">{clip.start_time.toFixed(1)}s – {clip.end_time.toFixed(1)}s ({clip.duration.toFixed(1)}s)</span>
                    <span className="viral-score">viral {(clip.viral_score * 100).toFixed(0)}</span>
                  </div>
                  <p className="preview-text">{clip.transcript_preview}</p>
                  <div className="reasons">
                    {clip.reasons.map((r) => <span key={r} className="tag">{r}</span>)}
                  </div>
                  <div className="scores-mini">
                    <ScoreBar value={clip.hook_score} label="hook" />
                    <ScoreBar value={clip.retention_score} label="retention" />
                    <ScoreBar value={clip.share_score} label="share" />
                    <ScoreBar value={clip.packaging_score} label="packaging" />
                  </div>
                </div>
              ))
          )}

          {tab === "candidates" && (
            candidates.length === 0
              ? <div className="card"><p className="muted">No candidates yet.</p></div>
              : candidates.map((c) => (
                <div key={c.id} className="card clip-card">
                  <div className="clip-header">
                    <span className="clip-type">{c.candidate_type}</span>
                    <span className="clip-time">{c.start_time.toFixed(1)}s – {c.end_time.toFixed(1)}s ({c.duration.toFixed(1)}s)</span>
                    {c.trigger_marker && <span className="tag">{c.trigger_marker}</span>}
                  </div>
                  <p className="preview-text">{c.transcript_preview}</p>
                </div>
              ))
          )}
        </>
      )}
    </div>
  );
}
