"""Package database privately, or static resources for a GitHub release."""
import argparse
import hashlib
import io
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--kind", choices=("database", "resources"), required=True)
parser.add_argument("--database", type=Path)
parser.add_argument("--tiles", type=Path)
parser.add_argument("--news-images", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Archive already exists; use a new output filename.")
if args.kind == "database" and not args.database:
    parser.error("--database is required")
if args.kind == "resources" and (not args.tiles or not args.news_images):
    parser.error("--tiles and --news-images are required")
args.output.parent.mkdir(parents=True, exist_ok=True)
checksums = []
inventory = {}

class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size):
        block = self.stream.read(size)
        self.digest.update(block)
        return block

with tarfile.open(args.output, "w:gz", compresslevel=1, format=tarfile.PAX_FORMAT) as archive:
    def add_file(path, relative, checksum_name=None):
        before = path.stat()
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Only ordinary resource files are allowed.")
        info = archive.gettarinfo(str(path), f"deployment-data/{relative}")
        info.mode = 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        with path.open("rb") as stream:
            reader = HashingReader(stream)
            archive.addfile(info, reader)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(f"Source changed while packing: {relative}")
        checksums.append(f"{reader.digest.hexdigest()}  {checksum_name or relative}")

    def add_text(relative, value):
        data = value.encode("utf-8")
        info = tarfile.TarInfo(f"deployment-data/{relative}")
        info.size = len(data)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))

    if args.kind == "database":
        for name in ("application.dump", "database-manifest.json"):
            add_file(args.database / name, f"database/{name}", name)
        add_text("database/SHA256SUMS", "\n".join(checksums) + "\n")
    else:
        for label, source, prefix in (("news_images", args.news_images, "news/images"),
                                      ("tiles", args.tiles, "tiles")):
            count = total_bytes = 0
            for root, directories, files in os.walk(source):
                directories.sort()
                for filename in sorted(files):
                    path = Path(root) / filename
                    add_file(path, f"{prefix}/{path.relative_to(source).as_posix()}")
                    count += 1
                    total_bytes += path.stat().st_size
            inventory[label] = {"files": count, "bytes": total_bytes}
            print(f"Packed {label}: {count} files, {total_bytes} bytes", flush=True)
        add_text("SHA256SUMS.resources", "\n".join(checksums) + "\n")
        add_text("resource-manifest.json", json.dumps({
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "resources": inventory, "contains_ais_or_credentials": False,
        }, ensure_ascii=False, indent=2) + "\n")

with args.output.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
args.output.with_name(args.output.name + ".sha256").write_text(
    f"{digest}  {args.output.name}\n", encoding="utf-8", newline="\n")
print(json.dumps({"archive": str(args.output), "bytes": args.output.stat().st_size,
                  "sha256": digest, "files": len(checksums)}, ensure_ascii=False))
