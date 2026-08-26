import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { useAuthStore } from "@/store/auth";
import App from "@/App";
import "@/index.css";

// Hydrate auth from localStorage
useAuthStore.getState().loadFromStorage();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
