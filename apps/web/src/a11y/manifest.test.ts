import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Audit item #134. The manifest declared one icon: `favicon.svg`, which is
 * 260x200. A PWA icon must be square, so every install surface that took it was
 * distorting or letterboxing it, and `sizes: "any"` told nobody.
 *
 * These assert the manifest against the filesystem, because a manifest that
 * references a file which does not exist fails silently: the install prompt
 * simply never appears and nothing logs why.
 */

const PUBLIC = join(__dirname, "..", "..", "public");

interface ManifestIcon {
  src: string;
  type: string;
  sizes: string;
  purpose: string;
}

interface Manifest {
  id: string;
  name: string;
  short_name: string;
  lang: string;
  start_url: string;
  scope: string;
  display: string;
  background_color: string;
  theme_color: string;
  icons: ManifestIcon[];
}

const manifest = JSON.parse(
  readFileSync(join(PUBLIC, "site.webmanifest"), "utf-8"),
) as Manifest;

describe("web app manifest", () => {
  it("declares the fields an install prompt requires", () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.icons.length).toBeGreaterThan(0);
  });

  it("has a stable id so a future start_url change does not orphan installs", () => {
    expect(manifest.id).toBeTruthy();
  });

  it("declares its language and direction", () => {
    expect(manifest.lang).toBe("en-GB");
  });

  it("every declared icon file exists", () => {
    const missing = manifest.icons
      .map((icon) => icon.src)
      .filter((src) => !existsSync(join(PUBLIC, src.replace(/^\//, ""))));

    expect(missing).toEqual([]);
  });

  it("offers a square icon, not only the letterboxed favicon", () => {
    const square = manifest.icons.filter((icon) =>
      /^(\d+)x\1$/.test(icon.sizes),
    );

    expect(square.length).toBeGreaterThan(0);
    for (const icon of square) {
      const svg = readFileSync(
        join(PUBLIC, icon.src.replace(/^\//, "")),
        "utf-8",
      );
      const viewBox = /viewBox="0 0 (\d+) (\d+)"/.exec(svg);
      expect(viewBox).not.toBeNull();
      expect(viewBox?.[1]).toBe(viewBox?.[2]);
    }
  });

  it("offers a maskable icon for Android's adaptive shapes", () => {
    const maskable = manifest.icons.filter((icon) =>
      icon.purpose.includes("maskable"),
    );

    expect(maskable.length).toBeGreaterThan(0);
  });

  it("keeps maskable artwork inside the safe zone", () => {
    // An aggressive circular mask keeps roughly the central 80%. Artwork drawn
    // edge to edge gets its corners cut off, which is worse than not declaring
    // maskable at all.
    const maskable = manifest.icons.find((icon) =>
      icon.purpose.includes("maskable"),
    );
    const svg = readFileSync(
      join(PUBLIC, maskable!.src.replace(/^\//, "")),
      "utf-8",
    );

    const scale = /scale\(([\d.]+)\)/.exec(svg);
    expect(
      scale,
      "the maskable icon should scale its artwork inward",
    ).not.toBeNull();
  });

  it("uses colours that match the shipped theme", () => {
    const styles = readFileSync(
      join(PUBLIC, "..", "src", "styles.css"),
      "utf-8",
    );

    expect(styles).toContain(manifest.theme_color);
  });

  it("scopes the app to the whole site", () => {
    expect(manifest.scope).toBe("/");
  });
});
