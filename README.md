# CyberHub Gallery

Browse, search and manage local AI image collections.

- Version: `1.2.14`
- Channel: `stable`
- Publisher: `official`

## Installation

1. Open **Module Manager** in CyberHub.
2. Click **Check for updates**.
3. Find **Gallery** and choose **Install** or **Update**.
4. Restart CyberHub when the installation finishes.

The ZIP attached to this repository's GitHub Release can also be imported manually through Settings.

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

## Development Checks

Run the layout regression checks without installing npm packages:

```sh
node --test tests/gallery_layout.test.cjs
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
