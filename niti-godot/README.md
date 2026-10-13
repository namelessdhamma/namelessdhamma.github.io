# «Нити» — Godot visual study (separate from «Синее море»)

**Status:** isolated Godot 4.7.2 proof-of-concept, not an approved music video or final song master.

## Behavior
- The visual theme follows the approved song *«Нити — Мир не рухнул»*: tension / fear → relief. No lyrics, audio masters, private song files or credentials are included.
- 52 continuous drawn threads, breathing color/light and non-repeating line curvature. Click/tap or **Space** to switch from contraction to release; **R** resets animation.
- Rendering is 16:9 at 1280×720 design resolution; all computation is CPU-side drawing, no Kaggle or paid GPU.
- Audio synchronization is **not implemented**: 106 BPM is musical context, not proof of timing. The project runs silently and does not touch the protected music source.

## Open
Open `project.godot` in Godot 4.7.2 and press F6/F5 or run the main scene.

## Headless render (when Godot & Xvfb installed)
```sh
NITI_RENDER_PREVIEW=1 xvfb-run -a godot --path . --rendering-method gl_compatibility --write-movie /tmp/niti-fear.avi --fixed-fps 24 --quit-after 72
NITI_RENDER_PREVIEW=1 NITI_PREVIEW_RELIEF=1 xvfb-run -a godot --path . --rendering-method gl_compatibility --write-movie /tmp/niti-relief.avi --fixed-fps 24 --quit-after 72
ffmpeg -i /tmp/niti-fear.avi -c:v libx264 -pix_fmt yuv420p /tmp/niti-fear.mp4
```
Preview variables force one state; they do not synchronize lyrics or replace independent visual review.

## Safety
No changes to `sinee-more-godot/**`, ND Music Studio canon, accepted track stems, Kaggle, or existing qualified A8 R02 video workflow. Keep song assets private.