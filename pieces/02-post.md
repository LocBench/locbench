# Post texts for piece 02

Ready to paste. Lengths are checked by `bin/verify_post.py`.

---

## r/LocalLLaMA

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
Four engines, one weight file: per-request cost 0.105 s vs 0.416 s, once you time them all with one clock
```

**Body:**

```
My first post here looked at what `prompt_tokens_per_sec` actually measures --
uncached tokens over time-to-first-token -- and found a fixed cost per request
that the metric spreads over the few new tokens.

This is the controlled version, on four engines. It is also a correction to my
own method, so that comes first.

**The engine's own clock is not one clock.** Every engine publishes something it
calls the prompt time, and they are not the same interval. Over the same
streamed requests -- same client, same lengths, same minute:

    llama.cpp   own clock 0.098 s   client's clock 0.161 s   63 ms untimed
    TabbyAPI    own clock 0.149 s   client's clock 0.273 s  124 ms untimed

llama.cpp stops its clock when the prompt has been evaluated; TabbyAPI when the
first token has been sampled; neither covers getting the bytes out. Ranking
engines by subtracting one from the other charges the difference between two
stopwatches to the engine. My earlier table did exactly that.

And on the OpenAI-compatible endpoint -- the one every client actually speaks --
Ollama and LM Studio publish token counts and **no timings at all**. So "the
engine's own clock" was, on that surface, a comparison of two engines out of
four.

**On one clock, all four, streamed. Same cell, same lengths:**

| engine | fixed cost | throughput |
|---|---|---|
| Ollama 0.34.4 | 0.105 ± 0.007 s | 1158 tok/s |
| llama.cpp b427 | 0.161 ± 0.010 s | 1145 tok/s |
| TabbyAPI / exllamav3 | 0.273 ± 0.044 s | 1106 tok/s |
| LM Studio 69d945a | 0.416 ± 0.061 s | 729 tok/s |

Ollama, llama.cpp and LM Studio are the **same file** -- `sha256 3445102e...`,
16,811 MB, verified by hash. Per-request cost differs 4.0x.

The two clocks agree on the slope and disagree on the intercept, which is
exactly what a constant per-request offset does to a line. llama.cpp: 1145 tok/s
on the client's clock, 1152 on its own. If the gap were an artefact of measuring
different things, it would move the slope too. It does not.

**If you run LM Studio on an NVIDIA card, this is the part worth your time.** It
is 36% slower than llama.cpp on the identical file, and it is not LM Studio:

    $ lms runtime ls
    llama.cpp-linux-x86_64-nvidia-cuda-avx2@2.41.0
    llama.cpp-linux-x86_64-vulkan-avx2@2.51.0      <- selected

It runs the **Vulkan** build. Selecting CUDA makes it abort inside
`llama_context`, or load without offloading at all -- 756 MiB of VRAM, the model
in system memory, a minute per short request. And at a 64k context it now fails
to allocate the 256 MiB its speculative decoding context wants, with 23 GB
nominally free. On this machine Vulkan is the only backend that works, and it
costs about a third of the prefill throughput.

**One more, if you ever report prompt length in words.** I ran the same sweep on
real prose from my own repository, alternating with the synthetic vocabulary to
control for the card warming up. The fixed cost moves 0.097 -> 0.111 s, the
throughput does not move, and the vocabulary-to-prose step reverses when it
goes back. But the interesting part is the token count:

    20 words    84 tokens (vocabulary)   107 and 117 (prose)
    60 words   124                       167 and 234
    300 words  364                       581 and 593

A word is not a unit of work. The same word count is 1.3x to 1.6x as many
tokens, and **up to 40% more between two passages of prose of the same length**.

**Two corrections to my own earlier posts, both mine to make.** An earlier
version said three engines ran the same weight file; the llama.cpp *service* was
loading a different GGUF, 32 bytes apart out of 16.8 GB. And an earlier fit over
four lengths instead of seven gave llama.cpp 0.090 s instead of 0.106 -- the
intercept is an extrapolation and the shortest prompt decides how far.

Six other explanations are dead, each measured rather than argued: not the
streaming, not the telemetry flag, not re-reading the cached prefix, not
preparing to generate, not KV precision or flash attention or slot count, not
the context size.

Data, client, analysis scripts and environment card are in the repo:
[REPO LINK]
```

---

## X

<!-- limit: 280 -- an X post -->

```
If LM Studio feels slow on an NVIDIA card, check which llama.cpp build it picked:

  llama.cpp-...-vulkan-avx2   <- selected

Its CUDA builds abort or load without offloading. On Vulkan it gets 729 tok/s where llama.cpp on the same file gets 1145.
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
Same weight file, four engines, per-request cost timed with one clock:

Ollama      0.105 s
llama.cpp   0.161 s
TabbyAPI    0.273 s
LM Studio   0.416 s

Their own reported windows say 0.098 and 0.149. They leave 63 ms and 124 ms of each request untimed.
```

---

## GitHub

The repository "About" field, 350 characters:

<!-- limit: 350 -- the About field of a GitHub repository -->

```
A measurement bench for local LLM inference. One variable at a time, raw data published, limits declared. Every number comes with the command that produced it.
```
