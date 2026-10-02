# Security policy

This candidate is intended only for a trusted user on their own computer. It is not a public web service, a multi-user server, or an operating-system sandbox. Do not bind it to a public interface, put it behind a tunnel, or use it for untrusted bulk computation.

## Implemented boundaries

- The launcher binds only to IPv4 loopback; Flask validates localhost Host headers against DNS rebinding.
- Cross-site Fetch Metadata and mismatched Origin requests are rejected. All POST routes require a per-process unpredictable write token. No CORS access is granted.
- Browser responses prohibit framing, MIME sniffing, referrer disclosure and device permissions. The main UI accepts only local scripts; Crumble authorizes its generated inline script by SHA-256 hash. Inline styles remain allowed for rendering.
- Requests are bounded to 4 MiB and eight multipart parts. Graph sizes, coordinates, types, probabilities and artifact names are validated.
- DAE preflight rejects DTDs, XML entities, external URLs/files, images, includes, cyclic node references and excessive XML complexity before TQEC parses it. Uploaded filenames never choose storage destinations.
- Detector imports use JSON, never uploaded Python or pickle. Database names and exported filenames cannot choose arbitrary filesystem paths.
- Unexpected HTTP errors return a generic message, with details kept in the local log. API responses and pages are not cached.
- The launcher creates new data with private OS permissions. The source exporter excludes user data, environments and Git history, and scans for common credentials and personal absolute paths.

## Limits and dependencies

A local process running as the same user can access the app and its data. Large intentional compile/simulation settings can exhaust memory or CPU; there is currently no worker timeout or cancellation interface. Numerical correctness and parser safety also depend on TQEC, Stim and other third-party libraries. Security headers and tests do not constitute a penetration test or guarantee of security.

Exported correlation-surface HTML loads external Three.js modules when opened. This is separate from offline graph editing and local Crumble. Install only trusted dependency distributions; runtime pins and PyPI SHA-256 hashes are in `requirements.lock`. Update them in a clean environment, audit and rerun the tests before release. See `docs/RELEASE_REVIEW.md` for the candidate's audit scope and remaining gates.

## Reporting

Do not post private graphs, tokens, credentials or an exploit containing sensitive files in public issues. Before publication, report privately to the project owner who supplied this candidate. After maintainer approval, configure the receiving repository's private vulnerability-reporting channel and replace this paragraph with its verified contact. No security email address or upstream sponsorship is implied.
