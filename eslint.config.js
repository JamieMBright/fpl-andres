import eslint from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/dist/**",
      "**/node_modules/**",
      "**/playwright-report/**",
      "**/test-results/**",
    ],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Build tooling. Runs under Node, never reaches a browser.
    files: ["**/scripts/**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.node },
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "jsx-a11y": jsxA11y,
      "react-hooks": reactHooks,
    },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      ...reactHooks.configs["recommended-latest"].rules,
      "@typescript-eslint/consistent-type-imports": "error",
      // `any` disables every other guarantee in this file, and the contracts
      // package exists precisely so a payload shape is checked at the boundary.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "no-floating-promises": "off",
      "@typescript-eslint/require-await": "off",
    },
  },
  {
    // Audit item #144. `api/_lib` is the boundary between the serverless
    // handlers and everything they call. An inferred return type there is a
    // contract nobody wrote down: it changes when the implementation changes,
    // silently, and the caller finds out at runtime.
    //
    // Only the exported surface. Inference inside a module is where it earns
    // its keep, and annotating a two-line local helper is noise.
    files: ["api/**/*.ts"],
    rules: {
      "@typescript-eslint/explicit-module-boundary-types": "error",
    },
  },
  {
    // Test doubles legitimately stand in for shapes they do not implement.
    files: ["**/*.test.{ts,tsx}", "**/e2e/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
