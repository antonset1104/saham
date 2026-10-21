"""CA bundle for Yahoo's curl-cffi transport on Windows.

Python's truststore affects urllib/requests, but curl-cffi needs a PEM file.
Keep certificate verification enabled and include only Windows roots trusted for
TLS server authentication alongside the standard certifi roots.
"""

import hashlib
import logging
import os
import ssl
import sys
import tempfile
from pathlib import Path

import certifi


_SERVER_AUTH_OID = "1.3.6.1.5.5.7.3.1"
_bundle_path: Path | None = None
_logger = logging.getLogger(__name__)


def configure_yahoo_tls() -> None:
    """Expose a cached CA bundle to curl-cffi without weakening TLS checks."""
    global _bundle_path
    if sys.platform != "win32" or _bundle_path is not None:
        return
    if os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE"):
        return

    temp_path: Path | None = None
    try:
        roots = [
            ssl.DER_cert_to_PEM_cert(certificate).encode("ascii")
            for certificate, encoding, trust in ssl.enum_certificates("ROOT")
            if encoding == "x509_asn" and (trust is True or _SERVER_AUTH_OID in trust)
        ]
        if not roots:
            return

        bundle = Path(certifi.where()).read_bytes() + b"\n" + b"".join(roots)
        digest = hashlib.sha256(bundle).hexdigest()[:16]
        cache_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "saham"
        cache_root.mkdir(parents=True, exist_ok=True)
        path = cache_root / f"yahoo-ca-{digest}.pem"
        if not path.exists() or path.read_bytes() != bundle:
            with tempfile.NamedTemporaryFile(dir=cache_root, prefix=".yahoo-ca-", suffix=".tmp", delete=False) as output:
                temp_path = Path(output.name)
                output.write(bundle)
            os.replace(temp_path, path)
            temp_path = None
    except (OSError, ssl.SSLError) as error:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        _logger.warning("Gagal menyiapkan sertifikat sistem untuk Yahoo: %s", error)
        return

    _bundle_path = path
    os.environ["REQUESTS_CA_BUNDLE"] = str(path)
