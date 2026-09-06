# `dataset/` — the offline social-media index

The offline search provider (`--provider local`) matches a scanned face against
the images in this folder using real face embeddings, and returns the **real
source URL** of the closest match.

## Format

Put social-media images here (`.jpg/.png/...`), one clear face per image, and a
`sources.json` that maps each filename to its real post:

```json
{
  "my_instagram_selfie.jpg": {
    "platform": "instagram",
    "url": "https://www.instagram.com/p/ABC123/",
    "title": "Beach trip 2024",
    "handle": "@yourhandle"
  }
}
```

Then build the index:

```bash
python cli.py build-index
```

## Quick demo data

Don't have your own images handy? Generate a runnable demo set (public sample
faces, each paired with its real GitHub source URL):

```bash
python cli.py make-sample
python cli.py build-index
```

The downloaded images and `sources.json` are git-ignored so your own data never
gets committed by accident.
