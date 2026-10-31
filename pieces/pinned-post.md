# The pinned post

What the account is about, and what LocBench is, in one post. It goes out once
the repository is public, and it stays pinned.

The main post carries the finding and the link. The reply carries the numbers,
so the main post stays readable.

---

## X

<!-- limit: 280 -- the pinned X post -->

```
I got tired of "X tok/s" with no length, no cache, no build. So I built a bench on my one 3090: four engines, one 27B, one clock. A 4x gap before the first token. Then an 8B, and the ranking fell apart. That's LocBench. Don't trust me. Rerun it: https://github.com/LocBench/locbench
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
Same 27B, four engines, one clock. Cost before the first token:

Ollama    0.105 ± 0.007 s
llama.cpp 0.161 ± 0.010 s
TabbyAPI  0.273 ± 0.044 s
LM Studio 0.416 ± 0.061 s

On an 8B: llama.cpp 0.040, Ollama 0.046. Six ms apart at 0.4σ. The ranking isn't the engine's to keep.
```
