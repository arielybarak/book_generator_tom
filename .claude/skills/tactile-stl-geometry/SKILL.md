---
name: tactile-stl-geometry
description: >-
  TOM CadQuery solid engine in src/dxf_3d.py — banded text/image/braille layout assembled as
  independent solids (NO boolean union), flat-top extrudes (taper segfaults OCCT). USE WHEN editing
  create_one_page_stl_from_dxf, config.yaml layout/plate, or debugging STL size / layout / segfault.
---

# Tactile STL geometry (CadQuery solid engine)

`src/dxf_3d.py` assembles the final page STL from three DXFs via CadQuery/OCCT. This is the
**engine-2.0 solid** path (Space `MLightning/text2STL-engine-2.0-superMX-bottom`), which replaced
the old lithophane heightmap. Entry point:
`create_one_page_stl_from_dxf(txt_dxf, braille_dxf, image_dxf, output)` — it prints `[t]` per-stage
timing, `Layout →`, and `Assembled N feature solids`.

## When to Activate This Skill
- "STL is 10× too big", "text/braille missing from the STL", "layers overlap", "build hangs",
  "OCCT segfault", "the extrude crashed"
- Editing `src/dxf_3d.py`, `config.yaml` `layout.*` / `plate.*`, or `layout_content_on_base`

## The rules that are now LAW (engine-2.0)
1. **No boolean union.** Features are independent solids collected into one `Compound`; the
   **slicer fuses overlaps at print time**. OCCT booleans do NOT scale to real line-art —
   thousands of solids → minutes-to-hours (the O(N²) blow-up; a 2.4 hr fuse was observed). Never
   `.union()` / `.fuse()` across feature solids.
2. **Flat tops only — `STROKE_TAPER_DEG = 0`.** `extrude(taper=)` **segfaults OCCT on real Hebrew
   glyph outlines** (reproduced on פרח). Rounded/tapered tops must run in a crash-isolated
   subprocess — see [[occt-crash-isolation]]. The default path stays flat-top.
3. **Banded layout.** text (top) / image (mid) / braille (bottom), driven by `layout.*` +
   `plate.content_margin_mm` in `config.yaml`; `layout_content_on_base` scales each layer into its
   band. For a 150 mm plate with 10 mm margin: text y≈[117,140], image≈[37,113], braille≈[10,33].
   A layer whose XY bbox escapes `[0,W]×[0,H]` is the 10× oversize bug.
4. **Flush logs.** `print(flush=True)` — HF stdout is block-buffered; without it the build looks
   hung even while progressing.

## Performance envelope (all CPU, no GPU)
~50-path page ≈ seconds; ~560-path dense page ≈ 60–80 s. A build that runs minutes→hours almost
always means a boolean union crept back in (rule 1).

## Verify before deploy
Run [[/stl-bench]] offline — it parses the binary STL and asserts plate-fit, per-band triangle
presence, and braille dot spacing in seconds, no GPU/deploy needed. After editing `src/` or
`config.yaml`, run `./sync_to_space.sh` then deploy (see [[hf-space-sync-deploy]]).
