"""The social card is an asset with a size, not a screenshot.

GitHub wants 1280×640 for the repository card, and X crops whatever it is given.
This test keeps the file at the size the platforms expect; the numbers on it are
checked by test_plot_fixed_cost.py, because the card is drawn from the same fits.
"""
from pathlib import Path

import matplotlib.image as mpimg

ROOT = Path(__file__).resolve().parent.parent


def test_the_card_is_the_size_the_platforms_want():
    image = mpimg.imread(ROOT / "assets" / "social-preview.png")
    height, width = image.shape[:2]
    assert (width, height) == (1280, 640)
