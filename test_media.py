"""Exercise real media copy/transcode paths without a GPU."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from media_pipeline import inspect_media, preview_video
import transcription


class ModelReuseTests(unittest.TestCase):
    def test_whisper_is_loaded_only_once(self):
        loader = Mock(return_value=object())
        with patch.dict('sys.modules', {'whisper': SimpleNamespace(load_model=loader)}):
            with patch.object(transcription, '_MODEL', None):
                first = transcription.load_model()
                self.assertIs(transcription.load_model(), first)
                loader.assert_called_once()


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is required')
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, codec, name):
        path = self.root / name
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10', '-f', 'lavfi', '-i',
                        'sine=frequency=440', '-t', '1', '-c:v', codec,
                        '-c:a', 'aac', str(path)], check=True, capture_output=True)
        return path

    def video_hash(self, path):
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                                       '-map', '0:v:0', '-c', 'copy', '-f', 'h264', '-'])
        return hashlib.sha256(data).hexdigest()

    def test_h264_is_copied_without_recompression(self):
        src = self.make('libx264', 'input.mp4')
        out = self.root / 'preview.mp4'
        self.assertEqual(preview_video(src, out, inspect_media(src)), 'video-copy')
        self.assertEqual(self.video_hash(src), self.video_hash(out))
        self.assertFalse((self.root / 'preview.part.mp4').exists())

    def test_incompatible_video_is_transcoded(self):
        src = self.make('mpeg4', 'input.mkv')
        out = self.root / 'preview.mp4'
        self.assertEqual(preview_video(src, out, inspect_media(src)), 'transcode')
        info = inspect_media(out)
        self.assertEqual(info['streams'][0]['codec_name'], 'h264')
        self.assertAlmostEqual(float(info['format']['duration']), 1, delta=.2)

    def test_failed_remux_falls_back_and_cleans_partial_file(self):
        src = self.make('libx264', 'input.mp4')
        out = self.root / 'preview.mp4'
        info = inspect_media(src)
        original = subprocess.run
        calls = []
        def fail_first(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)
            return original(cmd, **kwargs)
        with patch('media_pipeline.subprocess.run', side_effect=fail_first):
            self.assertEqual(preview_video(src, out, info), 'transcode-fallback')
        self.assertTrue(out.exists())
        self.assertFalse((self.root / 'preview.part.mp4').exists())
