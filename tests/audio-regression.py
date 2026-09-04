#!/usr/bin/env python3
"""Local DSP regressions. Requires ffmpeg + RNNoise LADSPA; no recordings used."""
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(os.environ.get("OMAREEL_TEST_SOURCE", Path(__file__).resolve().parents[1] / "bin/omareel"))
PLUGIN = Path("/usr/lib/ladspa/librnnoise_ladspa.so")


def pcm(data):
    samples = array.array("f", data)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


@unittest.skipUnless(PLUGIN.exists(), "RNNoise LADSPA is not installed")
class AudioRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omareel-audio-test-")
        self.config = Path(self.tmp.name) / "config.json"
        self.env = dict(os.environ, OMAREEL_CONFIG=str(self.config), XDG_RUNTIME_DIR=self.tmp.name)
        self.settings = {"denoiseStrength": "normal", "vadThreshold": 0,
                         "vadGraceMs": 300, "vadRetroactiveMs": 50}

    def tearDown(self):
        self.tmp.cleanup()

    def helper(self, command, *args, check=True):
        self.config.write_text(json.dumps(self.settings))
        return subprocess.run(["bash", "-c", 'source "$1"; shift; ' + command,
                               "_", str(SOURCE), *args], env=self.env, capture_output=True,
                              text=True, check=check, timeout=20)

    def graph(self, engine="ladspa"):
        return self.helper('voice_graph "0:a:0" "$1" out', engine).stdout.strip()

    def render(self, expression, graph, duration=2):
        result = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                                 f"aevalsrc={expression}:s=48000:d={duration}",
                                 "-filter_complex", graph, "-map", "[out]", "-f", "f32le", "-"],
                                capture_output=True, check=True, timeout=20)
        return pcm(result.stdout)

    def test_clean_and_strong_stay_aligned_at_all_lookaheads(self):
        for strength in ("normal", "strong"):
            for retro in (0, 50, 200):
                with self.subTest(strength=strength, retro=retro):
                    self.settings.update(denoiseStrength=strength, vadRetroactiveMs=retro)
                    samples = self.render(r"if(eq(n\,48000)\,0.5\,0)", self.graph())
                    self.assertEqual(len(samples), 96000)
                    self.assertTrue(all(math.isfinite(x) for x in samples))
                    peak = max(range(len(samples)), key=lambda i: abs(samples[i]))
                    self.assertLessEqual(abs(peak - 48000), 2)
                    self.assertGreater(abs(samples[peak]), 1e-5)

    def test_partial_final_frame_and_last_syllable_are_flushed(self):
        for strength in ("normal", "strong"):
            with self.subTest(strength=strength):
                self.settings["denoiseStrength"] = strength
                samples = self.render(r"if(eq(n\,95360)\,0.5\,0)", self.graph(), 2.001)
                self.assertEqual(len(samples), 96048)
                peak = max(range(len(samples)), key=lambda i: abs(samples[i]))
                self.assertLessEqual(abs(peak - 95360), 2)
                self.assertGreater(abs(samples[peak]), 1e-5)

    def test_silence_stays_silent(self):
        self.settings["vadThreshold"] = 50
        samples = self.render("0", self.graph())
        self.assertEqual(len(samples), 96000)
        self.assertEqual(max(abs(x) for x in samples), 0)

    def test_cleanup_off_preserves_input_after_startup_mute(self):
        samples = self.render("0.1*sin(2*PI*1000*t)", self.graph("none"))
        error = max(abs(samples[i] - 0.1 * math.sin(2 * math.pi * 1000 * i / 48000))
                    for i in range(48000, 90000))
        self.assertLess(error, 1e-6)

    def test_room_noise_is_not_restored_by_natural_component(self):
        self.settings["vadThreshold"] = 50
        samples = self.render("0.02*(random(0)-0.5)", self.graph(), 4)
        rms = math.sqrt(sum(x*x for x in samples[48000:]) / (len(samples)-48000))
        self.assertLess(rms, (0.02 / math.sqrt(12)) / 10)

    def test_normalization_does_not_turn_quiet_noise_into_loud_audio(self):
        raw = Path(self.tmp.name) / "quiet.wav"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i",
                        "aevalsrc=0.002*sin(2*PI*1000*t):s=48000:d=2",str(raw)],
                       check=True,capture_output=True,timeout=10)
        result = self.helper('loudnorm_measure_graph "$1" "[0:a:0]anull[premaster]"', str(raw))
        self.assertEqual(result.stdout.strip(), "volume=18dB")

    def test_desktop_bypasses_voice_processing(self):
        self.settings["vadThreshold"] = 50
        graph = self.helper('audio_graph 2 true true ladspa').stdout.strip()
        result = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                                 "anullsrc=r=48000:cl=mono:d=2", "-f", "lavfi", "-i",
                                 "aevalsrc=0.1*sin(2*PI*440*t)|0.1*sin(2*PI*880*t):s=48000:d=2",
                                 "-filter_complex", graph.replace("[0:a:1]", "[1:a:0]"),
                                 "-map", "[premaster]", "-f", "f32le", "-"],
                                capture_output=True, check=True, timeout=20)
        samples = pcm(result.stdout)
        self.assertEqual(len(samples), 96000 * 2)
        for channel, freq in enumerate((440, 880)):
            error = max(abs(samples[2*i + channel] - 0.05*math.sin(2*math.pi*freq*i/48000))
                        for i in range(48000, 90000))
            self.assertLess(error, 1e-6)

    def test_unmeasurable_plugin_fails_graph_preparation(self):
        result = self.helper('LADSPA_RNNOISE=/nonexistent/omareel-test.so; audio_graph 1 true false ladspa', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
