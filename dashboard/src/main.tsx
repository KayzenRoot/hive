import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import ControlCenterMetrics from "./ControlCenterMetrics";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <ControlCenterMetrics />
  </StrictMode>,
);
