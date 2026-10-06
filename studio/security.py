"""Boundaries for a single-user, loopback-only application."""

import base64
import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from defusedxml import ElementTree
from flask import abort, request


def validate_dae(data: bytes) -> None:
    """Reject active/external XML before handing a plain DAE to TQEC."""
    try:
        root = ElementTree.fromstring(
            data, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except Exception as exc:
        raise ValueError(
            "DAE must be plain XML without DTDs, entities or compressed contents."
        ) from exc
    pending = [(root, 0)]
    count = 0
    ids = set()
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 64 or count > 50000:
            raise ValueError("DAE exceeds the supported XML complexity limits.")
        node_id = node.get("id")
        if node_id:
            if node_id in ids:
                raise ValueError("DAE contains duplicate XML identifiers.")
            ids.add(node_id)
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in ("image", "include"):
            raise ValueError(
                "DAE images and external includes are not supported. Export a self-contained block graph."
            )
        for key, value in node.attrib.items():
            if key.rsplit("}", 1)[-1] in ("url", "source") and value and not value.startswith("#"):
                raise ValueError("DAE references must stay inside the same document.")
        pending.extend((child, depth + 1) for child in node)
    # Reject cyclic instance_node links, which can recurse inside downstream loaders.
    references = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "node" and node.get("id"):
            references[node.get("id")] = [
                child.get("url", "")[1:]
                for child in node.iter()
                if child.tag.rsplit("}", 1)[-1] == "instance_node"
            ]
    visited, active = set(), set()

    def visit(name):
        if name in active:
            raise ValueError("DAE contains a cyclic node reference.")
        if name in visited:
            return
        if len(active) >= 64:
            raise ValueError("DAE node references exceed the supported depth.")
        active.add(name)
        for target in references.get(name, []):
            visit(target)
        active.remove(name)
        visited.add(name)

    for name in references:
        visit(name)


def configure_security(app):
    app.config.update(
        TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"],
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=4 * 1024 * 1024,
        MAX_FORM_PARTS=8,
    )

    @app.before_request
    def same_origin():
        # Host validation also protects against DNS rebinding to loopback.
        host = request.host
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403, description="Cross-site requests are not allowed.")
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != request.scheme
                or parsed.netloc != host
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                abort(403, description="Requests must come from this Studio window.")

    @app.after_request
    def response_headers(response):
        if request.endpoint == "static" and response.status_code in (200, 304):
            # Windows registry associations can mislabel scripts as text/plain.
            # These are trusted bundled assets, never user-uploaded files.
            suffix = PurePosixPath(request.view_args["filename"]).suffix.lower()
            asset_types = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
            if suffix in asset_types:
                response.content_type = asset_types[suffix] + "; charset=utf-8"
            response.headers["Cache-Control"] = "no-store"
        script_policy = "'self'"
        if request.endpoint == "crumble_viewer" and response.status_code == 200:
            # Stim ships one self-contained script. Authorize only its exact content.
            scripts = re.findall(
                r"<script\b[^>]*>(.*?)</script\s*>",
                response.get_data(as_text=True),
                re.DOTALL | re.IGNORECASE,
            )
            script_policy = " ".join(
                "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
                for s in scripts
            )
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src {script_policy}; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.path.startswith("/api/") or request.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response
