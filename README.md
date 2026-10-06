# CyberHub Gallery

Browse, search and manage local AI image collections.

- Version: `1.2.16`
- Channel: `stable`
- Publisher: `official`

## Installation

1. Open **Module Manager** in CyberHub and click **Check for updates**.
2. Find **Gallery** and choose **Update** or **Install**.
3. Restart CyberHub after installation.

Requires CyberHub 1.3.0 or newer. The ZIP attached to the
[GitHub release](https://github.com/cyberdeliaAI/CyberHub-Gallery/releases/tag/v1.2.16)
can also be imported manually through **Settings**.

See [the upgrade and test guide](docs/performance/2026-09-28/TESTEN.md) for installation,
checks with an existing large library and rollback to 1.2.14.

## Export positive prompts

Select images with Ctrl/Cmd-click or Shift-click, then click **Export prompts**
in the selection bar between **Compare** and **Clear**. The browser downloads
`positive-prompts.txt` as UTF-8 text containing only the positive prompts, separated
by a blank line. There are no filenames, headings, negative prompts or generation
settings. Multiline prompts and special characters are preserved. Identical
prompts from different images remain in the file, in selection order.

Images with no available positive prompt are skipped and counted in the on-screen
notification. If metadata is still processing, wait and export again. An empty
selection of available prompts does not create an empty file. Export leaves the
image selection intact.

Export reads only the selected images' stored metadata in small indexed batches;
it does not reopen original images, generate thumbnails or require a rescan.
Up to 10,000 selected images can be exported per request.

## Gallery Layouts

Use **Layout** in the gallery toolbar to switch between **Grid** (square tiles,
the default) and **Masonry** (Pinterest-style columns showing the full image).
The browser remembers your choice. The thumbnail-size slider works in both
layouts, and columns adapt when the metadata panel opens or the window resizes.

Both layouts reuse the same WebP thumbnail cache: one thumbnail per indexed
image, bounded by 300×300 pixels while preserving its original proportions.
Masonry does not create a second cache, regenerate existing thumbnails or load
all original images. Pagination and lazy thumbnail loading remain in use;
only cards on the current page are arranged. Images whose dimensions are still
being processed start square and adjust when their thumbnail loads.

Search, metadata filters, favorites, collections and model grouping work in
both layouts. Group headings span all columns. Arrow keys follow the visible
neighbouring cards in Masonry; Shift extends the selection in display order.
Switching layouts preserves the current page and selection.

## Performance improvements in 1.2.15

- Gallery reads use independent SQLite snapshots, allowing browsing while discovery,
  background processing and delete bookkeeping continue.
- Changed files are registered in batches without repeatedly listing their directory.
  Search entries are removed through an indexed path-to-row mapping; tag counts are
  updated only for affected tags.
- Selection previews use the existing thumbnail. Rapid selection changes coalesce
  metadata requests, and late responses cannot replace a newer selection.
- The open page refreshes as files arrive or finish processing, reusing unchanged
  cards and preserving selection and the visible scroll position.
- Missing thumbnails are queued for background processing, with bounded priority
  and retries. Requests no longer decode an original on the HTTP thread. Existing
  thumbnails are reused; there is still one thumbnail cache per image.
- Deletes retain system-trash behavior and report partial failures. Their progress
  no longer waits behind a whole watcher batch.

No forced rescan, second thumbnail cache or Core change is required. At startup,
Gallery refreshes a small lookup table from its existing search index; it does not
reread the originals for this migration. Pausing/disabling background processing
also pauses newly requested missing thumbnails; cached thumbnails remain visible.

## Development Checks

Run the layout regression checks without installing npm packages:

```sh
node --test tests/gallery_layout.test.cjs tests/gallery_interaction.test.cjs
```

Backend regression checks need the adjacent CyberHub repository and its Python
dependencies (set `CYBERHUB_CORE_PATH` if it is elsewhere):

```sh
python -m unittest discover -s tests -p 'test_*.py'
```

Optional synthetic database benchmark (260,000 rows, about 3 GB of temporary disk
space; automatically removes the generated database after success):

```sh
python tests/benchmark_gallery.py --rows 260000 --output measurements.json
```

For manual testing in CyberHub, use a folder with portrait, landscape and square
images. Check layout switching, the size slider, opening/closing the metadata
panel, model grouping, Ctrl/Cmd- and Shift-selection, arrow keys, the fullscreen
viewer, page navigation, search and an empty result. Reload to check the saved
layout preference. Existing thumbnails should be reused in both views.

## Python Packages

- `Pillow>=9.0`
- `send2trash>=1.8`
- `watchdog>=4.0`

## Privacy

CyberHub runs locally. A module uses an external service only when its function requires it and the user starts that action.

## License

See `LICENSE.md` and `THIRD-PARTY-NOTICES.md`.
