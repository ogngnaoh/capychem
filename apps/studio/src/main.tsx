import React from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";
import App from "./App";
import "./design-tokens.css";
import "./styles.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Theme theme={neutralTheme} mode="light">
      <App />
    </Theme>
  </React.StrictMode>,
);

import "./live.css";

import "./product.css";
import "./flow-v5.css";
import "./candidate-inspector-v5.css";
import "./workspace-v5.css";
