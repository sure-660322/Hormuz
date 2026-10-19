"""Validate archive content hashes and prohibit database bytes in static assets."""
import argparse
import hashlib
import json
import tarfile
from pathlib import PurePosixPath

parser = argparse.ArgumentParser()
parser.add_argument("archive")
parser.add_argument("--kind", choices=("database", "resources"), required=True)
args = parser.parse_args()
hashes = {}
expected = None
total = 0
with tarfile.open(args.archive, "r|gz") as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not member.isfile():
            raise RuntimeError(f"Unsafe archive member: {member.name}")
        if path.parts[0] != "deployment-data" or any(p.startswith(".env") for p in path.parts):
            raise RuntimeError(f"Unexpected archive member: {member.name}")
        relative = path.relative_to("deployment-data").as_posix()
        if args.kind == "resources":
            allowed = relative.startswith(("news/images/", "tiles/")) or relative in {
                "SHA256SUMS.resources", "resource-manifest.json"}
            if not allowed:
                raise RuntimeError(f"Non-static content in resource archive: {relative}")
            key = relative
        else:
            if relative not in {"database/application.dump", "database/database-manifest.json", "database/SHA256SUMS"}:
                raise RuntimeError(f"Unexpected database content: {relative}")
            key = path.name
        stream = archive.extractfile(member)
        if key in {"SHA256SUMS", "SHA256SUMS.resources"}:
            expected = dict((line[66:], line[:64]) for line in stream.read().decode().splitlines())
        elif key == "resource-manifest.json":
            json.load(stream)
        else:
            if key in hashes:
                raise RuntimeError(f"Duplicate member: {key}")
            hashes[key] = hashlib.file_digest(stream, "sha256").hexdigest()
            total += member.size
if hashes != expected:
    raise RuntimeError("Archive checksums or file inventory differ.")
print(json.dumps({"archive": args.archive, "kind": args.kind,
                  "verified_files": len(hashes), "uncompressed_bytes": total, "status": "PASS"}))
