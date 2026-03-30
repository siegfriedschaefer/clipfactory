import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function UploadPage() {
  const [videos, setVideos] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef();
  const navigate = useNavigate();

  useEffect(() => {
    api.listVideos().then(setVideos).catch(() => {});
  }, []);

  async function handleUpload(e) {
    e.preventDefault();
    const file = fileRef.current.files[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const video = await api.uploadVideo(file);
      navigate(`/videos/${video.id}`);
    } catch (err) {
      setError(err.message);
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Delete this video and all its data?")) return;
    await api.deleteVideo(id);
    setVideos((v) => v.filter((x) => x.id !== id));
  }

  return (
    <div className="page">
      <h1>ClipFabric</h1>

      <section className="card">
        <h2>Upload Video</h2>
        <form onSubmit={handleUpload} className="upload-form">
          <input ref={fileRef} type="file" accept=".mp4,.mov,.avi,.mkv,.webm" required />
          <button type="submit" disabled={uploading}>
            {uploading ? "Uploading…" : "Upload & Analyse"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      {videos.length > 0 && (
        <section className="card">
          <h2>Previous Videos</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Status</th>
                <th>Uploaded</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v) => (
                <tr key={v.id} onClick={() => navigate(`/videos/${v.id}`)} className="clickable">
                  <td>{v.filename}</td>
                  <td><span className={`badge badge-${v.status}`}>{v.status}</span></td>
                  <td>{new Date(v.created_at).toLocaleString()}</td>
                  <td>
                    <button
                      className="btn-danger"
                      onClick={(e) => { e.stopPropagation(); handleDelete(v.id); }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
