#!/usr/bin/env python3
"""
kirei asset contract check for glTF / GLB models. Standard library only, Python 3.8+.

Reports each model's node names, triangles, materials, textures (size and power of two),
file size and mirrored transforms, then checks the node contract: every node name a model is
expected to have. A missing node fails the run (exit 1), because a lookup such as C++
findNode(model, "name") or three.js getObjectByName("name") returns -1 or null without a word.

Usage:
  python -I "${CLAUDE_PLUGIN_ROOT}/scripts/asset-check.py" MODEL_OR_DIR... [options]

Where the expected names come from (combine freely):
  --expect a,b,c       names every model given must have
  --manifest FILE      JSON: {"turntable.glb": ["platter", "tonearm"], ...}; keys match a
                       model's file name or its path relative to the current folder
  --scan-code DIR      names the code passes to the lookup functions under DIR (repeatable).
                       A string literal counts; an UPPER_CASE constant is resolved when the
                       tree assigns it exactly one string literal. Anything else (a parameter,
                       a field, a name built at runtime) is listed as unresolved for a human
                       look, never guessed. Code names cannot say which model they mean, so
                       each one must exist in at least one of the models given.
  --lookup NAME        a lookup function to scan for (repeatable; default findNode and
                       getObjectByName)
  --include-tests      also scan test folders (off by default: tests name their own fixtures)

Exit codes: 0 contract met (unresolved call sites alone do not fail), 1 a node is missing,
2 bad arguments or a model that cannot be read. A value that cannot be measured prints
"not measured", never 0.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

CODE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".m",
            ".mm", ".cs", ".rs", ".go", ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
SKIP_DIRS = {".git", "node_modules", "build", "dist", "out", "external", "third_party",
             "thirdparty", "vendor", "__pycache__", ".venv", "venv", "target"}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testdata"}
DEFAULT_LOOKUPS = ["findNode", "getObjectByName"]


class ModelError(Exception):
    pass


# ---------------------------------------------------------------- model reading

def load_gltf(path):
    """Return (gltf json, bin chunk bytes or None)."""
    data = path.read_bytes()
    if data[:4] == b"glTF":
        if len(data) < 20:
            raise ModelError("truncated GLB header")
        version, length = struct.unpack_from("<II", data, 4)
        if version != 2:
            raise ModelError(f"GLB version {version}, only 2 is read")
        offset, doc, binary = 12, None, None
        while offset + 8 <= min(length, len(data)):
            size, kind = struct.unpack_from("<II", data, offset)
            chunk = data[offset + 8: offset + 8 + size]
            if kind == 0x4E4F534A:
                doc = json.loads(chunk.decode("utf-8"))
            elif kind == 0x004E4942 and binary is None:
                binary = chunk
            offset += 8 + size
        if doc is None:
            raise ModelError("GLB has no JSON chunk")
        return doc, binary
    try:
        return json.loads(data.decode("utf-8")), None
    except ValueError as exc:
        raise ModelError(f"not a GLB and not glTF JSON ({exc})")


def image_size(blob):
    """(width, height, format) from an image header, or (None, None, format)."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        w, h = struct.unpack_from(">II", blob, 16)
        return w, h, "png"
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack_from(">H", blob, i + 2)[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack_from(">HH", blob, i + 5)
                return w, h, "jpeg"
            i += 2 + seg
        return None, None, "jpeg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP" and len(blob) >= 30:
        kind = blob[12:16]
        if kind == b"VP8X":
            w = 1 + int.from_bytes(blob[24:27], "little")
            h = 1 + int.from_bytes(blob[27:30], "little")
            return w, h, "webp"
        if kind == b"VP8 ":
            w, h = struct.unpack_from("<HH", blob, 26)
            return w & 0x3FFF, h & 0x3FFF, "webp"
        if kind == b"VP8L":
            bits = int.from_bytes(blob[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1, "webp"
        return None, None, "webp"
    if blob[:12] == b"\xabKTX 20\xbb\r\n\x1a\n" and len(blob) >= 28:
        w, h = struct.unpack_from("<II", blob, 20)
        return w, h, "ktx2"
    return None, None, "unknown"


def image_bytes(doc, binary, image, base):
    """The image's first bytes, or None with a reason."""
    if "bufferView" in image:
        view = doc.get("bufferViews", [])[image["bufferView"]]
        if "EXT_meshopt_compression" in view.get("extensions", {}):
            return None, "compressed buffer view"
        if view.get("buffer", 0) != 0 or binary is None:
            return None, "external buffer"
        start = view.get("byteOffset", 0)
        return binary[start: start + min(view.get("byteLength", 0), 65536)], None
    uri = image.get("uri", "")
    if uri.startswith("data:"):
        import base64
        try:
            return base64.b64decode(uri.split(",", 1)[1])[:65536], None
        except (IndexError, ValueError):
            return None, "bad data URI"
    from urllib.parse import unquote
    file = base / unquote(uri)
    try:
        with open(file, "rb") as handle:
            return handle.read(65536), None
    except OSError:
        return None, f"missing file {uri}"


def triangles(doc):
    """Triangles drawn, counted per node that uses a mesh (from accessor counts, so it also
    works for meshopt and Draco files)."""
    accessors = doc.get("accessors", [])
    meshes = doc.get("meshes", [])

    def mesh_tris(mesh):
        total = 0
        for prim in mesh.get("primitives", []):
            mode = prim.get("mode", 4)
            if "indices" in prim:
                count = accessors[prim["indices"]].get("count", 0)
            elif "POSITION" in prim.get("attributes", {}):
                count = accessors[prim["attributes"]["POSITION"]].get("count", 0)
            else:
                continue
            if mode == 4:
                total += count // 3
            elif mode in (5, 6):
                total += max(count - 2, 0)
        return total

    used = [n["mesh"] for n in doc.get("nodes", []) if "mesh" in n]
    return sum(mesh_tris(meshes[i]) for i in used if i < len(meshes))


def mirrored(node):
    if "matrix" in node:
        m = node["matrix"]
        det = (m[0] * (m[5] * m[10] - m[9] * m[6]) - m[4] * (m[1] * m[10] - m[9] * m[2])
               + m[8] * (m[1] * m[6] - m[5] * m[2]))
        return det < 0
    s = node.get("scale", [1, 1, 1])
    return s[0] * s[1] * s[2] < 0


def describe(path):
    doc, binary = load_gltf(path)
    nodes = [n.get("name", f"<node {i}>") for i, n in enumerate(doc.get("nodes", []))]
    textures = []
    for i, image in enumerate(doc.get("images", [])):
        blob, why = image_bytes(doc, binary, image, path.parent)
        name = image.get("name") or image.get("uri") or f"image {i}"
        if blob is None:
            textures.append((name, None, None, f"not measured ({why})"))
            continue
        w, h, fmt = image_size(blob)
        if w is None:
            textures.append((name, None, None, f"not measured ({fmt} header not read)"))
        else:
            pow2 = all(v > 0 and v & (v - 1) == 0 for v in (w, h))
            textures.append((name, w, h, f"{fmt}{'' if pow2 else ', not a power of two'}"))
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "nodes": nodes,
        "triangles": triangles(doc),
        "materials": [m.get("name", f"<material {i}>")
                      for i, m in enumerate(doc.get("materials", []))],
        "textures": textures,
        "mirrored": [nodes[i] for i, n in enumerate(doc.get("nodes", [])) if mirrored(n)],
        "extensions": doc.get("extensionsRequired", []),
    }


# ---------------------------------------------------------------- code scanning

def code_files(root, include_tests):
    skip = SKIP_DIRS if include_tests else SKIP_DIRS | TEST_DIRS
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).parts
        if any(p.lower() in skip for p in rel[:-1]):
            continue
        if path.suffix.lower() in CODE_EXT and path.is_file():
            yield path


def call_args(text, start):
    """Split the argument list that opens at text[start] == '('. Returns (args, end)."""
    depth, quote, arg, args, i = 0, None, "", [], start
    while i < len(text):
        c = text[i]
        if quote:
            arg += c
            if c == "\\" and i + 1 < len(text):
                arg += text[i + 1]
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
            arg += c
        elif c in "([{":
            depth += 1
            if depth > 1:
                arg += c
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append(arg.strip())
                return args, i
            arg += c
        elif c == "," and depth == 1:
            args.append(arg.strip())
            arg = ""
        else:
            arg += c
        i += 1
    return None, i


LITERAL = re.compile(r"""^(?:[\w:]+\s*[({]\s*)?(["'`])((?:\\.|(?!\1).)*)\1\s*(?:sv|s)?\s*[)}]?$""")


def scan_code(roots, lookups, include_tests):
    """Return (names: {name: [site]}, unresolved: [(site, arg)])."""
    files = [f for r in roots for f in code_files(r, include_tests)]
    texts = {f: f.read_text(encoding="utf-8", errors="replace") for f in files}
    constants = {}
    define = re.compile(r"\b([A-Z][A-Z0-9_]+)\b(?:\s*\[\s*\])?\s*(?:=|\{|\()\s*"
                        r"""(?:[\w:]+\s*[({]\s*)?(["'])((?:\\.|(?!\2).)*)\2""")
    for text in texts.values():
        for m in define.finditer(text):
            constants.setdefault(m.group(1), set()).add(m.group(3))
    call = re.compile(r"\b(" + "|".join(re.escape(n) for n in lookups) + r")\s*\(")
    names, unresolved = {}, []
    for f, text in texts.items():
        for m in call.finditer(text):
            before = text[max(0, m.start() - 40): m.start()]
            if re.search(r"\b(int|auto|function|def|fn|void|Node\*?|Object3D)\s*$", before):
                continue  # the lookup's own declaration or definition
            args, _ = call_args(text, m.end() - 1)
            line = text.count("\n", 0, m.start()) + 1
            site = f"{f.as_posix()}:{line}"
            if not args or not args[-1]:
                continue
            arg = args[-1]
            lit = LITERAL.match(arg)
            ident = re.search(r"\b([A-Z][A-Z0-9_]+)$", arg)
            if lit:
                names.setdefault(lit.group(2), []).append(site)
            elif ident and len(constants.get(ident.group(1), ())) == 1:
                names.setdefault(next(iter(constants[ident.group(1)])), []).append(
                    f"{site} ({ident.group(1)})")
            else:
                why = (f"{ident.group(1)} has {len(constants.get(ident.group(1), ()))} "
                       "string definitions" if ident else "not a literal or a constant")
                unresolved.append((site, " ".join(arg.split()), why))
    return names, unresolved


# ---------------------------------------------------------------- report

def safe(text):
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def models_in(paths):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".glb", ".gltf"))
        else:
            out.append(p)
    return out


def main():
    parser = argparse.ArgumentParser(description="Check glTF/GLB models against the node "
                                     "names the code and manifests expect.")
    parser.add_argument("models", nargs="+", help=".glb/.gltf files or folders")
    parser.add_argument("--expect", action="append", default=[],
                        help="comma separated node names every model must have")
    parser.add_argument("--manifest", help='JSON {"file.glb": ["node", ...]}')
    parser.add_argument("--scan-code", action="append", default=[], metavar="DIR")
    parser.add_argument("--lookup", action="append", metavar="NAME")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    paths = models_in(args.models)
    if not paths:
        print("no .glb or .gltf files found", file=sys.stderr)
        return 2
    reports, broken = [], False
    for p in paths:
        try:
            reports.append(describe(p))
        except (OSError, ModelError, ValueError, KeyError, IndexError, struct.error) as exc:
            print(safe(f"UNREADABLE  {p}: {exc}"), file=sys.stderr)
            broken = True

    expected = {}  # model path -> {name: source}
    missing = []
    flat = [n.strip() for e in args.expect for n in e.split(",") if n.strip()]
    for r in reports:
        for n in flat:
            expected.setdefault(r["path"], {})[n] = "--expect"
    if args.manifest:
        try:
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(safe(f"bad manifest {args.manifest}: {exc}"), file=sys.stderr)
            return 2
        for key, names in manifest.items():
            hits = [r for r in reports if Path(r["path"]).name == key
                    or Path(r["path"]).as_posix().endswith("/" + key.lstrip("./"))
                    or Path(r["path"]).as_posix() == key]
            if not hits:
                missing.append(("(the whole model)", key, f"named in {args.manifest}"))
            for r in hits:
                for n in names:
                    expected.setdefault(r["path"], {})[n] = args.manifest

    code_names, unresolved = {}, []
    if args.scan_code:
        code_names, unresolved = scan_code([Path(d) for d in args.scan_code],
                                           args.lookup or DEFAULT_LOOKUPS, args.include_tests)

    by_path = {r["path"]: r for r in reports}
    for path, names in expected.items():
        have = set(by_path[path]["nodes"]) if path in by_path else set()
        for n, src in names.items():
            if n not in have:
                missing.append((n, path, f"expected by {src}"))
    every = set(n for r in reports for n in r["nodes"])
    for n, sites in sorted(code_names.items()):
        if n not in every:
            missing.append((n, "any of the models given", "asked for at " + ", ".join(sites)))

    if args.json:
        print(json.dumps({"models": reports,
                          "code_names": code_names,
                          "missing": [{"name": n, "model": m, "why": w} for n, m, w in missing],
                          "unresolved": [{"site": s, "arg": a, "why": w}
                                         for s, a, w in unresolved]}, indent=2))
    else:
        for r in reports:
            print(safe(f"{r['path']}  {r['bytes'] / 1024:.1f} KB  {r['triangles']} triangles  "
                       f"{len(r['nodes'])} nodes  {len(r['materials'])} materials"))
            print(safe("  nodes: " + (", ".join(r["nodes"]) or "none")))
            print(safe("  materials: " + (", ".join(r["materials"]) or "none")))
            for name, w, h, note in r["textures"]:
                size = f"{w}x{h} " if w else ""
                print(safe(f"  texture {name}: {size}{note}"))
            if r["mirrored"]:
                print(safe("  mirrored (negative scale): " + ", ".join(r["mirrored"])))
            if r["extensions"]:
                print(safe("  requires: " + ", ".join(r["extensions"])))
        if args.scan_code:
            print(safe(f"code: {len(code_names)} node names from "
                       f"{', '.join(args.lookup or DEFAULT_LOOKUPS)} calls, "
                       f"{len(unresolved)} unresolved call sites"))
            for n, sites in sorted(code_names.items()):
                print(safe(f"  asks for '{n}' at {', '.join(sites)}"))
            for site, arg, why in unresolved:
                print(safe(f"  unresolved  {site}  {arg}  ({why})"))
        for n, model, why in missing:
            print(safe(f"MISSING  node '{n}' in {model}  ({why})"))
        total = sum(len(v) for v in expected.values()) + len(code_names)
        print(safe(f"contract: {total} expected names, {len(missing)} missing"
                   if total else "contract: no expected names given (report only)"))
    if broken:
        return 2
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
