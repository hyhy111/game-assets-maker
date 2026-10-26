# Repository presentation assets

- `social-preview.png`: 1280 × 640, opaque PNG, below GitHub's 1 MB limit. Uses the GAM brand mark and an actual before/after frame of the robot-knight demo. Keep this still image for link sharing.
- `workflow.gif`: the README's animated before/after comparison using the same layout. Seven matching source and transparent frames play in sync at 10 FPS, with a 0.7-second cycle that repeats indefinitely.

Both panels use the same fixed source crop and scale across all frames, preserving the original motion. The complete source height fills each panel; only the sides are cropped, and the source panel has no added green padding. Only the two image panels animate; the typography, checkerboard, and layout remain fixed. The GIF shows processed animation output rather than the processing steps or processing time.

The Social Preview setting is separate from the README image. Upload `social-preview.png` under repository **Settings → General → Social preview → Edit → Upload an image**. Committing the file alone does not apply this setting. GitHub's documented repository REST and GraphQL mutations do not expose a social-preview upload field.

References:

- [GitHub social media preview guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)
- [Repository REST API](https://docs.github.com/en/rest/repos/repos#update-a-repository)
- [Repository GraphQL API](https://docs.github.com/en/graphql/reference/repos#updaterepositoryinput)
