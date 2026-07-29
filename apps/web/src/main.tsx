import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { routes } from "./App";
import "./styles.css";

const container = document.querySelector<HTMLDivElement>("#root");

if (!container) {
  throw new Error("FPL Andres could not find its application root.");
}

const router = createBrowserRouter(routes);

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
