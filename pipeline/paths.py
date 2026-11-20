"""Where the pipeline finds its inputs. Override with environment variables.

CARD_REDESIGN  the card_redesign package (checkout of anki-card-redesign), used for the card format
DECKS          folder with the source collections: vn.anki2, jp.anki2, cn_raw.anki2
               (copies of your own collection exported from Anki – never commit them)
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_REDESIGN = os.environ.get("CARD_REDESIGN", str(ROOT.parent / "anki-card-redesign" / "card_redesign"))
DECKS = Path(os.environ.get("DECKS", str(ROOT / "data" / "decks")))


def deck(name: str) -> str:
    return str(DECKS / name)
