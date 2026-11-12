# Mini Me reel (v2)

32.5 s, 1080×1920, 30 fps, H.264 + AAC, −14 LUFS. Designed to work with the sound off.

| File | Use |
|---|---|
| `Mini_Me_Reel_v2.mp4` | Post as-is (synthesized sound design) |
| `Mini_Me_Reel_v2_no_audio.mp4` | Add trending audio or a voiceover inside Instagram/TikTok |

## Edit and re-render

All copy and timing live in `index.html` (one `draw` function per scene, times in seconds). Audio cues live in `audio.py` and use the same timeline.

```bash
node render.js stills 0 9.5 20.6 31   # check layout at given times
node render.js frames                 # all frames -> frames/
python3 audio.py                      # -> sfx.wav
```

Encode (normalize to −14 LUFS first):

```bash
ffmpeg -i sfx.wav -af loudnorm=I=-14:TP=-1.5 sfx_norm.wav
ffmpeg -framerate 30 -i frames/%05d.jpg -i sfx_norm.wav -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest -movflags +faststart Mini_Me_Reel_v2.mp4
```

Needs Node with Playwright, Python 3 with numpy, ffmpeg, and the fonts Inter Display and JetBrains Mono.

Every on-screen claim comes from `eval/`: the ~600 vs 6,100 tokens figure is measured on the 61-record test profile (`eval/bench_scale.py`).
