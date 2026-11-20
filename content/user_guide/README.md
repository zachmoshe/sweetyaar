# Parents' guide source

Builds `app/public/parents_user_guide.pdf` (ReportLab, A4). Edit `build_guide_a.py`;
the images are in `art/` and the app's tab icons come from `app/public/assets/`.

    uv run --no-project --with reportlab --with pillow python content/user_guide/build_guide_a.py /tmp/guide.pdf
    uv run --no-project --with pymupdf python tools/compress_guide.py /tmp/guide.pdf app/public/parents_user_guide.pdf

It needs the macOS fonts under `/System/Library/Fonts/Supplemental`. `ART_BRIEF_A_storybook.md`
describes the art style. `make release-app` checks the published guide against each release.
