# CyberHub Gallery

Browse, search and manage local AI image collections.

- Version: `1.3.1`
- Channel: `stable`
- Publisher: `official`

## Installation

1. Open **Module Manager** in CyberHub and click **Check for updates**.
2. Find **Gallery** and choose **Update** or **Install**.
3. Restart CyberHub after installation.

Requires CyberHub 1.3.0 or newer. The ZIP attached to the
[GitHub release](https://github.com/cyberdeliaAI/CyberHub-Gallery/releases/tag/v1.3.1)
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

## Collections sidebar

Added in **1.3.1** (5 November 2026): click **Collections**
or its arrow to collapse/expand the sidebar list. The browser remembers this
choice across reloads. **+ New** remains available while collapsed. Collapsing
the list preserves the selected collection and does not change its images.

## My tags in 1.3.0 (4 November 2026)

Add your own image labels, such as `great_pose`, `great_clothes` or
`photostudio_good_prompt`, directly in Gallery. This works without Auto Tagger
or Prompt Library and is separate from prompt-derived and AI-generated tags.

- Select an image, open the **Tags** tab and use **My tags**. Enter one or more
  comma-separated tags and press Enter or **Add**. Suggestions reuse existing
  labels; recently used labels can be applied with one click.
- Remove a label from the image using its **×** button. Other labels are kept.
- Select several images and choose **Tags** in the selection bar to add or remove
  labels across the selection. The dialog snapshots the selected images.
- Open **My tags** in the sidebar to filter images. Every selected tag must match.
  By default the current folder and its subfolders are searched; choose **All
  folders** for the whole collection. Clicking an assigned tag opens this filter.
- Tag results retain pagination, sorting, model grouping, Grid/Masonry layouts
  and the generation-metadata filter. **Clear filter** returns to the folder view.
  The active tag filter is restored when the page reloads.

Labels are lowercase, with whitespace converted to underscores. An operation
accepts up to 20 labels (80 characters each) and 10,000 indexed images. Missing
images are skipped and reported. Batch operations add/remove the specified labels
without replacing the rest of an image's labels.

Manual labels live in the local Gallery database, not in image files or prompts.
They survive metadata processing, reindexing, search-index rebuilds, AI retagging
and restarts. Include the Gallery database in backups; exporting an image alone
does not carry its manual labels. The dedicated **My tags** filter searches these
labels; the existing prompt search and AI tag filter retain their own behavior.
Recently used label names remain available for reuse even after their last image
assignment is removed. Deleting an indexed image cleans up its assignments.

In **1.3.1** (5 November 2026), the per-image editor
now lives in **Tags**, the renamed **AI Tags** tab. **My tags** appears first;
the existing **AI Tags** section appears below when Auto Tagger is available.
The tab remains available without Auto Tagger. Metadata and Raw Metadata no
longer show the editor. Sidebar filters, batch tagging and stored labels are
unchanged.

Update Gallery to **1.3.1** through Module Manager or import the release ZIP
through Settings, restart CyberHub, then reload Gallery. The additional tag tables
are created automatically; a full reindex or separate Core update is not required.

## Offline and unreadable folders

An image folder that is unavailable when CyberHub starts, such as an unplugged
drive or a NAS that is not mounted yet, stays configured. Gallery skips it while
it is offline and keeps its images, favorites, collections, tags, My tags and AI
tags in the database. Cached thumbnails remain visible. After reconnecting the
folder, run **Settings → Maintenance → Re-index folders** or restart CyberHub to pick up
changes and resume folder watching.

A folder that cannot be read during a scan, or a drive that disconnects while
CyberHub runs, is never treated as deleted. Records are only removed for files
and folders that are reported as not found below a folder that is still present,
or for a folder you remove from **Settings → Gallery**.

## Thumbnail repair in 1.2.17 (21 October 2026)

The fix for [issue #4](https://github.com/cyberdeliaAI/CyberHub/issues/4) makes **Generate All Thumbs** check that current
cached WebP thumbnails can actually be decoded. Empty, truncated or unreadable
cache files are regenerated alongside missing or stale thumbnails. Valid current
thumbnails are kept, and their original images are not decoded again.

Run **Settings → Maintenance → Generate All Thumbs** after updating Gallery
and restarting CyberHub. When it finishes, force-refresh the Gallery page so the
browser discards any previously cached broken image response. No image removal,
database cleanup or full reindex is needed. Existing failed-repair counts remain
available in the maintenance result; unreadable originals cannot be repaired by
regenerating a thumbnail.

Validation only runs during this explicit maintenance pass. Normal thumbnail
requests retain their existing fast path. Replacement remains atomic under the
per-thumbnail lock, and a failed encode/write leaves the previous cache file in
place. The patch does not modify image files, metadata, favorites or collections.
Update Gallery through Module Manager or import the 1.2.17 release ZIP through
Settings. No Core update is required for this Gallery correction.

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
