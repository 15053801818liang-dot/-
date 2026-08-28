import unittest

from joke_generator import build_url, format_joke


class JokeGeneratorTests(unittest.TestCase):
    def test_build_url_with_options(self):
        url = build_url(
            category="programming",
            joke_type="twopart",
            contains="python",
            blacklist_flags="nsfw,religious",
            safe_mode=True,
            lang="en",
        )
        self.assertIn("/programming?", url)
        self.assertIn("type=twopart", url)
        self.assertIn("contains=python", url)
        self.assertIn("blacklistFlags=nsfw%2Creligious", url)
        self.assertIn("safe-mode=", url)
        self.assertIn("lang=en", url)

    def test_format_single_joke(self):
        result = format_joke({"type": "single", "joke": "A SQL query walks into a bar..."})
        self.assertIn("😂", result)
        self.assertIn("SQL query", result)

    def test_format_twopart_joke(self):
        result = format_joke({"type": "twopart", "setup": "Knock knock", "delivery": "Who's there?"})
        self.assertIn("Q: Knock knock", result)
        self.assertIn("A: Who's there?", result)

    def test_format_missing_fields_raises(self):
        with self.assertRaises(RuntimeError):
            format_joke({"type": "twopart", "setup": "Only setup"})


if __name__ == "__main__":
    unittest.main()
