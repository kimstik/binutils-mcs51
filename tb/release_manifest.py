#!/usr/bin/env python3
"""Assemble and verify the assets of a release before anything is published.

Everything a release consists of passes through here: the per-host archives the
build workflow produced, the two patches that are the actual deliverable, and a
SHA256SUMS covering all of them.  Nothing is copied on trust.

The host list is not written down here.  It is read out of the build workflow's
own matrix, so a host added to the build is released without a second list
needing to be edited, and a host that failed to upload its archive is a missing
asset rather than a quietly shorter release.

Every archive is opened and read:

  * exactly one top-level directory, named after the archive
  * bin/<target>-as and bin/<target>-ld inside it, so it is a toolchain
  * a COPYING*, because these are GPLv3 binaries
  * BUILD-INFO.txt, whose upstream version, upstream sha256 and port commit
    have to be the ones this release claims - which is what catches an archive
    built from another commit or against another binutils being published under
    this tag

Problems are collected and all of them are reported; any one of them is a
nonzero exit and no release.

  usage: release_manifest.py --workflow .github/workflows/build.yml
                             --downloads DIR --out DIR
                             --version 2.47 --sha256 <64 hex> --commit <40 hex>
                             --target i51-elf
                             --patch mcs51/additions.patch [--patch ...]
"""

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import zipfile

import yaml

PACK_EXT = {"tar": ".tar.gz", "zip": ".zip"}


def hosts_from_workflow(path):
    """The (name, extension) pairs the build workflow's matrix produces."""
    with open(path, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    include = wf["jobs"]["build"]["strategy"]["matrix"]["include"]
    out = []
    for entry in include:
        name = entry["name"]
        pack = entry.get("pack", "tar")
        if pack not in PACK_EXT:
            raise SystemExit(f"{path}: host {name} has unknown pack '{pack}'")
        out.append((name, PACK_EXT[pack]))
    if not out:
        raise SystemExit(f"{path}: the build matrix is empty")
    return out


def find_named(root, filename):
    """Every file called `filename' anywhere under `root'."""
    hits = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if filename in filenames:
            hits.append(os.path.join(dirpath, filename))
    return hits


def archive_members(path):
    """(top-level names, member paths, reader) of a .tar.gz or a .zip.

    The reader takes a member path and returns its bytes.
    """
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()

        def read(name):
            with zipfile.ZipFile(path) as zf_inner:
                return zf_inner.read(name)
    else:
        with tarfile.open(path, "r:gz") as tf:
            names = tf.getnames()

        def read(name):
            with tarfile.open(path, "r:gz") as tf_inner:
                handle = tf_inner.extractfile(name)
                if handle is None:
                    raise KeyError(name)
                return handle.read()

    names = [n.rstrip("/") for n in names if n.rstrip("/")]
    tops = {n.split("/", 1)[0] for n in names}
    return tops, names, read


def parse_build_info(text):
    fields = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def check_archive(path, host, args, problems):
    tops, names, read = archive_members(path)
    stem = os.path.basename(path)
    for ext in PACK_EXT.values():
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
    if tops != {stem}:
        problems.append(f"{host}: archive unpacks to {sorted(tops)}, expected only '{stem}/'")
        return
    inside = {n[len(stem) + 1:] for n in names if n.startswith(stem + "/")}

    def present(prefix):
        return any(n == prefix or n == prefix + ".exe" for n in inside)

    for tool in ("as", "ld"):
        if not present(f"bin/{args.target}-{tool}"):
            problems.append(f"{host}: no bin/{args.target}-{tool} in the archive")
    if not any(n.startswith("COPYING") for n in inside):
        problems.append(f"{host}: no COPYING* in the archive - GPLv3 binaries need one")
    if "BUILD-INFO.txt" not in inside:
        problems.append(f"{host}: no BUILD-INFO.txt in the archive")
        return

    info = parse_build_info(read(f"{stem}/BUILD-INFO.txt").decode("utf-8", "replace"))
    for key, want in (
        ("upstream-binutils", args.version),
        ("upstream-sha256", args.sha256),
        ("port-commit", args.commit),
        ("host", host),
    ):
        got = info.get(key)
        if got != want:
            problems.append(f"{host}: BUILD-INFO {key} is {got!r}, this release is {want!r}")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True, help="the build workflow to read the host matrix from")
    ap.add_argument("--downloads", required=True, help="directory the build artifacts were downloaded into")
    ap.add_argument("--out", required=True, help="directory to assemble the release assets in")
    ap.add_argument("--version", required=True, help="upstream binutils version")
    ap.add_argument("--sha256", required=True, help="upstream tarball sha256")
    ap.add_argument("--commit", required=True, help="the commit this release is cut from")
    ap.add_argument("--target", required=True, help="target alias the programs are prefixed with")
    ap.add_argument("--patch", action="append", default=[], help="a patch file to publish (repeatable)")
    args = ap.parse_args()

    problems = []
    os.makedirs(args.out, exist_ok=True)
    assets = []

    for host, ext in hosts_from_workflow(args.workflow):
        want = f"i51-binutils-{args.version}-{host}{ext}"
        hits = find_named(args.downloads, want)
        if len(hits) != 1:
            problems.append(
                f"{host}: expected exactly one {want} among the build artifacts, found {len(hits)}"
            )
            continue
        dest = os.path.join(args.out, want)
        shutil.copyfile(hits[0], dest)
        try:
            check_archive(dest, host, args, problems)
        except Exception as exc:                      # a corrupt archive reads as one problem
            problems.append(f"{host}: {want} could not be read: {exc}")
        assets.append(want)

    if not args.patch:
        problems.append("no patch was given: the patches are the deliverable")
    for src in args.patch:
        if not os.path.isfile(src):
            problems.append(f"patch {src} does not exist")
            continue
        if os.path.getsize(src) == 0:
            problems.append(f"patch {src} is empty")
            continue
        name = f"binutils-{args.version}-mcs51-{os.path.basename(src)}"
        shutil.copyfile(src, os.path.join(args.out, name))
        assets.append(name)

    if problems:
        for p in problems:
            print(f"::error::{p}")
        print(f"release_manifest: {len(problems)} problem(s), nothing may be published")
        return 1

    # SHA256SUMS covers every asset; it cannot cover itself, so it is written
    # last and is the one file whose integrity the release page itself carries.
    lines = []
    for name in sorted(assets):
        path = os.path.join(args.out, name)
        lines.append(f"{sha256_of(path)}  {name}")
    with open(os.path.join(args.out, "SHA256SUMS"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"release_manifest: {len(assets)} asset(s) + SHA256SUMS")
    for line in lines:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
