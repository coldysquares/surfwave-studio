# SURFwave Studio

A local-first macOS creative-audio suite built around specialized rooms that share one project/source of truth.

**SURFwave** is the product family. **Studio** is the practical production room inside it.

## Product model

SURFwave is deliberately **not** one giant forced workflow.

A project may move between specialized rooms when useful:

- **Studio** — separate, rehearse, record, transform, mix, export
- **Voice Lab** — train and render reusable DDSP timbre models
- **Slopscore** — generative remix / playable-song experiments (separate repository for now)
- **Song Lab** — generate and explore new material (integration later)

The connective tissue is the **SURFwave Project**, not a six-step wizard.

## Current source snapshot

This repository is being initialized from the working **v5.8 Product Design Pass** macOS package.

Current shipped prototype characteristics:

- one macOS `.app`
- one Dock icon / one launcher window
- Studio + Voice Lab as working rooms
- local Python services hidden behind the app shell
- non-destructive audio project behavior
- Demucs / separator input path
- recording / overdubs
- mixer + render/export
- optional DDSP bridge and model tooling

## Design doctrine

SURFwave follows the shared **Graphic Web Utility** principle without copying WOLLOHY or TabbyCat cosmetically:

> PERSONALITY IN THE SHELL.  
> CLARITY IN THE TOOL.

For SURFwave that means its own product vocabulary: waveforms, meters, transport marks, stems, takes, signal flow, coastal color, and the SURFwave mark. The deeper the user gets into mixing/recording/performance, the quieter the branding becomes.

See `docs/DESIGN_LANGUAGE.md` and `docs/PRODUCT_MODEL.md`.

## Brand hierarchy

- Deep Shore `#403742` — anchor
- Coastal Blue `#89B5CC` — primary accent
- Mist `#E2DCE8` — light/reading surface
- Ocean Depth `#56548C` — secondary
- Twilight `#6D6380` — support

The mark is the surfboard/fin + wave gesture. The music-note variant is retired.

## Repository direction

This repo is the canonical source home. Customer-facing distribution should eventually be a signed/notarized macOS app with no exposed Homebrew/Python/command-file setup.

The old versioned ZIPs remain historical build artifacts, not the long-term source-of-truth architecture.
