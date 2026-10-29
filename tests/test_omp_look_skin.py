"""Fork-only (q-design): the titanium skin carries oh-my-pi's titanium-prompt-focus palette."""

import unittest

from omh.skin_pack import available_skins, default_theme, skin_colors, theme_for_name


class TitaniumSkinTest(unittest.TestCase):
    def test_titanium_is_shipped_after_the_default(self):
        self.assertIn("omh-titanium", available_skins())
        self.assertEqual(theme_for_name("titanium").skin_name, "omh-titanium")
        self.assertEqual(default_theme().short_name, "sky")

    def test_titanium_palette(self):
        colors = {key: value.lower() for key, value in skin_colors("omh-titanium").items()}
        self.assertEqual(colors["ui_accent"], "#00b4ff")
        self.assertEqual(colors["ui_ok"], "#00e67a")  # fork q-design: reads as a band on a light background
        self.assertEqual(colors["ui_error"], "#ff4757")
        self.assertEqual(colors["status_bar_bg"], "#151820")


if __name__ == "__main__":
    unittest.main()
