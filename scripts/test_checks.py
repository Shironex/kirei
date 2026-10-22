#!/usr/bin/env python3
"""Unit tests for asset-check.py, gate-commands.py and input-lock.py.
Run: python -B scripts/test_checks.py"""
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


asset_check = load("asset-check")
gate_commands = load("gate-commands")
input_lock = load("input-lock")


def png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h)


def glb(doc, binary=b""):
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(body), 0x4E4F534A) + body
    if binary:
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def model(tmp, name="prop.glb", nodes=("root", "arm"), image=png(512, 300)):
    doc = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": n, "mesh": 0} for n in nodes] + [{"name": "flip", "scale": [-1, 1, 1]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [{"count": 4}, {"count": 6}],
        "materials": [{"name": "paint"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(image)}],
        "images": [{"name": "albedo", "bufferView": 0, "mimeType": "image/png"}],
    }
    path = Path(tmp) / name
    path.write_bytes(glb(doc, image))
    return path


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(HERE / "asset-check.py"), *args],
                          capture_output=True, text=True, cwd=cwd)


class AssetCheckTest(unittest.TestCase):
    def test_describe(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = asset_check.describe(model(tmp))
        self.assertEqual(r["nodes"], ["root", "arm", "flip"])
        self.assertEqual(r["triangles"], 4)  # 2 triangles per node, 2 nodes use the mesh
        self.assertEqual(r["mirrored"], ["flip"])
        self.assertEqual(r["textures"][0][1:3], (512, 300))
        self.assertIn("not a power of two", r["textures"][0][3])

    def test_unreadable_image_is_not_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = asset_check.describe(model(tmp, image=b"garbage!" * 4))
        self.assertIsNone(r["textures"][0][1])
        self.assertIn("not measured", r["textures"][0][3])

    def test_expect_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = model(tmp)
            self.assertEqual(run(str(p), "--expect", "root,arm").returncode, 0)
            out = run(str(p), "--expect", "root,leg")
        self.assertEqual(out.returncode, 1)
        self.assertIn("MISSING  node 'leg'", out.stdout)

    def test_manifest_per_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = model(tmp, "a.glb"), model(tmp, "b.glb", nodes=("root",))
            manifest = Path(tmp) / "m.json"
            manifest.write_text(json.dumps({"a.glb": ["arm"], "b.glb": ["arm"], "c.glb": []}))
            out = run(str(a), str(b), "--manifest", str(manifest))
        self.assertEqual(out.returncode, 1)
        self.assertIn("node 'arm' in", out.stdout)
        self.assertIn("b.glb", out.stdout)
        self.assertIn("(the whole model)", out.stdout)
        self.assertEqual(out.stdout.count("MISSING"), 2)

    def test_code_scan(self):
        code = (
            'constexpr std::string_view HAND = "arm";\n'
            'constexpr const char* TAIL = "tail";\n'
            "int findNode(const Model& model, std::string_view name) { return -1; }\n"
            'int a = assets::findNode(model, "root");\n'
            "int b = assets::findNode(model, HAND);\n"
            "int c = assets::findNode(model, TAIL);\n"
            "int d = assets::findNode(model, std::string(prefix) + name);\n"
            "const head = scene.getObjectByName('root');\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "tests").mkdir(parents=True)
            (src / "Rig.cpp").write_text(code)
            (src / "tests" / "RigTests.cpp").write_text('findNode(model, "fixture");\n')
            names, unresolved = asset_check.scan_code([src], ["findNode", "getObjectByName"],
                                                      False)
            self.assertEqual(sorted(names), ["arm", "root", "tail"])
            self.assertEqual(len(unresolved), 1)
            self.assertIn("prefix", unresolved[0][1])
            out = run(str(model(tmp)), "--scan-code", str(src))
        self.assertEqual(out.returncode, 1)
        self.assertIn("MISSING  node 'tail'", out.stdout)
        self.assertNotIn("fixture", out.stdout)

    def test_not_a_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.glb"
            bad.write_bytes(b"nope")
            self.assertEqual(run(str(bad)).returncode, 2)


class GateCommandsTest(unittest.TestCase):
    def roles(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / name).write_text(text)
            return {(r, c) for r, c, _, _ in gate_commands.discover(Path(tmp))}

    def test_make_wins_over_cmake_and_accept_is_manual(self):
        got = self.roles({
            "Makefile": ".PHONY: test smoke \\\n\tgoldens run\n"
                        "X := 1\ntest:\n\tctest\nsmoke:\n\tpython smoke.py\n"
                        "goldens:\n\tpython smoke.py --accept-goldens\nrun:\n\t./app\n",
            "CMakeLists.txt": "enable_testing()\n",
        })
        self.assertIn(("test", "make test"), got)
        self.assertIn(("smoke", "make smoke"), got)
        self.assertIn(("goldens-accept", "make goldens"), got)
        self.assertNotIn(("goldens", "make goldens"), got)
        self.assertFalse(any(c.startswith("ctest") for _, c in got))
        self.assertFalse(any(c == "make run" for _, c in got))

    def test_cmake_presets_without_test_presets(self):
        presets = {
            "configurePresets": [
                {"name": "base", "hidden": True, "binaryDir": "${sourceDir}/build/${presetName}"},
                {"name": "debug", "inherits": "base",
                 "cacheVariables": {"CMAKE_BUILD_TYPE": "Debug"}}],
            "buildPresets": [{"name": "debug", "configurePreset": "debug"}],
        }
        got = self.roles({"CMakeLists.txt": "add_test(NAME t COMMAND t)\n",
                          "CMakePresets.json": json.dumps(presets)})
        self.assertIn(("build", "cmake --preset debug && cmake --build --preset debug"), got)
        self.assertIn(("test", "ctest --test-dir build/debug -C Debug --output-on-failure"), got)

    def test_agents_md_section_overrides(self):
        got = self.roles({
            "package.json": json.dumps({"scripts": {"test": "vitest", "lint": "eslint ."}}),
            "pnpm-lock.yaml": "",
            "AGENTS.md": "# Repo\n\n## gate-commands\n\n- test: `make unit` (fast)\n"
                         "- capture: `python tools/shots.py` (slow)\n\n## other\n- x: `nope`\n",
        })
        self.assertIn(("test", "make unit"), got)
        self.assertNotIn(("test", "pnpm run test"), got)
        self.assertIn(("lint", "pnpm run lint"), got)
        self.assertIn(("capture", "python tools/shots.py"), got)
        self.assertFalse(any(c == "nope" for _, c in got))


class InputLockTest(unittest.TestCase):
    def test_runs_child_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock"
            out = subprocess.run([sys.executable, "-I", str(HERE / "input-lock.py"),
                                  "--lock", str(lock), "--role", "test", "--",
                                  sys.executable, "-c", "import sys; sys.exit(3)"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 3)
            self.assertFalse(lock.exists())

    def test_live_holder_blocks_and_dead_holder_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock"
            lock.mkdir()
            (lock / "owner.txt").write_text(f"role=other\npid={os.getpid()}\ntime=9999999999\n")
            self.assertFalse(input_lock.acquire(lock, "me", wait=0))
            (lock / "owner.txt").write_text("role=other\npid=999999\ntime=9999999999\n")
            self.assertTrue(input_lock.acquire(lock, "me", wait=0))
            input_lock.release(lock)
            self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()
