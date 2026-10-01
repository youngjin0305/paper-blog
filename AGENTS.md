# Paper review workflow

When the user supplies a paper for the blog, use `paper_pipeline.py add` and `paper_pipeline.py daily` to create the post. Verify public citation metadata first. For an attached/local PDF, use `add <local.pdf> --metadata-file <citation.json>` so `daily` reads the supplied bytes. Do not write a new `content/` post directly or bypass the pipeline's validation to publish it. For a verified conceptual paper, set `studyType: "conceptual"` in the local citation metadata. The pipeline validates a detailed conceptual method and omits the experiment group; never invent experiments to pass validation. If the paper cannot satisfy the applicable checks, leave the pipeline's draft and report why.

Present a model ID as the model actually used only when the CLI response identifies it. If the CLI does not report one, label the configured value as a requested model. For a historical manual review without a model log, record the review method and unknown ID rather than guessing a specific Codex model.

Summary prompts should preserve the paper's English form for important, recurring, or translation-sensitive technical terms. Introduce them as Korean (original English) or retain English where Korean would change the meaning; keep terminology consistent and never invent an English expansion absent from the paper.
