# Canonical source layout

The repository should represent the product architecture, not the internal shape of a zipped macOS `.app` bundle.

```text
surfwave-studio/
├── src/
│   ├── launcher.py
│   ├── shared/
│   │   └── project.py
│   ├── studio/
│   │   ├── server.py
│   │   ├── index.html
│   │   └── assets/
│   └── voice_lab/
│       ├── app.py
│       ├── ddsp_voice_lab/
│       ├── static/
│       └── requirements*.txt
├── brand/
├── docs/
├── tests/
├── packaging/
└── scripts/
```

## Source of truth

The v5.8 Product Design Pass remains the known-working runtime reference while its files are normalized into this layout.

Do not preserve `Contents/Resources/Suite/...` as the development architecture simply because that is how the distributable app bundle was assembled.

## Runtime separation

Studio and Voice Lab remain independent processes behind one launcher.

- Studio runtime: lightweight audio/project workbench
- Voice Lab runtime: heavier DDSP/TensorFlow environment
- shared project module: dependency-free project manifest / asset ledger

The heavier ML dependency stack must not become a requirement merely to launch Studio.

## Data separation

User content never belongs in the repository.

- Studio user data stays under the user's music/application data locations
- Voice models/datasets stay under the user's Voice Lab data location
- project manifests use project-relative paths
- repository tests use temporary directories only

## Packaging

Customer-facing command files are migration/bootstrap implementation details, not the product interface. The end state remains one signed/notarized macOS app with one Dock icon and managed runtime setup.
