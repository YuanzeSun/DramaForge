"""Offline behavioral tests; the fake service writes tiny real audio/video files."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/continuous-video-drama/scripts"))
from workflow import Project, export_jobs, import_asset, migrate, read, validate, write
from video import compile_request, fork_run, render, stitch
from PIL import Image
import imageio_ffmpeg


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        write(self.project / "project.json", {"version": 2, "size": [112, 64], "fps": 24, "output": "renders"})
        write(self.project / "cast.json", {
            "a": "Alice, a Chinese woman in blue; she speaks with an adult female Mandarin voice",
            "b": "Bo, a Chinese man in grey; he speaks with an adult male Mandarin voice"})
        write(self.project / "assets.json", {"version": 2, "assets": {
            "opening": {"kind": "keyframe", "prompt": "Opening shot", "references": []},
            "ending": {"kind": "keyframe", "prompt": "End of shot", "references": []}}})
        self.plan_path = self.project / "episodes/ep01/plan.json"
        self.plan = {"version": 2, "seed": 100, "segments": [
            {"id": "01", "frames": 158, "start": {"mode": "asset", "asset": "opening"},
             "end_asset": "ending", "in_frame": ["a", "b"], "offscreen": [],
             "beats": [{"action": "Alice looks at Bo."}, {"say": "a", "to": "b", "text": "你好。"}]},
            {"id": "02", "frames": 158, "start": {"mode": "continue"}, "in_frame": ["b"], "offscreen": ["a"],
             "beats": [{"action": "Bo waits."}, {"say": "a", "off": True, "text": "走吧。"}]}]}
        write(self.plan_path, self.plan)
        for key, color in [("opening", "red"), ("ending", "green")]:
            path = self.root / (key + ".png")
            Image.new("RGB", (64, 112), color).save(path)
            import_asset(Project(self.project), key, path)

    def tearDown(self):
        self.temp.cleanup()

    def fake_service(self):
        posts = []
        root = self.root
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                posts.append(payload)
                shutil.copy2(root / "synthetic.mp4", payload["save_result_path"])
                self.reply({"task_id": str(len(posts))})
            def do_GET(self):
                self.reply({"status": "completed"})
            def do_DELETE(self):
                self.reply({"status": "cancelled"})
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        cfg = read(self.project / "project.json")
        cfg["endpoint"] = f"http://127.0.0.1:{server.server_port}"
        write(self.project / "project.json", cfg)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=64x112:r=24", "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono",
            "-t", "0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(root / "synthetic.mp4")], check=True)
        return posts

    def test_payloads_stable_voices_offscreen_and_endpoints(self):
        project = Project(self.project)
        validate(project, ready=True)
        first = compile_request(project, "ep01", self.plan, self.plan["segments"][0], 0, self.root, dry=True)
        second = compile_request(project, "ep01", self.plan, self.plan["segments"][1], 1, self.root, dry=True)
        self.assertEqual(first["task"], "fl2av")
        self.assertEqual(first["size"], [112, 64])
        self.assertIn("last_frame_path", first)
        self.assertIn('Alice (S1) alone speaks', first["prompt"])
        self.assertIn('Alice (S1) says in an off-screen voiceover', second["prompt"])
        self.assertIn('Bo remain silent', second["prompt"])
        self.assertEqual(second["task"], "i2av")
        self.assertEqual(second["image_path"], str(self.root / "01.last.png"))

    def test_real_video_resume_and_changed_input(self):
        posts = self.fake_service()
        self.assertTrue(render(Project(self.project), "ep01", "test"))
        self.assertEqual(len(posts), 2)
        # The second shot consumes decoded video pixels, not the pinned target image.
        tail = Path(posts[1]["image_path"])
        with Image.open(tail) as img:
            pixel = img.getpixel((0, 0))
        self.assertGreater(pixel[2], 200)
        self.assertLess(pixel[1], 30)
        self.assertTrue(render(Project(self.project), "ep01", "test"))
        self.assertEqual(len(posts), 2)
        preview = stitch(Project(self.project), "ep01", self.plan, "test")
        self.assertGreater(preview.stat().st_size, 0)
        self.plan["segments"][0]["beats"][1]["text"] = "再见。"
        write(self.plan_path, self.plan)
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            render(Project(self.project), "ep01", "test")
        self.assertEqual(len(posts), 2)

    def test_inflight_task_reattaches(self):
        posts = self.fake_service()
        with patch("requests.get", side_effect=ConnectionError("connection lost")):
            with self.assertRaises(ConnectionError):
                render(Project(self.project), "ep01", "resume")
        state = read(self.project / "renders/resume/ep01/01.state.json")
        self.assertEqual(state["task_id"], "1")
        self.assertEqual(state["status"], "pending")
        self.assertTrue(render(Project(self.project), "ep01", "resume"))
        self.assertEqual(len(posts), 2)  # first request was not resubmitted

    def test_repair_preserves_independent_setups(self):
        self.plan["segments"].append({"id": "03", "frames": 158, "start": {"mode": "asset", "asset": "opening"},
            "in_frame": ["b"], "beats": [{"action": "Bo nods."}]})
        write(self.plan_path, self.plan)
        posts = self.fake_service()
        render(Project(self.project), "ep01", "original")
        self.assertEqual(len(posts), 3)
        self.plan["segments"][0]["beats"][1]["text"] = "再见。"
        write(self.plan_path, self.plan)
        kept = fork_run(Project(self.project), "ep01", "original", "repair", "01")
        self.assertEqual(kept, ["03"])
        render(Project(self.project), "ep01", "repair")
        self.assertEqual(len(posts), 5)  # repaired shot and its continuation, reused independent setup
        self.assertTrue((self.project / "renders/original/ep01/01.mp4").exists())

    def test_uncertain_submission_never_automatically_resubmits(self):
        with patch("requests.post", side_effect=TimeoutError("lost acknowledgement")):
            with self.assertRaises(TimeoutError):
                render(Project(self.project), "ep01", "uncertain")
        with patch("requests.post") as post:
            with self.assertRaisesRegex(ValueError, "Submission outcome unknown"):
                render(Project(self.project), "ep01", "uncertain")
            post.assert_not_called()

    def test_resumed_active_task_is_cancelled_at_expired_deadline(self):
        self.fake_service()
        with patch("requests.get", side_effect=ConnectionError("interrupted polling")):
            with self.assertRaises(ConnectionError):
                render(Project(self.project), "ep01", "deadline")
        response = unittest.mock.Mock()
        response.json.return_value = {"status": "processing"}
        with patch("requests.get", return_value=response):
            with self.assertRaises(TimeoutError):
                render(Project(self.project), "ep01", "deadline", deadline="2000-01-01T00:00+08:00")
        state = read(self.project / "renders/deadline/ep01/01.state.json")
        self.assertEqual(state["status"], "cancelled")

    def test_missing_images_and_bad_frames_block_before_network(self):
        self.plan["segments"][0]["frames"] = 159
        write(self.plan_path, self.plan)
        with self.assertRaisesRegex(ValueError, "frames"):
            validate(Project(self.project))
        self.plan["segments"][0]["frames"] = 158
        write(self.plan_path, self.plan)
        manifest = read(self.project / "assets.json")
        del manifest["assets"]["opening"]["path"]
        write(self.project / "assets.json", manifest)
        with patch("requests.post") as post:
            with self.assertRaisesRegex(ValueError, "Generate and import"):
                render(Project(self.project), "ep01", "missing")
            post.assert_not_called()

    def test_references_invalidate_consumers_and_export_in_order(self):
        manifest = read(self.project / "assets.json")
        manifest["assets"]["opening"]["references"] = ["ending"]
        write(self.project / "assets.json", manifest)
        import_asset(Project(self.project), "opening", self.root / "opening.png")
        Image.new("RGB", (64, 112), "yellow").save(self.root / "ending.png")
        import_asset(Project(self.project), "ending", self.root / "ending.png")
        with self.assertRaisesRegex(ValueError, "Reference ending changed"):
            Project(self.project).asset_path("opening")
        count = export_jobs(Project(self.project), self.root / "jobs.json")
        self.assertEqual(count, 1)
        self.assertEqual(read(self.root / "jobs.json")["jobs"][0]["id"], "opening")

    def test_migration_creates_fresh_specs_without_modifying_source(self):
        src = self.root / "legacy"
        write(src / "cast.json", read(self.project / "cast.json"))
        old = {"seed": 123, "cast": ["a"], "scene": "A classroom", "segments": [
            {"id": "01", "frames": 158, "beats": [{"action": "Alice waits."}]}]}
        write(src / "ep01/plan.json", old)
        before = (src / "ep01/plan.json").read_bytes()
        destination = self.root / "migrated"
        migrate(src, destination)
        p = Project(destination)
        validate(p)
        self.assertEqual((src / "ep01/plan.json").read_bytes(), before)
        self.assertEqual(p.assets["ep01_01_start"]["kind"], "keyframe")
        self.assertFalse(p.assets["ep01_01_start"].get("path"))
        self.assertTrue(any(a["kind"] == "scene" for a in p.assets.values()))
        self.assertFalse((destination / "renders").exists())


if __name__ == "__main__":
    unittest.main()
