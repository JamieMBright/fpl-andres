import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

import { ApplicationFrame } from "./components/ApplicationFrame";
import { LazyRoute } from "./components/LazyRoute";
import HomePage from "./pages/HomePage";
import NotFoundPage from "./pages/NotFoundPage";
import TeamAnalysisRoute from "./pages/TeamAnalysisPage";

/**
 * The route table, and nothing else.
 *
 * Audit item #115. This file was 910 lines holding eleven components, six
 * helpers and the route table, so every one of them could only be tested by
 * rendering a router. Each now lives beside the thing it does.
 *
 * These three are split out so the 213 kB projection artifact and the 51 kB
 * calibration report are fetched by the routes that need them, not by every
 * first paint.
 */
const MethodPage = lazy(() => import("./pages/MethodPage"));
const PlayerPoolPage = lazy(() => import("./pages/PlayerPoolPage"));
const CalibrationPage = lazy(() => import("./pages/CalibrationPage"));
const SeasonPlanPage = lazy(() => import("./pages/SeasonPlanPage"));
const KitPreviewPage = lazy(() => import("./pages/KitPreviewPage"));
const AnalysisPage = lazy(() => import("./pages/AnalysisPage"));
/** An operator tool, kept out of the navigation and out of the first paint. */
const DiagnosticsPage = lazy(() => import("./pages/DiagnosticsPage"));

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <ApplicationFrame />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "team/:teamId", element: <TeamAnalysisRoute /> },
      {
        path: "plan",
        element: (
          <LazyRoute>
            <SeasonPlanPage />
          </LazyRoute>
        ),
      },
      {
        path: "players",
        element: (
          <LazyRoute>
            <PlayerPoolPage />
          </LazyRoute>
        ),
      },
      {
        path: "analysis",
        element: (
          <LazyRoute>
            <AnalysisPage />
          </LazyRoute>
        ),
      },
      {
        path: "methodology",
        element: (
          <LazyRoute>
            <MethodPage />
          </LazyRoute>
        ),
      },
      {
        path: "kits",
        element: (
          <LazyRoute>
            <KitPreviewPage />
          </LazyRoute>
        ),
      },
      {
        path: "calibration",
        element: (
          <LazyRoute>
            <CalibrationPage />
          </LazyRoute>
        ),
      },
      {
        path: "diagnostics",
        element: (
          <LazyRoute>
            <DiagnosticsPage />
          </LazyRoute>
        ),
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
