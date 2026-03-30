import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import VideoPage from "./pages/VideoPage";
import ClipDetailPage from "./pages/ClipDetailPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/videos/:videoId" element={<VideoPage />} />
        <Route path="/videos/:videoId/clips/:candidateId" element={<ClipDetailPage />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
