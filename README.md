# OctLLM Project Page

The static project page for **Octrees as an Explicit 3D Language**. HTML, CSS,
JavaScript, fonts, GLB models, and videos are served locally; no build step or
runtime CDN is required.

## Preview

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Open [the local preview](http://127.0.0.1:4173). Use HTTP rather than opening
`index.html` directly: the 3D viewer uses an ES module and fetches GLB files.
All paths are relative, including when hosted under a repository subpath.

## Content

- The abstract is copied from page 1 of `paper/iclr2027_conference.pdf`, with
  PDF line wrapping removed. `scripts/paper-abstract.txt` preserves the checked
  source text. Method copy summarizes sections 3.1–3.3 and Figure 2.
- Author names and affiliations are omitted. The page lists anonymous authors and
  double-blind review, matching the supplied manuscript. It makes no acceptance claim.
- Twelve selected GLBs from the supplied favorites are available in one large
  viewer: six image-conditioned and six text-conditioned examples. Drag or use
  arrow keys to rotate; scroll or pinch to zoom. Reset and fullscreen controls
  are provided. Original text prompts are available under “View text prompt”.
- Models load when the gallery approaches the viewport; only the selected model
  is requested. A failed load offers retry and a GLB download. Downloaded files
  are the original generated outputs, without geometry or texture edits.
- One 60-second, 1920×1080 H.264 film shows Robot → Airplane → Truck. Each clip
  has depth 3–6, voxel completion, surface reveal, and final-asset captions.
  Captions are centered above the object; the player is centered at a maximum
  width of 1080 CSS pixels with space on both sides.
  Native controls support seeking and fullscreen playback. The film visualizes
  octrees derived from source GLBs; it is not an inference recording.
- Videos pause outside the viewport and while the browser tab is hidden. Manual
  pauses persist. Reduced-motion preferences disable automatic playback.
- The method figure can be enlarged; architecture figures expand on demand.
  Two understanding examples retain excerpts of model responses from the paper.

## Editing

| File | Purpose |
| --- | --- |
| `index.html` | Paper copy, section layout, media elements |
| `styles.css` | Typography, spacing, desktop and mobile layout |
| `script.js` | Gallery, camera controls, loading, video playback, resource links |
| `model-data.js` | Twelve selected models, source asset IDs, conditions, exact prompts |
| `assets/models/manifest.json` | GLB provenance, hashes, geometry statistics |
| `gallery-data.js` | Original figure data; understanding examples are still displayed |
| `release-config.js` | Confirmed paper, code, model URLs and optional BibTeX |

The Paper button links to the supplied manuscript. Empty code, model, and
citation fields are hidden until resources are available. Do not invent release
URLs or publication metadata.

## Film reproduction

The film is encoded from the original lossless frame sequences in the research
checkout's `outputs/octllm_animation/{robot,airplane,truck}/frames`. The original
Blender rendering scripts are in that checkout's `scripts/visualization/`.
From this page checkout:

```sh
python scripts/build_generation_film.py \
  --frames-root /path/to/OctLLM/outputs/octllm_animation
```

The script needs Pillow and FFmpeg with drawtext support; pass `--ffmpeg` and
`--font` if they are not discoverable. Run `--help` for encoder options and
optional WebM output. The script writes the MP4, poster, and
`assets/videos/generation.json` with stage timings and validation results.
Existing individual videos are retained as source assets but are no longer
embedded beside each other.

## Viewer dependency

The browser loads the bundled [Google model-viewer](https://modelviewer.dev/)
**4.2.0** from `assets/vendor/model-viewer-4.2.0.min.js`. The vendored bundle
includes Three.js and Lit. License notices are retained in `assets/vendor/`.
The chosen GLBs embed their textures and need no Draco, KTX2, or Meshopt decoder,
so loading these assets makes no requests to external services.

To replace the bundle, obtain the desired version of `@google/model-viewer`,
copy `dist/model-viewer.min.js`, preserve its licenses, and update the import in
`script.js`. The viewer's [camera documentation](https://modelviewer.dev/examples/stagingandcameras/)
and [loading documentation](https://modelviewer.dev/examples/loading/) describe
its interaction and loading APIs.

## Checks

```sh
python3 scripts/check_site.py
node --check script.js
node --check model-data.js
node --check gallery-data.js
node --check release-config.js
```

The checker covers local references and anchors, the exact abstract, GLB
structure and hashes, embedded resources, and asset size limits. Browser checks
should also exercise all twelve models, camera dragging/zoom/reset, mode switching,
fullscreen, failed loads, video controls, and mobile layouts. Serve under a
subpath as well when preparing a GitHub Pages deployment.

## Hosting

This branch contains a complete static site, compatible with GitHub Pages or any
static HTTP host. Serve the branch root. No deployment is performed by the local
preview or validation commands. Source research assets retain their original
rights; font OFL notices are in `assets/fonts/`.
