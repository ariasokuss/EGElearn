const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const root = process.cwd();
const nodeCmd = process.execPath;
const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");
const port = Number(process.env.SEO_VALIDATE_PORT ?? 4207);
const baseUrl = `http://127.0.0.1:${port}`;
const expectedOrigin = process.env.NEXT_PUBLIC_APP_URL
  ? process.env.NEXT_PUBLIC_APP_URL.replace(/\/$/, "")
  : null;

const requiredBuildArtifacts = [".next/BUILD_ID", ".next/server/app-paths-manifest.json"];
const privateRoutes = ["/auth", "/registration", "/restore", "/chat", "/folders", "/settings", "/notes", "/learning"];

function ensureFile(relativePath) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`Missing required artifact: ${relativePath}`);
  }
}

async function fetchText(url) {
  const response = await fetch(url);
  const text = await response.text();
  return { response, text };
}

function readRegistryPaths() {
  const registryPath = path.join(root, "src", "features", "seo-content", "model", "seo-pages.ts");
  const registryContent = fs.readFileSync(registryPath, "utf8");
  const matches = [...registryContent.matchAll(/path:\s*"([^"]+)"/g)];

  return matches.map((item) => item[1]);
}

async function waitForServer(maxAttempts = 120) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/robots.txt`);
      if (response.ok) {
        return;
      }
    } catch {}

    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  throw new Error("Failed to start Next.js server for SEO validation.");
}

function parseSitemapUrls(sitemapXml) {
  const matches = [...sitemapXml.matchAll(/<loc>(.*?)<\/loc>/g)];
  return matches.map((item) => item[1]);
}

function extractRobotsSitemapUrl(robotsText) {
  const match = robotsText.match(/Sitemap:\s*(.+)/i);
  return match?.[1]?.trim() ?? null;
}

async function validateRobots() {
  const { response, text } = await fetchText(`${baseUrl}/robots.txt`);

  if (!response.ok) {
    throw new Error(`robots.txt is not available, status=${response.status}`);
  }

  if (!text.includes("Sitemap:")) {
    throw new Error("robots.txt does not include Sitemap directive.");
  }

  const sitemapUrl = extractRobotsSitemapUrl(text);
  if (!sitemapUrl) {
    throw new Error("robots.txt sitemap URL is missing.");
  }

  const parsedSitemapUrl = new URL(sitemapUrl);
  if (parsedSitemapUrl.pathname !== "/sitemap.xml") {
    throw new Error("robots.txt sitemap URL has unexpected pathname.");
  }

  if (expectedOrigin && parsedSitemapUrl.origin !== expectedOrigin) {
    throw new Error("robots.txt contains unexpected Sitemap origin.");
  }

  for (const route of privateRoutes) {
    if (!text.includes(`Disallow: ${route}`)) {
      throw new Error(`robots.txt is missing Disallow rule for ${route}`);
    }
  }
}

async function validateSitemap() {
  const requiredPublicRoutes = readRegistryPaths();
  const { response, text } = await fetchText(`${baseUrl}/sitemap.xml`);

  if (!response.ok) {
    throw new Error(`sitemap.xml is not available, status=${response.status}`);
  }

  const urls = parseSitemapUrls(text);
  if (!urls.length) {
    throw new Error("sitemap.xml has no URLs.");
  }

  for (const route of requiredPublicRoutes) {
    const matchedUrl = urls.find((url) => url.endsWith(route));
    if (!matchedUrl) {
      throw new Error(`sitemap.xml is missing required route: ${route}`);
    }

    const parsedUrl = new URL(matchedUrl);
    if (expectedOrigin && parsedUrl.origin !== expectedOrigin) {
      throw new Error(`sitemap.xml contains unexpected origin for route: ${route}`);
    }
  }

  for (const route of privateRoutes) {
    if (urls.some((url) => url.includes(route))) {
      throw new Error(`Private route leaked into sitemap.xml: ${route}`);
    }
  }
}

async function validateCanonicalAndNoindex() {
  const publicPage = await fetchText(`${baseUrl}/ege`);
  if (!publicPage.response.ok) {
    throw new Error(`Public SEO page is unavailable, status=${publicPage.response.status}`);
  }

  const canonicalMatch = publicPage.text.match(/<link[^>]+rel="canonical"[^>]+href="([^"]+)"/i);
  if (!canonicalMatch) {
    throw new Error("Public page canonical is missing.");
  }

  const canonicalUrl = new URL(canonicalMatch[1]);
  if (canonicalUrl.pathname !== "/ege") {
    throw new Error("Public page canonical has unexpected pathname.");
  }

  if (expectedOrigin && canonicalUrl.origin !== expectedOrigin) {
    throw new Error("Public page canonical has unexpected origin.");
  }

  const privateSmokeRoutes = ["/auth", "/chat", "/settings/profile"];
  for (const route of privateSmokeRoutes) {
    const privatePage = await fetchText(`${baseUrl}${route}`);
    if (!privatePage.response.ok) {
      throw new Error(`Private/auth page is unavailable: ${route}, status=${privatePage.response.status}`);
    }

    if (!privatePage.text.includes('content="noindex, nofollow')) {
      throw new Error(`Private/auth page is missing noindex, nofollow robots meta: ${route}`);
    }
  }
}

async function run() {
  requiredBuildArtifacts.forEach(ensureFile);
  ensureFile("node_modules/next/dist/bin/next");

  const server = spawn(nodeCmd, [nextBin, "start", "-p", String(port)], {
    cwd: root,
    stdio: "inherit",
    env: {
      ...process.env,
      PORT: String(port),
    },
  });

  try {
    await waitForServer();
    await validateRobots();
    await validateSitemap();
    await validateCanonicalAndNoindex();
    console.log("SEO artifact validation passed.");
  } finally {
    if (!server.killed) {
      server.kill("SIGTERM");
    }
  }
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
