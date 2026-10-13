import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import { ToastProvider } from "../src/components/ui";
import "../src/styles.css";
import "./showcase.css";
import ShowcaseApp from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <ToastProvider>
        <ShowcaseApp />
      </ToastProvider>
    </HashRouter>
  </StrictMode>,
);
