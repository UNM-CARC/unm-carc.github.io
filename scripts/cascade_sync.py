#!/usr/bin/env python3
"""Publish the built site into Cascade CMS through its REST API.

carc.unm.edu is served from an Apache document root that only Cascade can reach
(port 22 on the host is firewalled from off-campus, so CI cannot rsync). Cascade
itself is publicly reachable, so this tool pushes the built tree into Cascade's
asset tree and lets Cascade publish it by SFTP. Cascade becomes a conduit nobody
edits; every content change flows from the repo.

Ownership is a manifest (stored in Cascade, unpublished, with a local cache).
The tool never deletes an asset that is not in the manifest, never writes under
the legacy folders it must not touch, and never folder-publishes a folder it did
not create. Every publish is verified by comparing the live file's SHA-256 with
the local build.

    cascade_sync.py preflight
    cascade_sync.py probe                      # learn the API's rules first
    cascade_sync.py plan   --scope about/ --with-referenced-assets
    cascade_sync.py sync   --scope about/ --with-referenced-assets --verify-live
    cascade_sync.py verify
    cascade_sync.py remove --scope about/      # unpublish -> 404 -> delete
    cascade_sync.py retire-page research/featured-projects
    cascade_sync.py tombstone _publish-test.txt

Stdlib only. Key: $CASCADE_API_KEY, else ~/.cascade/api_key.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://cascade.unm.edu/api/v1"
SITE_NAME = "carc.unm.edu V2"
LIVE_BASE = "https://carc.unm.edu/"
ROOT_FOLDER_ID = "3e9a06cbc0a8508c0d511691e1e04068"
DESTINATION_ID = "466010f7c0a8508c6f5fe53a2f7abc91"
DESTINATION_DIR = "public_html/carc.unm.edu"
MANIFEST_FOLDER = "_carc-sync"
PROBE_FOLDER = "_carc-sync-probe"

# Legacy Cascade content that keeps serving at its old URLs. Refuse any write here.
NEVER_TOUCH = (
    "_internal", "archive", "images", "new-users", "systems", "user-support-2",
    "news--events", "about-carc", "contact-us", "education--training",
    "assets/css", "assets/img", "assets/js",
    "google6adb8a45c621767b.html", "donate-to-carc",
)
# Pre-existing assets we may edit by id but never create over or delete.
PROTECTED = {
    ".htaccess": "69500253c0a8508c6f5fe53ae307e5c1",
    "robots.txt": "3e9a07d4c0a8508c0d5116914151ee22",
    "assets/carc-cost-model-tool.xlsx": "674230c20a65a0e753886bc21ee12179",
}
TEXT_EXT = {".html", ".htm", ".md", ".txt", ".xml", ".css", ".js", ".json",
            ".svg", ".csv", ".yml", ".yaml", ".toml"}
CONTROL_SET = ["", "robots.txt", "sitemap.xml", "about-carc/index.html",
               "research/featured-projects.html"]

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cascade-sync"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- API

class CascadeError(RuntimeError):
    pass


class Cascade:
    """Thin client over the Cascade REST API."""

    def __init__(self, key: str, pace: float = 0.2):
        self.key = key
        self.pace = pace
        self._last = 0.0

    def _wait(self) -> None:
        dt = time.time() - self._last
        if dt < self.pace:
            time.sleep(self.pace - dt)
        self._last = time.time()

    def call(self, path: str, body: dict | None = None, retries: int = 4) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        timeout = 120 if not data or len(data) < 4_000_000 else 900
        req = urllib.request.Request(
            f"{API}/{path}", data=data, method="POST" if data is not None else "GET",
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"})
        for attempt in range(retries + 1):
            self._wait()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                try:
                    return json.loads(raw)
                except ValueError:
                    raise CascadeError(f"non-JSON response from {path} (auth expired?)")
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503, 504) and attempt < retries and data is None:
                    time.sleep(2 ** attempt)
                    continue
                raise CascadeError(f"HTTP {e.code} on {path}: {e.read()[:200]!r}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries and data is None:
                    time.sleep(2 ** attempt)
                    continue
                raise CascadeError(f"{type(e).__name__} on {path}: {e}")
        raise CascadeError(f"exhausted retries on {path}")

    # reads ---------------------------------------------------------------
    def read(self, kind: str, ident: str) -> dict | None:
        """Read by id, or by site path when `ident` contains a '/' or looks like a name."""
        if re.fullmatch(r"[0-9a-f]{32}", ident):
            r = self.call(f"read/{kind}/{ident}")
        else:
            site = urllib.parse.quote(SITE_NAME)
            r = self.call(f"read/{kind}/{site}/{urllib.parse.quote(ident.lstrip('/'), safe='/()')}")
        if not r.get("success"):
            return None
        return r["asset"]

    def exists_any(self, path: str) -> tuple[str, str] | None:
        """(type, id) of whatever asset lives at this site path, or None."""
        for kind in ("file", "folder", "page", "symlink"):
            a = self.read(kind, path)
            if a:
                inner = next(iter(a.values()))
                return kind, inner["id"]
        return None

    # writes --------------------------------------------------------------
    def create(self, kind: str, spec: dict) -> str:
        spec = {"siteName": SITE_NAME, **spec}
        r = self.call("create", {"asset": {kind: spec}})
        if not r.get("success"):
            raise CascadeError(f"create {kind} {spec.get('parentFolderPath')}/{spec.get('name')}: {r.get('message')}")
        return r["createdAssetId"]

    def edit(self, asset: dict) -> None:
        r = self.call("edit", {"asset": asset})
        if not r.get("success"):
            raise CascadeError(f"edit: {r.get('message')}")

    def publish(self, kind: str, ident: str, unpublish: bool = False) -> None:
        body = {"publishInformation": {"unpublish": True}} if unpublish else {}
        r = self.call(f"publish/{kind}/{ident}", body)
        if not r.get("success"):
            raise CascadeError(f"{'un' if unpublish else ''}publish {kind} {ident}: {r.get('message')}")

    def delete(self, kind: str, ident: str, unpublish: bool = True) -> None:
        body = {"deleteParameters": {"unpublish": unpublish, "doWorkflow": False}}
        r = self.call(f"delete/{kind}/{ident}", body)
        if not r.get("success"):
            raise CascadeError(f"delete {kind} {ident}: {r.get('message')}")

    def move(self, kind: str, ident: str, dest_folder_id: str | None = None,
             new_name: str | None = None, unpublish: bool = False) -> dict:
        params: dict = {"doWorkflow": False, "unpublish": unpublish}
        if dest_folder_id:
            params["destinationContainerIdentifier"] = {"id": dest_folder_id, "type": "folder"}
        if new_name:
            params["newName"] = new_name
        return self.call(f"move/{kind}/{ident}", {"moveParameters": params})


# ---------------------------------------------------------------- encoding

def encode_data(b: bytes, mode: str):
    if mode == "base64":
        return base64.b64encode(b).decode("ascii")
    if mode == "uint8":
        return list(b)
    if mode == "int8":
        return [x - 256 if x > 127 else x for x in b]
    raise ValueError(f"unknown encoding {mode!r}; run `probe` first")


def decode_data(v) -> bytes:
    if v is None:
        return b""
    if isinstance(v, str):
        return base64.b64decode(v)
    return bytes((x + 256) % 256 for x in v)


def asset_bytes(inner: dict) -> bytes:
    """Bytes of a File asset as returned by read (text or data form)."""
    if inner.get("text") is not None:
        return inner["text"].encode("utf-8")
    return decode_data(inner.get("data"))


# ----------------------------------------------------------------- manifest

class Manifest:
    """Ownership record: path -> {id, sha256, ...}. Lives in Cascade + local cache."""

    def __init__(self, cx: Cascade, prefix: str, store: str = "cascade"):
        self.cx = cx
        self.prefix = prefix
        self.store = store
        self.name = f"manifest-{prefix or 'root'}.json"
        self.local = CACHE_DIR / self.name
        self.remote_id: str | None = None
        self.data: dict = {"version": 1, "prefix": prefix, "updated": None,
                           "meta": {}, "folders": {}, "files": {}}
        self._dirty = 0

    def load(self) -> None:
        remote = local = None
        if self.store == "cascade":
            a = self.cx.read("file", f"{MANIFEST_FOLDER}/{self.name}")
            if a:
                inner = a["file"]
                self.remote_id = inner["id"]
                try:
                    remote = json.loads(asset_bytes(inner).decode("utf-8"))
                except ValueError:
                    remote = None
        if self.local.exists():
            local = json.loads(self.local.read_text(encoding="utf-8"))
        cands = [m for m in (remote, local) if m]
        if cands:
            self.data = max(cands, key=lambda m: m.get("updated") or "")

    def save(self, force_remote: bool = False) -> None:
        self.data["updated"] = now()
        CACHE_DIR.mkdir(exist_ok=True)
        tmp = self.local.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.local)
        self._dirty += 1
        if self.store == "cascade" and (force_remote or self._dirty % 25 == 0):
            self._push()
            self._dirty = 0

    def _push(self) -> None:
        payload = json.dumps(self.data, indent=1, sort_keys=True)
        enc = self.data["meta"].get("encoding")
        if self.remote_id:
            a = self.cx.read("file", self.remote_id)
            inner = a["file"]
            if inner.get("text") is not None or not enc:
                inner["text"] = payload
                inner.pop("data", None)
            else:
                inner["data"] = encode_data(payload.encode(), enc)
                inner.pop("text", None)
            inner["shouldBePublished"] = False
            self.cx.edit(a)
            return
        if not self.cx.read("folder", MANIFEST_FOLDER):
            self.cx.create("folder", {"name": MANIFEST_FOLDER, "parentFolderPath": "/",
                                      "shouldBePublished": False, "shouldBeIndexed": False})
        self.remote_id = self.cx.create("file", {
            "name": self.name, "parentFolderPath": f"/{MANIFEST_FOLDER}",
            "shouldBePublished": False, "shouldBeIndexed": False,
            "rewriteLinks": False, "text": payload})

    @property
    def meta(self) -> dict:
        return self.data["meta"]

    @property
    def files(self) -> dict:
        return self.data["files"]

    @property
    def folders(self) -> dict:
        return self.data["folders"]


# ------------------------------------------------------------------ helpers

def load_key(path: str | None) -> str:
    k = os.environ.get("CASCADE_API_KEY")
    if not k:
        p = Path(path or "~/.cascade/api_key").expanduser()
        if not p.exists():
            sys.exit("error: no CASCADE_API_KEY and no ~/.cascade/api_key")
        k = p.read_text().strip()
    return k


def cascade_path(prefix: str, rel: str) -> str:
    return f"{prefix}/{rel}" if prefix else rel


def parent_and_name(cpath: str) -> tuple[str, str]:
    parent, _, name = cpath.rpartition("/")
    return ("/" + parent if parent else "/"), name


def live_url(base: str, cpath: str) -> str:
    return base.rstrip("/") + "/" + cpath


def fetch_live(url: str) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                               "User-Agent": "cascade-sync/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, b"", dict(e.headers or {})
    except (urllib.error.URLError, OSError):
        return 0, b"", {}


def poll_live(url: str, want_sha: str | None = None, want_status: int | None = None,
              timeout: int = 180, interval: int = 5) -> bool:
    """Wait until the live URL matches (a sha, or a status like 404)."""
    deadline = time.time() + timeout
    while True:
        status, body, _ = fetch_live(url)
        if want_status is not None and status == want_status:
            return True
        if want_sha is not None and status == 200 and sha256(body) == want_sha:
            return True
        if time.time() > deadline:
            return False
        time.sleep(interval)


def is_never_touch(cpath: str) -> bool:
    for nt in NEVER_TOUCH:
        if cpath == nt or cpath.startswith(nt + "/"):
            return True
    return False


def walk_site(site: Path) -> dict[str, Path]:
    out = {}
    for p in sorted(site.rglob("*")):
        if p.is_file() and p.name != ".DS_Store":
            out[p.relative_to(site).as_posix()] = p
    return out


def in_scope(rel: str, scopes: list[str], excludes: list[str]) -> bool:
    if any(fnmatch.fnmatch(rel, e) or rel.startswith(e.rstrip("/") + "/") for e in excludes):
        return False
    if not scopes:
        return True
    for s in scopes:
        if rel == s or (s.endswith("/") and rel.startswith(s)) or fnmatch.fnmatch(rel, s):
            return True
    return False


ASSET_REF = re.compile(r'(?:href|src)="([^"#?]*?assets/[^"#?]+)"')


def referenced_assets(site: Path, files: dict[str, Path], selected: list[str]) -> list[str]:
    found = set()
    for rel in selected:
        if not rel.endswith((".html", ".md")):
            continue
        text = files[rel].read_text(encoding="utf-8", errors="replace")
        for ref in ASSET_REF.findall(text):
            name = ref.split("assets/", 1)[1]
            cand = f"assets/{name}"
            if cand in files:
                found.add(cand)
    return sorted(found)


# --------------------------------------------------------------------- plan

def build_plan(cx: Cascade, man: Manifest, site: Path, prefix: str, scopes: list[str],
               excludes: list[str], with_assets: bool, allow_edit: set[str]) -> dict:
    files = walk_site(site)
    selected = [r for r in files if in_scope(r, scopes, excludes)]
    if with_assets:
        for a in referenced_assets(site, files, selected):
            if a not in selected and not any(fnmatch.fnmatch(a, e) for e in excludes):
                selected.append(a)
    selected.sort()

    plan = {"create_folders": [], "create": [], "edit": [], "skip": [], "delete": [],
            "collisions": [], "refused": []}
    seen_folders = set()

    for rel in selected:
        cpath = cascade_path(prefix, rel)
        if is_never_touch(cpath):
            plan["refused"].append((cpath, "never_touch"))
            continue
        digest = sha256(files[rel].read_bytes())
        entry = man.files.get(rel)
        # folders to ensure
        parts = cpath.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            f = "/".join(parts[:i])
            frel = "/".join(rel.split("/")[:i]) if len(rel.split("/")) > i else None
            if f in seen_folders:
                continue
            seen_folders.add(f)
            if f in man.folders or (frel and frel in man.folders):
                continue
            hit = cx.exists_any(f)
            if hit and hit[0] == "folder":
                man.folders[f] = {"id": hit[1], "created": False}
            elif hit:
                plan["collisions"].append((f, f"{hit[0]} {hit[1]} occupies the folder name"))
            else:
                plan["create_folders"].append(f)
        if entry:
            if entry.get("sha256") == digest and entry.get("published", True):
                plan["skip"].append(rel)
            else:
                plan["edit"].append((rel, digest))
            continue
        if rel in PROTECTED or cpath in PROTECTED:
            if rel in allow_edit or cpath in allow_edit:
                plan["edit"].append((rel, digest))
            else:
                plan["collisions"].append((cpath, f"protected file {PROTECTED.get(rel) or PROTECTED.get(cpath)}; use adopt / --allow-edit"))
            continue
        # A file inside a folder we are about to create cannot collide with
        # anything; skip the four reads per path that check would cost.
        parent_new = parent_and_name(cpath)[0].lstrip("/") in plan["create_folders"]
        if not parent_new:
            hit = cx.exists_any(cpath)
            if hit:
                plan["collisions"].append((cpath, f"{hit[0]} {hit[1]} already exists (not in manifest)"))
                continue
            if cpath.endswith(".html"):
                shadow = cx.read("page", cpath[:-5])
                if shadow:
                    plan["collisions"].append((cpath, f"page {shadow['page']['id']} publishes to the same URL"))
                    continue
        plan["create"].append((rel, digest))

    for rel, entry in man.files.items():
        if rel not in files and in_scope(rel, scopes, excludes) and not entry.get("protected"):
            plan["delete"].append(rel)
    return plan


def print_plan(plan: dict, prefix: str) -> None:
    for f in plan["create_folders"]:
        log(f"  CREATE folder  {f}")
    for rel, _ in plan["create"]:
        log(f"  CREATE file    {cascade_path(prefix, rel)}")
    for rel, _ in plan["edit"]:
        log(f"  EDIT   file    {cascade_path(prefix, rel)}")
    for rel in plan["delete"]:
        log(f"  DELETE file    {cascade_path(prefix, rel)}")
    for p, why in plan["refused"]:
        log(f"  REFUSE         {p}  ({why})")
    for p, why in plan["collisions"]:
        log(f"  COLLISION      {p}  ({why})")
    log(f"  -- {len(plan['create_folders'])} folders, {len(plan['create'])} create, "
        f"{len(plan['edit'])} edit, {len(plan['skip'])} skip, {len(plan['delete'])} delete, "
        f"{len(plan['collisions'])} collision(s), {len(plan['refused'])} refused")


# --------------------------------------------------------------------- sync

def file_spec(man: Manifest, cpath: str, b: bytes, publish: bool = True) -> dict:
    parent, name = parent_and_name(cpath)
    spec = {"name": name, "parentFolderPath": parent,
            "shouldBePublished": publish, "shouldBeIndexed": False, "rewriteLinks": False}
    enc = man.meta.get("encoding")
    ext = Path(name).suffix.lower()
    if ext in TEXT_EXT and not man.meta.get("data_ok_for_text", True):
        spec["text"] = b.decode("utf-8")
    else:
        spec["data"] = encode_data(b, enc)
    if man.meta.get("file_metadata_set"):
        spec["metadataSetPath"] = man.meta["file_metadata_set"]
    return spec


def do_sync(cx: Cascade, man: Manifest, site: Path, prefix: str, plan: dict,
            publish_mode: str, verify_base: str | None, force: bool) -> int:
    if plan["collisions"] or plan["refused"]:
        log("refusing to sync: resolve collisions/refusals first")
        return 1
    if not man.meta.get("encoding"):
        log("refusing to sync: encoding unknown — run `probe` first")
        return 1
    files = walk_site(site)
    created_folders: list[str] = []
    journal = CACHE_DIR / f"journal-{prefix or 'root'}-{now().replace(':', '')}.jsonl"
    CACHE_DIR.mkdir(exist_ok=True)

    def jot(**kw):
        with journal.open("a") as fh:
            fh.write(json.dumps({"ts": now(), **kw}) + "\n")

    # 1. folders, parents first
    for f in sorted(plan["create_folders"], key=lambda p: p.count("/")):
        parent, name = parent_and_name(f)
        spec = {"name": name, "parentFolderPath": parent,
                "shouldBePublished": True, "shouldBeIndexed": False}
        if man.meta.get("folder_metadata_set"):
            spec["metadataSetPath"] = man.meta["folder_metadata_set"]
        fid = cx.create("folder", spec)
        man.folders[f] = {"id": fid, "created": True}
        created_folders.append(f)
        jot(op="create_folder", path=f, id=fid)
        log(f"  created folder {f}")
        man.save()

    # 2. files
    to_publish: list[tuple[str, str]] = []  # (rel, id)
    for rel, digest in plan["create"]:
        cpath = cascade_path(prefix, rel)
        b = files[rel].read_bytes()
        fid = cx.create("file", file_spec(man, cpath, b))
        back = cx.read("file", fid)["file"]
        if sha256(asset_bytes(back)) != digest:
            log(f"  !! read-back mismatch for {cpath}; stopping")
            man.files[rel] = {"id": fid, "sha256": None, "size": len(b), "published": False}
            man.save(force_remote=True)
            return 1
        man.files[rel] = {"id": fid, "sha256": digest, "size": len(b), "published": False,
                          "synced": now()}
        to_publish.append((rel, fid))
        jot(op="create_file", path=cpath, id=fid, sha256=digest, bytes=len(b))
        log(f"  created {cpath}  ({len(b):,} B)")
        man.save()

    for rel, digest in plan["edit"]:
        cpath = cascade_path(prefix, rel)
        entry = man.files.get(rel) or {"id": PROTECTED.get(rel) or PROTECTED.get(cpath)}
        a = cx.read("file", entry["id"])
        inner = a["file"]
        who = inner.get("lastModifiedBy")
        if (man.meta.get("api_user") and who and who != man.meta["api_user"]
                and rel in man.files and not force):
            log(f"  !! {cpath} was last modified by {who!r} in Cascade; refusing (use --force)")
            return 1
        if entry.get("sha256") is None and rel in PROTECTED and "backup" not in entry:
            entry["backup"] = {k: v for k, v in inner.items() if k in ("text", "data")}
        b = files[rel].read_bytes()
        ext = Path(rel).suffix.lower()
        if inner.get("text") is not None and (ext in TEXT_EXT or not man.meta.get("data_ok_for_text", True)):
            inner["text"] = b.decode("utf-8")
            inner.pop("data", None)
        else:
            inner["data"] = encode_data(b, man.meta["encoding"])
            inner.pop("text", None)
        inner["rewriteLinks"] = False
        inner["shouldBeIndexed"] = False
        inner["shouldBePublished"] = True
        cx.edit(a)
        man.files[rel] = {**entry, "sha256": digest, "size": len(b), "published": False,
                          "synced": now()}
        to_publish.append((rel, entry["id"]))
        jot(op="edit_file", path=cpath, id=entry["id"], sha256=digest, bytes=len(b))
        log(f"  edited  {cpath}  ({len(b):,} B)")
        man.save()

    # 3. publish
    if publish_mode != "none":
        top_created = [f for f in created_folders
                       if parent_and_name(f)[0].lstrip("/") not in created_folders
                       and not any(f.startswith(g + "/") for g in created_folders if g != f)]
        for f in top_created:
            cx.publish("folder", man.folders[f]["id"])
            jot(op="publish_folder", path=f, id=man.folders[f]["id"])
            log(f"  published folder {f} (recursive)")
        for rel, fid in to_publish:
            cpath = cascade_path(prefix, rel)
            if any(cpath.startswith(f + "/") for f in top_created):
                continue
            cx.publish("file", fid)
            jot(op="publish_file", path=cpath, id=fid)
        log(f"  queued {len(to_publish)} file publish(es)")

    # 4. verify live
    if verify_base and to_publish:
        bad = []
        # the last-queued item gates the whole queue; wait long for it
        for i, (rel, fid) in enumerate(reversed(to_publish)):
            cpath = cascade_path(prefix, rel)
            if Path(rel).name.startswith("."):
                man.files[rel]["published"] = True
                continue
            ok = poll_live(live_url(verify_base, cpath), want_sha=man.files[rel]["sha256"],
                           timeout=600 if i == 0 else 120)
            man.files[rel]["published"] = ok
            man.files[rel]["live_ok"] = ok
            if not ok:
                bad.append(cpath)
        man.save(force_remote=True)
        if bad:
            log(f"  !! {len(bad)} file(s) not live/identical after publish:")
            for p in bad:
                log(f"     {p}")
            return 1
        log(f"  verified {len(to_publish)} file(s) live and byte-identical")
    else:
        for rel, _ in to_publish:
            man.files[rel]["published"] = publish_mode != "none"
        man.save(force_remote=True)

    # 5. deletes (only after everything else verified)
    if plan["delete"]:
        n = len(plan["delete"])
        if n > 50 or n > 0.25 * max(len(man.files), 1):
            log(f"  !! refusing to delete {n} files without --allow-mass-delete")
            return 1
        remove_paths(cx, man, prefix, plan["delete"], verify_base or LIVE_BASE, jot)
    return 0


def remove_paths(cx: Cascade, man: Manifest, prefix: str, rels: list[str], base: str, jot) -> None:
    for rel in rels:
        entry = man.files.get(rel)
        if not entry or entry.get("protected"):
            continue
        cpath = cascade_path(prefix, rel)
        cx.publish("file", entry["id"], unpublish=True)
        gone = poll_live(live_url(base, cpath), want_status=404, timeout=180)
        if not gone:
            log(f"  !! {cpath} still live after unpublish; leaving asset in place")
            continue
        cx.delete("file", entry["id"], unpublish=True)
        del man.files[rel]
        jot(op="delete_file", path=cpath, id=entry["id"])
        log(f"  removed {cpath}")
        man.save()
    # created folders now empty of our files
    for f in sorted([f for f, e in man.folders.items() if e.get("created")],
                    key=lambda p: -p.count("/")):
        still = any(cascade_path(prefix, r).startswith(f + "/") for r in man.files)
        if still:
            continue
        a = cx.read("folder", man.folders[f]["id"])
        if a and a["folder"].get("children"):
            continue  # someone else's content lives there now
        cx.delete("folder", man.folders[f]["id"], unpublish=True)
        del man.folders[f]
        jot(op="delete_folder", path=f)
        log(f"  removed empty folder {f}")
        man.save()
    man.save(force_remote=True)


# -------------------------------------------------------------------- probe

def do_probe(cx: Cascade, man: Manifest, args) -> int:
    """Learn the API's rules inside a throwaway folder, then leave no trace."""
    base = args.verify_live or LIVE_BASE
    R: dict = {}
    P = PROBE_FOLDER

    def live(p):
        return live_url(base, p)

    def record(k, v):
        R[k] = v
        log(f"    -> {k} = {v!r}")

    control = {p: sha256(fetch_live(live(p))[1]) for p in CONTROL_SET}
    log("P0  read encoding")
    a = cx.read("file", "images/brutus.png")["file"]
    record("read_encoding", "int8" if a["data"][0] < 0 else "uint8")
    record("file_metadata_set_seen", a.get("metadataSetPath"))

    if cx.exists_any(P):
        log(f"  probe folder {P} already exists — remove it first"); return 1
    log("P1  create folder")
    fid = cx.create("folder", {"name": P, "parentFolderPath": "/",
                               "shouldBePublished": True, "shouldBeIndexed": False})
    fb = cx.read("folder", fid)["folder"]
    record("folder_metadata_set", fb.get("metadataSetPath"))
    created: list[tuple[str, str, str]] = [("folder", fid, P)]

    png = (ROOT / "docs" / "assets" / "carc-lockup-dark.png").read_bytes()
    png_sha = sha256(png)
    log("P2  binary encodings")
    working = []
    for mode in ("base64", "uint8", "int8"):
        name = f"p-{mode}.png"
        try:
            i = cx.create("file", {"name": name, "parentFolderPath": f"/{P}",
                                   "shouldBePublished": True, "shouldBeIndexed": False,
                                   "rewriteLinks": False, "data": encode_data(png, mode)})
            created.append(("file", i, f"{P}/{name}"))
            back = cx.read("file", i)["file"]
            api_ok = sha256(asset_bytes(back)) == png_sha
            cx.publish("file", i)
            live_ok = poll_live(live(f"{P}/{name}"), want_sha=png_sha, timeout=120)
            log(f"    {mode}: api_roundtrip={api_ok} live={live_ok}")
            if api_ok and live_ok:
                working.append(mode)
                R.setdefault("api_user", back.get("lastModifiedBy"))
                R.setdefault("file_metadata_set", back.get("metadataSetPath"))
        except CascadeError as e:
            log(f"    {mode}: rejected ({str(e)[:120]})")
    if not working:
        log("  !! no binary encoding works — stop and escalate"); R["encoding"] = None
    else:
        record("encoding", working[0])
        record("encodings_ok", working)
    enc = R.get("encoding") or "uint8"

    log("P3  html fidelity + link rewriting")
    html = ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>probe ☾ ☀ → ©</title><link rel=\"canonical\" href=\"https://carc.unm.edu/x/\">"
            "</head><body><a href=\"../about/\">a</a> <a href=\"/assets/unm.ico\">b</a> "
            "<img src=\"../../assets/img/y.png\" alt=\"\"> <a href=\"index.md\">c</a> "
            "<a href=\"page.html?x=1\">d</a></body></html>\n").encode("utf-8")
    for name, extra in (("probe.html", {"rewriteLinks": False}), ("probe-rw.html", {})):
        i = cx.create("file", {"name": name, "parentFolderPath": f"/{P}", "shouldBePublished": True,
                               "shouldBeIndexed": False, "data": encode_data(html, enc), **extra})
        created.append(("file", i, f"{P}/{name}"))
        cx.publish("file", i)
        ok = poll_live(live(f"{P}/{name}"), want_sha=sha256(html), timeout=120)
        record("html_exact_" + ("rw_false" if extra else "rw_default"), ok)
    R["data_ok_for_text"] = bool(R.get("html_exact_rw_false"))

    log("P4  names + .htaccess in a sandbox")
    marker = b"<!doctype html><title>probe 404</title><p>PROBE-404-MARKER</p>\n"
    ht = (f"ErrorDocument 404 /{P}/404.html\nOptions -Indexes\n"
          "AddType text/markdown .md\nAddCharset UTF-8 .md .txt\n").encode()
    names = {"404.html": marker, ".htaccess": ht, "bundle.49251538.min.js": b"//js\n",
             "Sequential.R": b"# r\n", "POSCAR": b"poscar\n", "probe.md": "# md ☾\n".encode(),
             "search.json": b'{"docs":[]}\n', "x" * 63 + ".txt": b"long\n"}
    sub = cx.create("folder", {"name": "sub", "parentFolderPath": f"/{P}",
                               "shouldBePublished": True, "shouldBeIndexed": False})
    created.append(("folder", sub, f"{P}/sub"))
    names_ok = {}
    for name, body in names.items():
        try:
            i = cx.create("file", {"name": name, "parentFolderPath": f"/{P}", "shouldBePublished": True,
                                   "shouldBeIndexed": False, "rewriteLinks": False,
                                   "data": encode_data(body, enc)})
            created.append(("file", i, f"{P}/{name}"))
            names_ok[name] = True
        except CascadeError as e:
            names_ok[name] = False
            log(f"    {name!r} rejected: {str(e)[:100]}")
    try:
        cx.create("file", {"name": "has space.txt", "parentFolderPath": f"/{P}",
                           "shouldBePublished": False, "shouldBeIndexed": False, "data": encode_data(b"x", enc)})
        names_ok["has space.txt"] = True
    except CascadeError as e:
        names_ok["has space.txt"] = False
    record("names_ok", names_ok)
    i = cx.create("file", {"name": "index.html", "parentFolderPath": f"/{P}/sub", "shouldBePublished": True,
                           "shouldBeIndexed": False, "rewriteLinks": False, "data": encode_data(b"<p>sub</p>\n", enc)})
    created.append(("file", i, f"{P}/sub/index.html"))
    cx.publish("folder", fid)
    poll_live(live(f"{P}/404.html"), want_sha=sha256(marker), timeout=300)
    st, body, hdrs = fetch_live(live(f"{P}/nope"))
    record("options_indexes_safe", st == 404 and b"PROBE-404-MARKER" in body)
    if st >= 500:
        log("    !! sandbox .htaccess caused 5xx — unpublishing it now")
        hid = next(i for k, i, p in created if p == f"{P}/.htaccess")
        cx.publish("file", hid, unpublish=True)
    st2, body2, _ = fetch_live(live(f"{P}/"))
    record("dir_listing_suppressed", b"Index of" not in body2)
    st3, _, h3 = fetch_live(live(f"{P}/probe.md"))
    record("md_content_type", h3.get("Content-Type"))
    st4, _, _ = fetch_live(live(f"{P}/sub/"))
    record("nested_dir_index", st4 == 200)

    log("P5  edit a text-ext file by sending data")
    mid = next(i for k, i, p in created if p == f"{P}/probe.md")
    a = cx.read("file", mid)
    inner = a["file"]
    record("md_read_form", "text" if inner.get("text") is not None else "data")
    newmd = "# md ☾ edited\n".encode()
    inner["data"] = encode_data(newmd, enc); inner.pop("text", None); inner["rewriteLinks"] = False
    try:
        cx.edit(a); cx.publish("file", mid)
        record("edit_text_via_data", poll_live(live(f"{P}/probe.md"), want_sha=sha256(newmd), timeout=120))
    except CascadeError as e:
        record("edit_text_via_data", False); log(f"    {str(e)[:120]}")

    if not args.skip_size_ladder:
        log("P6  size ladder")
        maxok = 0
        for mb in (1, 2, 5, 10, 20):
            blob = os.urandom(mb * 1_000_000)
            name = f"s{mb}.bin"
            t0 = time.time()
            try:
                i = cx.create("file", {"name": name, "parentFolderPath": f"/{P}", "shouldBePublished": True,
                                       "shouldBeIndexed": False, "rewriteLinks": False, "data": encode_data(blob, enc)})
                created.append(("file", i, f"{P}/{name}"))
                cx.publish("file", i)
                ok = poll_live(live(f"{P}/{name}"), want_sha=sha256(blob), timeout=600)
                log(f"    {mb} MB: create ok, live={ok}, {time.time()-t0:.0f}s")
                if not ok:
                    break
                maxok = mb * 1_000_000
            except CascadeError as e:
                log(f"    {mb} MB: FAILED {str(e)[:160]}"); break
        record("max_body_bytes", maxok)

    log("P7  nested file publish creates dirs?")
    deep = cx.create("folder", {"name": "deep", "parentFolderPath": f"/{P}/sub",
                                "shouldBePublished": True, "shouldBeIndexed": False})
    created.append(("folder", deep, f"{P}/sub/deep"))
    i = cx.create("file", {"name": "deep.txt", "parentFolderPath": f"/{P}/sub/deep", "shouldBePublished": True,
                           "shouldBeIndexed": False, "rewriteLinks": False, "data": encode_data(b"deep\n", enc)})
    created.append(("file", i, f"{P}/sub/deep/deep.txt"))
    cx.publish("file", i)
    record("file_publish_makes_dirs", poll_live(live(f"{P}/sub/deep/deep.txt"), want_sha=sha256(b"deep\n"), timeout=120))

    log("P8  unpublish + delete-with-unpublish")
    cx.publish("file", mid, unpublish=True)
    record("unpublish_works", poll_live(live(f"{P}/probe.md"), want_status=404, timeout=120))
    sid = next(i for k, i, p in created if p == f"{P}/search.json")
    cx.delete("file", sid, unpublish=True)
    record("delete_unpublish_works", poll_live(live(f"{P}/search.json"), want_status=404, timeout=120))
    created = [c for c in created if c[1] != sid]

    log("P9  move / rename")
    rid = next(i for k, i, p in created if p == f"{P}/probe-rw.html")
    try:
        cx.move("file", rid, new_name="probe-renamed.html")
        record("rename_works", bool(cx.read("file", f"{P}/probe-renamed.html")))
    except CascadeError as e:
        record("rename_works", False); log(f"    {str(e)[:140]}")
    try:
        cx.move("file", rid, dest_folder_id=sub)
        record("move_works", bool(cx.read("file", f"{P}/sub/probe-renamed.html") or cx.read("file", f"{P}/sub/probe-rw.html")))
    except CascadeError as e:
        record("move_works", False); log(f"    {str(e)[:140]}")

    log("P10 does a folder republish rewrite unchanged files?")
    _, _, h1 = fetch_live(live(f"{P}/p-{enc}.png"))
    time.sleep(2); cx.publish("folder", fid); time.sleep(20)
    _, _, h2 = fetch_live(live(f"{P}/p-{enc}.png"))
    record("folder_publish_retransfers", h1.get("Last-Modified") != h2.get("Last-Modified"))

    log("P11 research/ workflow check")
    try:
        pid = cx.create("file", {"name": "_probe.txt", "parentFolderPath": "/research", "shouldBePublished": False,
                                 "shouldBeIndexed": False, "rewriteLinks": False, "data": encode_data(b"x\n", enc)})
        cx.delete("file", pid, unpublish=False)
        record("research_create_ok", True)
    except CascadeError as e:
        record("research_create_ok", False); log(f"    {str(e)[:140]}")

    log("P12 clean the orphan /_publish-test.txt")
    if fetch_live(live("_publish-test.txt"))[0] == 200 and not cx.exists_any("_publish-test.txt"):
        tid = cx.create("file", {"name": "_publish-test.txt", "parentFolderPath": "/", "shouldBePublished": True,
                                 "shouldBeIndexed": False, "rewriteLinks": False, "data": encode_data(b"cleanup\n", enc)})
        cx.publish("file", tid)
        poll_live(live("_publish-test.txt"), want_sha=sha256(b"cleanup\n"), timeout=120)
        cx.publish("file", tid, unpublish=True)
        gone = poll_live(live("_publish-test.txt"), want_status=404, timeout=120)
        cx.delete("file", tid, unpublish=True)
        record("orphan_cleaned", gone and not cx.exists_any("_publish-test.txt"))
    else:
        record("orphan_cleaned", "n/a")

    log("P13 teardown")
    cx.publish("folder", fid, unpublish=True)
    cx.delete("folder", fid, unpublish=True)
    gone = all(poll_live(live(p), want_status=404, timeout=180)
               for p in (f"{P}/p-{enc}.png", f"{P}/404.html", f"{P}/sub/index.html"))
    record("probe_folder_gone", gone and not cx.exists_any(P))
    after = {p: sha256(fetch_live(live(p))[1]) for p in CONTROL_SET}
    record("control_set_unchanged", after == control)

    man.meta.update({k: v for k, v in R.items() if k in (
        "encoding", "encodings_ok", "api_user", "file_metadata_set", "folder_metadata_set",
        "data_ok_for_text", "options_indexes_safe", "max_body_bytes", "unpublish_works",
        "delete_unpublish_works", "rename_works", "move_works", "file_publish_makes_dirs",
        "folder_publish_retransfers", "names_ok", "md_content_type")})
    man.meta["probed_at"] = now()
    man.save(force_remote=True)
    log("\nprobe results:")
    for k, v in R.items():
        log(f"  {k:28} {v!r}")
    return 0 if R.get("encoding") and R.get("unpublish_works") else 1


# ---------------------------------------------------------------- commands

def cmd_preflight(cx: Cascade, man: Manifest, args) -> int:
    ok = True
    d = cx.read("destination", DESTINATION_ID)
    dd = d["destination"] if d else {}
    log(f"destination enabled={dd.get('enabled')} directory={dd.get('directory')!r}")
    ok &= bool(dd.get("enabled")) and dd.get("directory") == DESTINATION_DIR
    s = cx.read("site", "3e9a0476c0a8508c0d511691936cc560")["site"]
    log(f"site scheduledPublishing={s.get('usesScheduledPublishing')} linkRewriting={s.get('linkRewriting')}")
    ok &= not s.get("usesScheduledPublishing")
    for p in args.expect_absent or []:
        hit = cx.exists_any(p)
        st = fetch_live(live_url(args.verify_live or LIVE_BASE, p))[0]
        log(f"expect absent {p!r}: cascade={'ABSENT' if not hit else hit} live=HTTP {st}")
        ok &= not hit and st in (404, 403)
    log(f"manifest: {len(man.files)} files, {len(man.folders)} folders, encoding={man.meta.get('encoding')}")
    log("PREFLIGHT " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def cmd_verify(cx: Cascade, man: Manifest, args) -> int:
    base = args.verify_live or LIVE_BASE
    bad = 0
    for rel, e in sorted(man.files.items()):
        if not in_scope(rel, args.scope, args.exclude) or Path(rel).name.startswith("."):
            continue
        st, body, _ = fetch_live(live_url(base, cascade_path(man.prefix, rel)))
        good = st == 200 and sha256(body) == e.get("sha256")
        bad += not good
        log(f"  {'ok ' if good else 'BAD'} {cascade_path(man.prefix, rel)}  HTTP {st}")
    log(f"verify: {bad} mismatch(es)")
    return 1 if bad else 0


def cmd_remove(cx: Cascade, man: Manifest, args) -> int:
    rels = [r for r in man.files if in_scope(r, args.scope, args.exclude)]
    if not args.scope and not args.all:
        log("refusing to remove everything without --all"); return 1
    log(f"removing {len(rels)} file(s)")
    remove_paths(cx, man, man.prefix, rels, args.verify_live or LIVE_BASE, lambda **kw: None)
    return 0


def cmd_adopt(cx: Cascade, man: Manifest, args) -> int:
    for rel in args.paths:
        cpath = cascade_path(man.prefix, rel)
        a = cx.read("file", cpath)
        if not a:
            log(f"  {cpath}: no such file"); continue
        inner = a["file"]
        man.files[rel] = {"id": inner["id"], "sha256": None, "adopted": True,
                          "protected": rel in PROTECTED}
        log(f"  adopted {cpath} -> {inner['id']}")
    man.save(force_remote=True)
    return 0


def cmd_retire_page(cx: Cascade, man: Manifest, args) -> int:
    a = cx.read("page", args.path)
    if not a:
        log(f"no page at {args.path}"); return 1
    pid = a["page"]["id"]
    hold = cx.read("folder", args.to)
    if not hold:
        hid = cx.create("folder", {"name": args.to, "parentFolderPath": "/",
                                   "shouldBePublished": False, "shouldBeIndexed": False})
        log(f"  created holding folder /{args.to}")
    else:
        hid = hold["folder"]["id"]
    if args.unpublishable:
        a["page"]["shouldBePublished"] = False
        cx.edit(a)
        log(f"  {args.path}: shouldBePublished=false")
    r = cx.move("page", pid, dest_folder_id=hid, unpublish=args.unpublish)
    log(f"  moved page {args.path} -> /{args.to}/ (unpublish={args.unpublish}): {r.get('success')}")
    return 0 if r.get("success") else 1


def cmd_tombstone(cx: Cascade, man: Manifest, args) -> int:
    base = args.verify_live or LIVE_BASE
    enc = man.meta.get("encoding") or "uint8"
    for p in args.paths:
        if cx.exists_any(p):
            log(f"  {p}: a Cascade asset exists — not an orphan"); continue
        if fetch_live(live_url(base, p))[0] != 200:
            log(f"  {p}: not live — nothing to remove"); continue
        parent, name = parent_and_name(p)
        tid = cx.create("file", {"name": name, "parentFolderPath": parent, "shouldBePublished": True,
                                 "shouldBeIndexed": False, "rewriteLinks": False,
                                 "data": encode_data(b"retired\n", enc)})
        cx.publish("file", tid)
        poll_live(live_url(base, p), want_sha=sha256(b"retired\n"), timeout=180)
        cx.publish("file", tid, unpublish=True)
        gone = poll_live(live_url(base, p), want_status=404, timeout=180)
        cx.delete("file", tid, unpublish=True)
        log(f"  {p}: {'removed' if gone else 'STILL LIVE'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preflight", "probe", "plan", "sync", "verify", "remove",
                                    "adopt", "retire-page", "tombstone"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--site", default=str(ROOT / "site"))
    ap.add_argument("--prefix", default="")
    ap.add_argument("--scope", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--with-referenced-assets", action="store_true")
    ap.add_argument("--allow-edit", action="append", default=[])
    ap.add_argument("--publish", choices=["changed", "none"], default="changed")
    ap.add_argument("--verify-live", nargs="?", const=LIVE_BASE, default=None)
    ap.add_argument("--manifest-store", choices=["cascade", "local"], default="cascade")
    ap.add_argument("--key-file", default=None)
    ap.add_argument("--pace", type=float, default=0.2)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-size-ladder", action="store_true")
    ap.add_argument("--expect-absent", action="append", default=[])
    ap.add_argument("--to", default="_retired")
    ap.add_argument("--unpublish", action="store_true")
    ap.add_argument("--unpublishable", action="store_true")
    args = ap.parse_args()
    if args.cmd == "retire-page":
        args.path = args.paths[0]

    cx = Cascade(load_key(args.key_file), pace=args.pace)
    man = Manifest(cx, args.prefix.strip("/"), store=args.manifest_store)
    man.load()

    if args.cmd == "preflight":
        return cmd_preflight(cx, man, args)
    if args.cmd == "probe":
        return do_probe(cx, man, args)
    if args.cmd in ("plan", "sync"):
        site = Path(args.site)
        if not site.is_dir():
            sys.exit(f"error: {site} is not a directory")
        plan = build_plan(cx, man, site, man.prefix, args.scope, args.exclude,
                          args.with_referenced_assets, set(args.allow_edit))
        print_plan(plan, man.prefix)
        if args.cmd == "plan":
            return 1 if plan["collisions"] or plan["refused"] else 0
        return do_sync(cx, man, site, man.prefix, plan, args.publish, args.verify_live, args.force)
    if args.cmd == "verify":
        return cmd_verify(cx, man, args)
    if args.cmd == "remove":
        return cmd_remove(cx, man, args)
    if args.cmd == "adopt":
        return cmd_adopt(cx, man, args)
    if args.cmd == "retire-page":
        return cmd_retire_page(cx, man, args)
    if args.cmd == "tombstone":
        return cmd_tombstone(cx, man, args)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CascadeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(3)
