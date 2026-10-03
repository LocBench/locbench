# Post texts for piece 02

Ready to paste. Lengths are checked by `bin/verify_post.py`.

---

## r/LocalLLaMA

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
Three engines on the identical weight file: the per-request fixed cost is 0.058 s, 0.095 s and 0.228 s
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

**It is not the streaming and it is not the flag.** Same prompt length, four ways
of asking, each at four lengths, five times each, fitted separately -- at one
length a bigger fixed cost and a slower throughput look identical.

TabbyAPI, three cells: 0.179 / 0.176 / 0.174 s. Spread of 5 ms.
llama.cpp, four cells: 0.094 / 0.099 / 0.093 / 0.100 s. Spread of 7 ms.

**The cache cannot be imposed.** I asked for 25%, 50% and 75% of the prompt to
be already cached and got 0% back every time; the threshold is around 1,500
tokens of shared prefix, and even at 90% it failed once in five. But the two
ends answer the question: the same 2,024-token prompt takes 1.98 s fully
uncached and 0.35 s with 1,792 tokens cached, and the line from the sweep
predicts both to within 35 ms. The cached tokens are free.

**Then I put them side by side, and three of them turned out to be running the
same file.** Not the same family -- `sha256 3445102e...`, 16,811 MB, verified:

| engine | fixed cost | throughput |
|---|---|---|
| Ollama 0.34.4 | **0.058 s** | 1182 tok/s |
| llama.cpp b427 | **0.095 s** | 1105 tok/s |
| LM Studio 69d945a | **0.228 s** | 714 tok/s |

Same weights, same card. Per-request cost differs 4x, throughput differs 1.7x,
and LM Studio is the slowest at both. TabbyAPI, on a different format, sits at
0.179 s.

**And five explanations are dead.** A fixed per-request cost invites "it's
obviously X", so I measured each rather than argued: not streaming, not the
telemetry flag, not re-reading the cached prefix, not the client's clock. The
last one was the interesting one -- if the engine is setting up to write, letting
it write more should cost more, so I swept the generation budget at 1, 64 and 256
tokens with everything else fixed: 0.212 / 0.211 / 0.192 s. Writing 256 times
more moves the fixed cost by 20 ms, in the wrong direction and inside the noise.

What is left is whatever the engine does at its own front door between receiving
a request and starting the forward pass. This data does not separate those, and
I am not going to pretend it does.

A practical note for anyone measuring engines: **four engines, four places for
the same number**, and two of them publish nothing at all on the
OpenAI-compatible endpoint most clients use.

| engine | where its window lives |
|---|---|
| TabbyAPI | `prompt_tokens_per_sec`, a rate, to be inverted |
| llama.cpp | `prompt_n` and `prompt_ms`, two numbers to divide |
| Ollama | `prompt_eval_duration`, nanoseconds, native API only |
| LM Studio | `time_to_first_token`, ready, native API only |

And a correction to my own earlier post: it published a fixed cost of 0.75 s
from opportunistic data. The controlled measurement says 0.18 s on the same
engine. Both are honest, they are not the same number, and I do not have the
data to say which difference did it. The direction is the usual one.

Data, client, analysis scripts and environment card are in the repo:
[REPO LINK]
```

---

## X

<!-- limit: 280 -- an X post -->

```
Measured the per-request fixed cost on local engines — what each charges before it does any work:

Ollama      0.058 s
llama.cpp   0.095 s
LM Studio   0.228 s

Same identical weight file (sha256 verified). Same card. 4x apart.
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
It is not streaming, not the telemetry flag, not the cached prefix, not the client's clock, and not setting up to generate: allowing 256x more output moved it by 20 ms.

What is left is the engine's own front door. I cannot separate those from here.
```

---

## GitHub

The repository "About" field, 350 characters:

<!-- limit: 350 -- the About field of a GitHub repository -->

```
A measurement bench for local LLM inference. One variable at a time, raw data published, limits declared. Every number comes with the command that produced it.
```
