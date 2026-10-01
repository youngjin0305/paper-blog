# Paper review workflow

When the user supplies a paper for the blog, use `paper_pipeline.py add` and `paper_pipeline.py daily` to create the post. Verify public citation metadata first. For an attached/local PDF, use `add <local.pdf> --metadata-file <citation.json>` so `daily` reads the supplied bytes. Do not write a new `content/` post directly or bypass the pipeline's validation to publish it. If a conceptual paper cannot satisfy the required methodology or experiment checks, leave the pipeline's draft and report why; never invent experiments to pass validation.

Present a model ID as the model actually used only when the CLI response identifies it. If the CLI does not report one, label the configured value as a requested model. For a historical manual review without a model log, record the review method and unknown ID rather than guessing a specific Codex model.
