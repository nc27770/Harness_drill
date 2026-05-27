"""Gradio UI for the dispatch string. One-screen, catch-phrase gated.

The catch-phrase gate is the rate-limit. There is no real auth; if the
URL leaks, the only thing between the world and your video budget is
the word "harness". Treat it that way.
"""

from __future__ import annotations

import gradio as gr

from dispatch import (
    PARSER_INPUT_CAPABILITY,
    COMPOSER_OUTPUT_CAPABILITY,
    INPUT_MODALITIES,
    OUTPUT_MODALITIES,
    dispatch,
)

CATCH_PHRASE = "harness"


# ─────────────────────────────────────────────────────────────────────────────
# Capability filtering — UI dropdowns ask the matrices, not the modules
# ─────────────────────────────────────────────────────────────────────────────


def _parser_choices(input_modality: str) -> list[str]:
    return list(PARSER_INPUT_CAPABILITY[input_modality])


def _composer_choices(output_modality: str) -> list[str]:
    return list(COMPOSER_OUTPUT_CAPABILITY[output_modality])


def _detect_input_modality(asset) -> str:
    """Gradio File component returns a NamedString-like with `.name`
    pointing at a temp path; we sniff the extension."""
    if asset is None:
        return "text"
    name = getattr(asset, "name", str(asset))
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in {"png", "jpg", "jpeg", "webp", "gif"}:
        return "image"
    if ext in {"mp3", "wav", "m4a", "ogg", "flac"}:
        return "audio"
    if ext in {"mp4", "mov", "webm", "mkv", "mpeg", "avi"}:
        return "video"
    return "text"


# ─────────────────────────────────────────────────────────────────────────────
# Run handler
# ─────────────────────────────────────────────────────────────────────────────


def _run(unlocked, prompt, asset, output_modality, parser_slot, composer_slot,
         image_quality, video_duration, video_size, video_aspect):
    # Server-side phrase enforcement — UI visibility alone is not
    # sufficient since Gradio API routes are reachable directly.
    if not unlocked:
        return ("(locked)", None, None, None,
                "ERROR: catch phrase not validated for this session.", "")
    if not prompt or not prompt.strip():
        return ("(no prompt)", None, None, None, "Please enter a prompt.", "")

    input_modality = _detect_input_modality(asset)
    asset_uri = getattr(asset, "name", None) if asset is not None else None

    # The level-1 modules expect either an s3:// URI, an http(s):// URL,
    # or a local path. Gradio gives us a local temp path — pass it
    # straight through; assets.py in the modules handles local paths.
    result = dispatch(
        prompt=prompt.strip(),
        input_modality=input_modality,
        output_modality=output_modality,
        parser_slot=parser_slot,
        composer_slot=composer_slot,
        asset_uri=asset_uri,
        image_quality=image_quality,
        video_duration=int(video_duration),
        video_size=video_size,
        video_aspect=video_aspect,
        timeout=900.0,
    )

    if result.get("error"):
        return ("(error)", None, None, None,
                f"ERROR: {result['error']}",
                result.get("stderr", ""))

    canonical = result.get("canonical_output", "")
    presigned = result.get("presigned_url")

    # Route the canonical output to the right Gradio component.
    text_out = canonical if not canonical.startswith("s3://") else None
    image_out = presigned if (output_modality == "image" and presigned) else None
    audio_out = presigned if (output_modality == "audio" and presigned) else None
    video_out = presigned if (output_modality == "video" and presigned) else None

    summary_lines = [
        f"**Module dispatched:** `{result['module']}`",
        f"**Input modality (detected):** `{input_modality}`",
        f"**Output modality:** `{output_modality}`",
        f"**Parser → Composer:** `{parser_slot}` → `{composer_slot}`",
    ]
    parsed = result.get("parsed", {})
    if parsed.get("total_cost_usd") is not None:
        summary_lines.append(f"**Total cost:** ${parsed['total_cost_usd']:.4f}")
    if parsed.get("stage_latencies_s"):
        lats = parsed["stage_latencies_s"]
        summary_lines.append(f"**Stage latencies:** {', '.join(f'{x:.1f}s' for x in lats)}")
    if parsed.get("job_id"):
        summary_lines.append(f"**Async job id:** `{parsed['job_id']}`")
    if canonical.startswith("s3://"):
        summary_lines.append(f"**S3 URI:** `{canonical}`")
    summary = "\n\n".join(summary_lines)

    return (text_out or canonical, image_out, audio_out, video_out,
            summary, result.get("stderr", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Catch-phrase gate
# ─────────────────────────────────────────────────────────────────────────────


def _check_phrase(phrase):
    if (phrase or "").strip().lower() == CATCH_PHRASE:
        return (gr.update(visible=False),   # hide gate
                gr.update(visible=True),    # show app
                "",
                True)                       # session unlocked
    return (gr.update(visible=True),
            gr.update(visible=False),
            "Wrong phrase. Try again.",
            False)


# ─────────────────────────────────────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────────────────────────────────────


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Harness Drill — Dispatch") as demo:
        # Per-session unlock state. Gradio gives each browser session
        # its own gr.State, so unlocks don't leak across users.
        unlocked = gr.State(value=False)

        gr.Markdown("# Harness Drill — Dispatch (String 01)")
        gr.Markdown(
            "Routes any (input modality × output modality × parser × composer) "
            "request through the level-1 modules. Subprocess fan-out — each run "
            "shells out to the canonical module CLI."
        )

        # Gate.
        with gr.Group(visible=True) as gate:
            gr.Markdown("### Enter catch phrase to continue")
            phrase_in = gr.Textbox(label="Catch phrase", type="password",
                                   placeholder="(it's a single word)")
            unlock_btn = gr.Button("Unlock", variant="primary")
            phrase_msg = gr.Markdown("")

        # Main app.
        with gr.Group(visible=False) as app:
            with gr.Row():
                with gr.Column(scale=2):
                    prompt = gr.Textbox(label="Prompt", lines=3,
                                        placeholder="Describe what you want…")
                    asset = gr.File(label="Asset (optional — image / audio / video)",
                                    file_types=["image", "audio", "video"])

                with gr.Column(scale=1):
                    output_modality = gr.Dropdown(
                        label="Output modality",
                        choices=list(OUTPUT_MODALITIES),
                        value="text",
                    )
                    parser_slot = gr.Dropdown(
                        label="Parser slot",
                        choices=_parser_choices("text"),
                        value="anthropic-fast",
                    )
                    composer_slot = gr.Dropdown(
                        label="Composer slot",
                        choices=_composer_choices("text"),
                        value="anthropic-deep",
                    )

            with gr.Accordion("Modality-specific knobs", open=False):
                with gr.Row():
                    image_quality = gr.Dropdown(
                        label="Image quality (1i)",
                        choices=["low", "medium", "high"], value="low",
                    )
                    video_duration = gr.Slider(
                        label="Video duration sec (1j)",
                        minimum=2, maximum=10, step=1, value=4,
                    )
                    video_size = gr.Dropdown(
                        label="Video size (1j)",
                        choices=["1280x720", "1920x1080"], value="1280x720",
                    )
                    video_aspect = gr.Dropdown(
                        label="Video aspect (1j Veo)",
                        choices=["16:9", "9:16"], value="16:9",
                    )

            run_btn = gr.Button("Run", variant="primary")

            with gr.Tabs():
                with gr.Tab("Result"):
                    text_out = gr.Textbox(label="Text result", lines=8)
                    image_out = gr.Image(label="Image result", type="filepath")
                    audio_out = gr.Audio(label="Audio result")
                    video_out = gr.Video(label="Video result")
                with gr.Tab("Summary"):
                    summary_out = gr.Markdown()
                with gr.Tab("Raw stderr trace"):
                    stderr_out = gr.Code(label="Module stderr (parser IR + costs + latencies)",
                                         language="markdown")

            # Capability-driven dropdown updates.
            def _update_parser(asset_obj):
                im = _detect_input_modality(asset_obj)
                choices = _parser_choices(im)
                return gr.update(choices=choices,
                                 value=choices[0] if choices else None)

            def _update_composer(om):
                choices = _composer_choices(om)
                return gr.update(choices=choices,
                                 value=choices[0] if choices else None)

            asset.change(_update_parser, inputs=asset, outputs=parser_slot)
            output_modality.change(_update_composer,
                                   inputs=output_modality,
                                   outputs=composer_slot)

            run_btn.click(
                _run,
                inputs=[unlocked, prompt, asset, output_modality,
                        parser_slot, composer_slot,
                        image_quality, video_duration, video_size, video_aspect],
                outputs=[text_out, image_out, audio_out, video_out,
                         summary_out, stderr_out],
            )

        unlock_btn.click(_check_phrase, inputs=phrase_in,
                         outputs=[gate, app, phrase_msg, unlocked])
        phrase_in.submit(_check_phrase, inputs=phrase_in,
                         outputs=[gate, app, phrase_msg, unlocked])

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860)
