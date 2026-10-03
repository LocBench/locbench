# Post texts for piece 02

Ready to paste. Lengths are checked by `bin/verify_post.py`.

---

## r/LocalLLaMA

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
I measured the per-request fixed cost on three local engines: 0.058 s on Ollama, 0.095 s on llama.cpp, 0.179 s on TabbyAPI
```

**Body:**

```
The first piece I posted here looked at what `prompt_tokens_per_sec` actually
measures -- uncached tokens over time-to-first-token, in both llama.cpp and
TabbyAPI -- and found a fixed cost per request that the metric spreads over the
few new tokens, so that short prompts report a third of the real speed.

What I could not say was where the cost came from. The data was real usage, and
in real usage streaming, the `stream_options` flag and the client were all the
same set of requests. So I built a client and measured it properly.

**The fixed cost is the engine's.** Same prompt length, four ways of asking --
streaming or not, crossed with the telemetry flag -- each at four lengths, five
times each, fitted separately (at one length a bigger fixed cost and a slower
throughput look identical).

TabbyAPI, three cells: 0.179 / 0.176 / 0.174 s. Spread of 5 ms.
llama.cpp, four cells: 0.094 / 0.099 / 0.093 / 0.100 s. Spread of 7 ms.

Streaming adds nothing. The telemetry flag adds nothing. Whatever it is, it is
there however you ask.

**The cache cannot be imposed.** I asked for 25%, 50% and 75% of the prompt to
be already cached and got 0% back every time -- the threshold is somewhere
around 1,500 tokens of shared prefix, and even at 90% it failed once in five.
But the two ends answer the question: the same 2,024-token prompt takes 1.98 s
fully uncached and 0.35 s with 1,792 tokens cached. The line from the sweep
predicts both to within 35 ms, so the cached tokens are free. The cost is per
request, not per token re-read.

**And the engines differ.**

| engine | fixed cost | throughput |
|---|---|---|
| Ollama 0.34.4 | 0.058 s | 1182 tok/s |
| llama.cpp b427 | 0.095 s | 1105 tok/s |
| TabbyAPI / exllamav3 | 0.179 s | 1133 tok/s |

Same throughput within 7%. Per-request cost differs by 3.1x. All three measured
by the engines' own clocks -- llama.cpp gives `prompt_n`/`prompt_ms` in a
`timings` field, Ollama gives `prompt_eval_duration` on its native API, and
TabbyAPI's rate has to be inverted. Its OpenAI-compatible endpoint reports no
timing at all, so if you are measuring Ollama through that you are measuring
nothing.

For one long conversation none of this matters. For an agent making 400 short
calls to do one task, it is 23 seconds of overhead versus 71.

**And a correction to my own earlier piece.** That one published a fixed cost of
0.75 s, from opportunistic data. The controlled measurement says 0.18 s on the
same engine and card. Both are honest and they are not the same number -- the
opportunistic fit was over real client traffic, a different model, a cache 93%
full on average, and two sessions a week apart. I do not have the data to say
which of those did it. The direction is the usual one: the estimate was high.

Raw data, the client, the analysis scripts and the environment card are in the
repo, and every number above is one command away:
[REPO LINK]
```

---

## X

<!-- limit: 280 -- an X post -->

```
Measured the per-request fixed cost of a local engine — what it charges before it does any work:

Ollama      0.058 s
llama.cpp   0.095 s
TabbyAPI    0.179 s

Same throughput within 7%. It is not streaming and it is not the telemetry flag. It is the engine.
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
The cached tokens are free: the same prompt takes 1.98 s uncached and 0.35 s with 89% of it cached, and the line predicts both to 35 ms.

Asking for 25/50/75% cached gets you 0%. The threshold is around 1500 tokens of shared prefix.
```

---

## GitHub

The repository "About" field, 350 characters:

<!-- limit: 350 -- the About field of a GitHub repository -->

```
A measurement bench for local LLM inference. One variable at a time, raw data published, limits declared. Every number comes with the command that produced it.
```
