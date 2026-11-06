import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import "./styles.css";

const container = document.querySelector<HTMLDivElement>("#root");

if (!container) {
  throw new Error("FPL Andres could not find its application root.");
}

const root = createRoot(container);

root.render(
  <main className="text-page" id="main">
    <p role="status">{"I'm loading the player records\u2026"}</p>
  </main>,
);

void import("./App")
  .then(({ routes }) => {
    const router = createBrowserRouter(routes);
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <RouterProvider router={router} />
        </ErrorBoundary>
      </StrictMode>,
    );
  })
  .catch(() => {
    root.render(
      <main className="text-page" id="main">
        <h1>I couldn't load the player records.</h1>
        <p role="alert">Reload to try the latest complete records.</p>
        <button
          className="error-reload"
          type="button"
          onClick={() => window.location.reload()}
        >
          Reload records
        </button>
      </main>,
    );
  });
