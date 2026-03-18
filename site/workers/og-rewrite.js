/**
 * Cloudflare Worker: rewrite og:image for /thought/?ts=<timestamp> pages.
 *
 * Social crawlers (Bluesky, Twitter, Facebook) don't execute JS, so the
 * client-side og:image update in thought.js is invisible to them. This
 * worker intercepts requests to /thought/ with a ts= query param and
 * injects the correct per-thought og:image URL into the HTML response.
 */

const API_BASE = 'https://spark-api.wedd.au/api/v1/public';

// Validate ts looks like an ISO timestamp (prevent XSS injection into HTML attributes)
const TS_PATTERN = /^[\d\-T:+.Z]+$/;

function escapeHtmlAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export default {
  // NOTE: This Worker relies on zone-deployed routing (spark.wedd.au/thought/* → Worker).
  // Cloudflare prevents recursive Worker invocation on the same zone, so fetch(request)
  // hits the origin server, not this Worker again.
  async fetch(request) {
    const url = new URL(request.url);

    // Only intercept /thought/ paths with a ts= param
    if (!url.pathname.startsWith('/thought/') && url.pathname !== '/thought') {
      return fetch(request);
    }

    const ts = url.searchParams.get('ts');
    if (!ts || ts.length > 200 || !TS_PATTERN.test(ts)) {
      return fetch(request);
    }

    // Fetch the original page from origin
    const response = await fetch(request);
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/html')) {
      return response;
    }

    // Build the per-thought image URL (HTML-escaped for safe attribute injection)
    const imageUrl = escapeHtmlAttr(`${API_BASE}/thought-image?ts=${encodeURIComponent(ts)}`);

    // Rewrite og:image and dimensions (thought cards are 1080x1080)
    let html = await response.text();
    html = html.replace(
      /<meta property="og:image" content="[^"]*">/,
      `<meta property="og:image" content="${imageUrl}">`
    );
    html = html.replace(
      /<meta property="og:image:width" content="[^"]*">/,
      '<meta property="og:image:width" content="1080">'
    );
    html = html.replace(
      /<meta property="og:image:height" content="[^"]*">/,
      '<meta property="og:image:height" content="1080">'
    );

    // Also update twitter:image if present
    html = html.replace(
      /<meta name="twitter:image" content="[^"]*">/,
      `<meta name="twitter:image" content="${imageUrl}">`
    );

    return new Response(html, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),
        'content-type': 'text/html; charset=utf-8',
      },
    });
  },
};
