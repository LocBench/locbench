# Post texts for piece 02

Ready to paste. Lengths are checked by `bin/verify_post.py`.

---

## r/LocalLLaMA

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
Three engines, the same weight file, per-request cost 0.062 s vs 0.106 s vs 0.225 s
```

**Body:**

```
My first post here looked at what `prompt_tokens_per_sec` actually measures --
uncached tokens over time-to-first-token, in both llama.cpp and TabbyAPI -- and
found a fixed cost per request that the metric spreads over the few new tokens,
so a short prompt reports a third of the real speed.

What I could not say was where that cost comes from. In real usage, streaming,
the `stream_options` flag and the client were all the same set of requests. So I
built a client and measured it properly.

**It is not the streaming and it is not the flag.** Four cells -- streaming or
not, crossed with the telemetry flag -- each walked at seven prompt lengths from
20 words to 4,000, three times each, fitted separately. Every intercept carries
its standard error.

TabbyAPI: 0.148 / 0.151 / 0.144 / 0.148 s. Spread of 7 ms.
llama.cpp: 0.099 / 0.101 / 0.104 / 0.104 s. Spread of 5 ms, error 6.

**The cache cannot be imposed.** I asked for 25%, 50% and 75% of the prompt to
be already cached and got 0% back every time; the threshold is around 1,500
tokens of shared prefix, and at 90% it failed once in five. But the two ends
answer the question: the same 2,024-token prompt takes 1.98 s fully uncached and
0.35 s with 1,792 tokens cached, and the line from the sweep predicts both to
within 35 ms. The cached tokens are free.

**Then I put four engines side by side, and three of them are running the same
file.** Not the same family -- `sha256 3445102e...`, 16,811 MB, verified by hash:

| engine | fixed cost | throughput |
|---|---|---|
| Ollama 0.34.4 | **0.062 ± 0.005 s** | 1154 tok/s |
| llama.cpp b427 | **0.106 ± 0.004 s** | 1140 tok/s |
| LM Studio 69d945a | **0.225 ± 0.041 s** | 717 tok/s |

Same weights, same card. Per-request cost differs 3.6x, throughput differs 1.6x.
TabbyAPI, on a different format, sits at 0.152 s -- but its curve is not linear
over these lengths and its interval overlaps the others, so I am not ranking it.

**And six explanations are dead.** A fixed per-request cost invites "it's
obviously X", so I measured each: not streaming, not the telemetry flag, not
re-reading the cached prefix, not the client's clock, not setting up to generate
(allowing 256x more output moved it by 20 ms), and not the configuration --
llama.cpp re-run under LM Studio's KV precision, flash attention and slot count
came out within 2.5%.

What is left is whatever the engine does at its own front door between receiving
a request and starting the forward pass. I am not going to pretend I measured
that.

**The one that is worth your time if you use LM Studio on NVIDIA.** LM Studio is
40% slower than llama.cpp on the identical file, and it is not LM Studio:

```
$ lms runtime ls
llama.cpp-linux-x86_64-nvidia-cuda-avx2@2.41.0
llama.cpp-linux-x86_64-vulkan-avx2@2.51.0         ✓   <- selected
```

It runs the **Vulkan** build. Its log says `ggml_vulkan` throughout and `cuda`
never. And switching is not a matter of a menu: selecting the CUDA runtime makes
LM Studio abort inside `llama_context`, and on a smaller context it loads
without offloading at all -- 756 MiB of VRAM, the model in system memory, a
minute per short request. On this machine Vulkan is the only backend that works,
and it costs 40% of the prefill throughput.

**Two corrections to my own earlier posts**, since both were mine to make. An
earlier version said the three engines ran the same weight file; the llama.cpp
*service* was loading a different GGUF, `sha256 bfbd68b3...`, 32 bytes apart out
of 16.8 GB. And an earlier fit over four lengths instead of seven gave
llama.cpp 0.090 s instead of 0.106 -- the intercept is an extrapolation and the
shortest prompt decides how far it has to extrapolate.

Data, client, analysis scripts and environment card are in the repo:
[REPO LINK]
```

---

## X

<!-- limit: 280 -- an X post -->

```
If LM Studio feels slow on an NVIDIA card, check which llama.cpp build it picked:

  llama.cpp-...-vulkan-avx2    <- selected

Its CUDA builds abort or load without offloading. On Vulkan it gets 717 tok/s where llama.cpp on the same file gets 1140.
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
Same weight file (sha256 verified), three engines, per-request fixed cost:

Ollama      0.062 s
llama.cpp   0.106 s
LM Studio   0.225 s

Not streaming, not the telemetry flag, not the cache, not generation setup. It is what the engine does before the first forward pass.
```

---

## GitHub

The repository "About" field, 350 characters:

<!-- limit: 350 -- the About field of a GitHub repository -->

```
A measurement bench for local LLM inference. One variable at a time, raw data published, limits declared. Every number comes with the command that produced it.
```
