// Empty string = relative URLs (works both behind nginx and with Vite dev proxy)
const BASE = import.meta.env.VITE_API_URL ?? "";

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listVideos: () => req("/videos"),

  uploadVideo: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("/videos", { method: "POST", body: fd });
  },

  deleteVideo: (id) => req(`/videos/${id}`, { method: "DELETE" }),

  getStatus: (id) => req(`/videos/${id}/status`),

  getCandidates: (id) => req(`/videos/${id}/candidates`),

  getRankedClips: (id) => req(`/videos/${id}/ranked-clips`),

  exportClip: (videoId, candidateId) =>
    req(`/videos/${videoId}/candidates/${candidateId}/export`, { method: "POST" }),

  getExports: (videoId) => req(`/videos/${videoId}/exports`),

  sendFeedback: (videoId, candidateId, action) =>
    req(`/videos/${videoId}/candidates/${candidateId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }),
};
