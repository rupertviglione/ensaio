import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { Header } from "@/components/Header";
import Library from "@/pages/Library";
import NewScript from "@/pages/NewScript";
import ScriptPage from "@/pages/ScriptPage";
import Rehearsal from "@/pages/Rehearsal";
import Summary from "@/pages/Summary";
import Settings from "@/pages/Settings";

function App() {
  return (
    <div className="App grain spotlight">
      <BrowserRouter>
        <Header />
        <main className="relative z-10">
          <Routes>
            <Route path="/" element={<Library />} />
            <Route path="/novo" element={<NewScript />} />
            <Route path="/texto/:id" element={<ScriptPage />} />
            <Route path="/definicoes" element={<Settings />} />
            <Route path="/ensaio/:sessionId" element={<Rehearsal />} />
            <Route path="/resumo/:sessionId" element={<Summary />} />
          </Routes>
        </main>
        <Toaster position="bottom-right" theme="dark" />
      </BrowserRouter>
    </div>
  );
}

export default App;
