import type { RouteObject } from "react-router-dom";

import { ApplicationFrame } from "./components/ApplicationFrame";
import { LazyRoute } from "./components/LazyRoute";
import HomePage from "./pages/HomePage";
import NotFoundPage from "./pages/NotFoundPage";
import TeamRedirect from "./pages/TeamRedirect";
import { lazyRoute } from "./state/lazy-route";

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
const MethodPage = lazyRoute(() => import("./pages/MethodPage"));
const PlayerPoolPage = lazyRoute(() => import("./pages/PlayerPoolPage"));
const CalibrationPage = lazyRoute(() => import("./pages/CalibrationPage"));
const SeasonPlanPage = lazyRoute(() => import("./pages/SeasonPlanPage"));
const KitPreviewPage = lazyRoute(() => import("./pages/KitPreviewPage"));
const AnalysisPage = lazyRoute(() => import("./pages/AnalysisPage"));

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <ApplicationFrame />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "team/:teamId", element: <TeamRedirect /> },
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
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
