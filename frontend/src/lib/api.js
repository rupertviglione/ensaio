import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const http = axios.create({ baseURL: API });

export const errMsg = (e) => e?.response?.data?.detail || e?.message || "Ocorreu um erro";

export const api = {
  listScripts: () => http.get("/scripts").then((r) => r.data),
  getScript: (id) => http.get(`/scripts/${id}`).then((r) => r.data),
  createScript: (body) => http.post("/scripts", body).then((r) => r.data),
  updateScript: (id, body) => http.put(`/scripts/${id}`, body).then((r) => r.data),
  deleteScript: (id) => http.delete(`/scripts/${id}`).then((r) => r.data),
  extract: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return http.post("/extract", fd).then((r) => r.data);
  },
  addMemory: (id, text, extra = {}) => http.post(`/scripts/${id}/memory`, { text, ...extra }).then((r) => r.data),
  updateLines: (id, lines) => http.put(`/scripts/${id}/lines`, { lines }).then((r) => r.data),
  renameCharacter: (id, old, name) => http.post(`/scripts/${id}/rename-character`, { old, new: name }).then((r) => r.data),
  deleteMemory: (id, noteId) => http.delete(`/scripts/${id}/memory/${noteId}`).then((r) => r.data),
  scriptSessions: (id) => http.get(`/scripts/${id}/sessions`).then((r) => r.data),
  createSession: (body) => http.post("/sessions", body).then((r) => r.data),
  getSession: (id) => http.get(`/sessions/${id}`).then((r) => r.data),
  turn: (id, body) => http.post(`/sessions/${id}/turn`, body).then((r) => r.data),
  finish: (id) => http.post(`/sessions/${id}/finish`).then((r) => r.data),
  stt: (blob) => {
    const fd = new FormData();
    const ext = blob.type.includes("mp4") ? "mp4" : "webm";
    fd.append("file", blob, `fala.${ext}`);
    return http.post("/stt", fd).then((r) => r.data.text);
  },
  voiceTurn: (id, lineIdx, blob) => {
    const fd = new FormData();
    fd.append("line_idx", String(lineIdx));
    fd.append("file", blob, `fala.${blob.type.includes("mp4") ? "mp4" : "webm"}`);
    return http.post(`/sessions/${id}/voice-turn`, fd).then((r) => r.data);
  },
  voices: () => http.get("/voices").then((r) => r.data),
  probe: (id, lineIdx, blob, final) => {
    const fd = new FormData();
    fd.append("line_idx", String(lineIdx));
    fd.append("final", final ? "true" : "false");
    fd.append("file", blob, `fala.${blob.type.includes("mp4") ? "mp4" : "webm"}`);
    return http.post(`/sessions/${id}/probe`, fd).then((r) => r.data);
  },
  setElevenVoice: (id, character, voice) => http.post(`/scripts/${id}/eleven-voice`, { character, voice }).then((r) => r.data),
  autoVoices: (id) => http.post(`/scripts/${id}/auto-voices`).then((r) => r.data),
  tts: (body) =>
    http.post("/tts", body, { responseType: "blob" }).then((r) => URL.createObjectURL(r.data)),
};

export const VOICES = [
  { id: "onyx", label: "Onyx — grave, masculina" },
  { id: "echo", label: "Echo — calma, masculina" },
  { id: "ash", label: "Ash — clara, masculina" },
  { id: "fable", label: "Fable — expressiva" },
  { id: "verse", label: "Verse — narrativa" },
  { id: "nova", label: "Nova — enérgica, feminina" },
  { id: "coral", label: "Coral — calorosa, feminina" },
  { id: "shimmer", label: "Shimmer — luminosa, feminina" },
  { id: "sage", label: "Sage — ponderada" },
  { id: "ballad", label: "Ballad — suave" },
  { id: "alloy", label: "Alloy — neutra" },
];

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString("pt-PT", { dateStyle: "medium", timeStyle: "short" }) : "—";
