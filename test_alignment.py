import unittest
from transcription import align_words


class Alignment(unittest.TestCase):
    def test_switch_is_preserved(self):
        words = [
            {
                "words": [
                    {"start": 0, "end": 1, "word": "前半"},
                    {"start": 1, "end": 2, "word": "後半"},
                ]
            }
        ]
        rows = align_words(
            words,
            [
                {"start": 0, "end": 1, "speaker": 0},
                {"start": 1, "end": 2, "speaker": 1},
            ],
        )
        self.assertEqual([r["speaker"] for r in rows], [0, 1])

    def test_overlap_is_marked(self):
        rows = align_words(
            [{"start": 0, "end": 1, "text": "重なり"}],
            [
                {"start": 0, "end": 1, "speaker": 0},
                {"start": 0.5, "end": 1, "speaker": 1},
            ],
        )
        self.assertTrue(rows[0]["uncertain"])

    def test_silence_not_assigned_to_nearest(self):
        rows = align_words(
            [{"start": 5, "end": 6, "text": "不明"}],
            [{"start": 0, "end": 1, "speaker": 0}],
        )
        self.assertIsNone(rows[0]["speaker"])


if __name__ == "__main__":
    unittest.main()
