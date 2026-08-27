# SURFwave product model — v5.8+

SURFwave is one creative audio product family with specialized rooms, not one mandatory workflow.

## Shared object

The connective tissue is the **SURFwave Project**: one local project directory containing a small manifest plus the user's source audio, stems, takes, analysis, model renders, mix state, and exports.

The first real implementation now lives at `src/shared/project.py` and writes `surfwave.project.json` using schema `surfwave.project.v1`.

The manifest is deliberately boring. It records:

- project identity and timestamps
- an asset ledger
- each asset's kind and project-relative path
- source relationships between derived assets
- lightweight metadata such as the separation/render engine
- independent workspace state for Studio, Voice Lab, Slopscore, and Song Lab

The manifest does **not** prescribe an order of operations and does not delete user audio when a ledger entry is removed.

### Asset kinds

Current ledger vocabulary:

`source` · `stem` · `take` · `render` · `export` · `analysis` · `model_ref` · `other`

This is a provenance layer, not a replacement filesystem. The files remain ordinary files in the project directory.

## Rooms

- **Studio** — record, edit, blend, finish, export.
- **Slopscore** — mutate and generatively reinterpret existing material.
- **Song Lab** — generate and explore new material.
- **Voice Lab** — train and use reusable timbre models.

Only Studio and Voice Lab are currently shipped inside this app build. Do not add fake Slopscore or Song Lab surfaces until their real engines are integrated.

## UX rules

1. Integration does not mean sameness. Each room can have its own workflow.
2. Studio tools are non-linear. Do not number Studio navigation as if every user must record or train a model.
3. Voice Lab training is genuinely sequential, so its Recordings → Prepare → Train → Use workflow may remain explicit.
4. Hide implementation plumbing during normal use. Engine names belong in diagnostics, not the primary product hierarchy.
5. Preserve originals. Every derived asset should be recoverable and traceable to its source.
6. SURFwave is the brand. Room names are descriptors.
7. Never add placeholder product surfaces. A room appears only when its real capability exists.
8. Shared project infrastructure should make handoffs easier without forcing every room to use every asset.

## Brand hierarchy

Deep Shore `#403742` + Coastal Blue `#89B5CC` + Mist `#E2DCE8` do most of the work. Ocean Depth `#56548C` and Twilight `#6D6380` support structure.

## Current design intent

Surfy, not SURFY. Modern, not MODERN. Personality comes from movement, mark, palette, and copy; utility remains calm and restrained.
