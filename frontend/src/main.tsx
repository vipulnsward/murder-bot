import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import App from "./App";
import { TopNav } from "@/components/TopNav";
import CounterPage from "@/pages/CounterPage";
import IntelPage from "@/pages/IntelPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/counter" element={<CounterPage />} />
        <Route path="/intel" element={<IntelPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
