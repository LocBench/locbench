# What an engine charges you before it does any work

The first piece ended with a measurement it could not explain. On 98 real
requests through a proxy in front of TabbyAPI, the prompt window fitted

```
time_to_first_token = 0.447 s + uncached_tokens / 943 tok/s
```

and the fixed cost — the 0.447 s, the part that does not depend on how much you
sent — could not be attributed. It showed up in the streaming requests (0.752 s)
and not measurably in the ones that were not (0.114 s), but the two groups did
not overlap in length, one of them was a single client, and that client was the
only one that did not ask for telemetry.

This is the controlled version. The answer is that the cost belongs to the
engine, that four engines running the **same weight file** differ by a factor of
4, and that six of the explanations one would reach for first are all wrong.

It also cost this piece a correction to its own method, and that correction is
the most useful thing here — so it comes before the numbers.

---

## 1. Four cells, seven lengths

The design is from the protocol, D1. The same prompt lengths, sent four ways —
streaming or not, crossed with the telemetry flag present or not — always from
the same measuring client, so the client is controlled by construction.

Both the cells and the lengths matter, and the first attempt had only the cells.
At a single length a cell with a larger fixed cost and a cell with a slower
throughput look the same: both take longer. And a fit whose shortest prompt is
at 400 tokens is extrapolating to zero from a long way off — the same mistake
this project criticises in the September data.

So every cell is walked at seven lengths, from 20 words to 4,000, three times
each, and fitted separately. Each intercept below carries its standard error.

**TabbyAPI**, EXL3, `qwen3.8-27b-uncensored-4.0bpw`, one RTX 3090, R² = 0.9973:

| cell | fixed cost |
|---|---|
| non-streaming, no flag | 0.148 ± 0.038 s |
| non-streaming, with `stream_options` | 0.151 ± 0.040 s |
| streaming, with `stream_options` | 0.144 ± 0.038 s |
| streaming, no flag | 0.148 ± 0.039 s |

**Spread of 7 milliseconds across all four.**

**llama.cpp**, on the same weight file as the engines in section 4, R² = 0.9999:

| cell | fixed cost |
|---|---|
| non-streaming, no flag | 0.099 ± 0.006 s |
| non-streaming, with the flag | 0.101 ± 0.006 s |
| streaming, with `stream_options` | 0.104 ± 0.006 s |
| streaming, no flag | 0.104 ± 0.006 s |

**Spread of 5 milliseconds against an error of 6 — every cell is the same cell.**

The telemetry flag is innocent. So is streaming. Whatever the cost is, it is
there however you ask for it.

Streaming does buy one thing, and it is not a smaller cost. It is a clock, and
section 3 is about what happens when you have one.

---

## 2. The cache cannot be imposed, and it is free anyway

D2 asks a different question: is the fixed cost per request or per token
re-read? The way to find out is to hold the prompt fixed and vary how much of it
is already in the cache.

The protocol is careful about the wording here, and running it shows why. **You
do not impose the cache, you ask for it and read back what happened.** The
engine reports `cached_tokens`, and that number — not the one requested — is the
measurement.

| fraction asked for | times the cache engaged | prompt window |
|---|---|---|
| 0% | 0 / 5 | 1.98 s |
| 25% | 0 / 5 | 1.96 s |
| 50% | 0 / 5 | 1.96 s |
| 75% | 0 / 5 | 1.96 s |
| 90% | 4 / 5 | 0.35 s |
| 99% | 5 / 5 | 0.35 s |

**Asked for a quarter, a half, three quarters of the prompt cached, the engine
cached nothing.** The threshold sits somewhere around 1,500 tokens of shared
prefix, and it also fails once in five at 90% — which is why the protocol asks
for the interval and not only the median.

The two ends answer the question. The same 2,024-token prompt takes 1.98 s fully
uncached and 0.35 s with 1,792 tokens cached. The line from D1 predicts 1.965 s
and 0.384 s for those two points, and across all thirty requests of D2 it is
never off by more than 0.035 s.

**The cached tokens are free.**

---

## 3. An engine's own clock is not one clock

The first version of this piece put four engines in one table, each measured by
its own reported window, and called that a comparison. It was not one. It was
four.

Every engine here publishes *something* and calls it the prompt time. They are
not the same interval. Over the same streamed requests — same client, same
lengths, same minute — the engine's own number and the client's own number
differ by this much:

| engine | its own clock | the client's clock | untimed |
|---|---|---|---|
| llama.cpp | 0.098 ± 0.003 s | 0.161 ± 0.010 s | **+63 ms** |
| TabbyAPI | 0.149 ± 0.043 s | 0.273 ± 0.044 s | **+124 ms** |

The 61 millisecond difference between those two gaps is not a property of either
engine's speed. llama.cpp stops its clock when the prompt has been evaluated;
TabbyAPI stops it when the first token has been sampled; neither covers getting
the bytes out of the process. Ranking engines by subtracting one of these from
the other charges the difference between two stopwatches to the engine.

D1 reproduces it from the other direction. The streaming cells of the four-cell
experiment, measured an hour earlier on the same machine, give llama.cpp a gap of
58 and 65 ms and TabbyAPI 128 and 131 ms. Four measurements, two engines, one
conclusion.

**And for half the field there is no engine number to argue about.** On the
OpenAI-compatible endpoint — the one every client actually speaks — Ollama
publishes token counts and no timings at all, and LM Studio publishes usage and
no timings. Their windows exist only on their own native APIs, which no generic
client calls. So a comparison built on "the engine's own clock" is, on this
surface, a comparison of two engines out of four.

This protocol already said which clock to use. Section 4 reads:

> The measurement client therefore always times the window itself and treats the
> engine's number as a cross-check where one exists, rather than as the source.

The piece had it the other way round. The rule was right and the write-up
ignored it, which is worth saying plainly because the corrected numbers are not
dramatically different — they are just finally comparable.

---

## 4. Four engines on one clock

Same cell, same lengths, same client, streamed. One instrument, four readings.
Both clocks are shown where an engine publishes one; the client's column is the
only one that exists for all four.

| engine | fixed cost | throughput | R² | its own clock |
|---|---|---|---|---|
| Ollama 0.34.4 | **0.105 ± 0.007 s** | 1158 tok/s | 0.9999 | — not published |
| llama.cpp b427 | **0.161 ± 0.010 s** | 1145 tok/s | 0.9998 | 0.098 s, 1152 tok/s |
| TabbyAPI / exllamav3 | 0.273 ± 0.044 s | 1106 tok/s | 0.9963 | 0.149 s, 1110 tok/s |
| LM Studio 69d945a | 0.416 ± 0.061 s | 729 tok/s | 0.9971 | — not published |

**Ollama, llama.cpp and LM Studio are the same file.** Not the same model family
and not the same bytes by coincidence: `sha256 3445102e…`, 16,811 MB, and the
path llama.cpp and LM Studio are both given is a symbolic link into Ollama's own
blob store —

```
models/lmstudio/orcarouter/Qwen3.8-27B-Uncensored/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
  -> /usr/share/ollama/.ollama/models/blobs/sha256-3445102e9cde5d5625...
```

— so it is one file on one disk, opened by three programs. Same weights, same
card, same machine. Per-request cost differs **4.0x**; throughput differs 1.6x.

**The two clocks agree on the slope and disagree on the intercept**, which is
exactly what a constant per-request offset does to a line. llama.cpp: 1145 tok/s
on the client's clock and 1152 on its own. TabbyAPI: 1106 and 1110. If the gap
were an artefact of measuring different things, it would show up in the slope
too. It does not.

**What the errors say.** All four numbers come from one clock, so these are
differences worth stating as such:

| pair | apart by | combined error | |
|---|---|---|---|
| Ollama — llama.cpp | 56 ms | 12 ms | 4.6σ |
| Ollama — LM Studio | 311 ms | 61 ms | **5.1σ** |
| llama.cpp — LM Studio | 255 ms | 62 ms | 4.1σ |
| llama.cpp — TabbyAPI | 112 ms | 45 ms | 2.5σ |
| TabbyAPI — LM Studio | 143 ms | 75 ms | **1.9σ** |

**The two ends are 4.0x apart and that is 5.1 sigma** — the widest the interval
allows is 3.2x and the narrowest 4.9x, so the factor survives its own error
bars. **The middle of the field does not.** TabbyAPI and LM Studio are 1.9σ
apart, which is not a separation, and llama.cpp is 2.5σ from TabbyAPI. Three of
the four could be reordered by a better measurement of any one of them, and this
piece does not claim otherwise.

**Two of the four carry errors four to nine times the others', and there is a
reason.** Over fourteen lengths, each measured five times, TabbyAPI's window is
not monotone: 164 tokens took 0.340 s and 214 tokens took 0.330 s, with spreads
of 10 ms and 0 ms. A prefill cannot be faster with more tokens, so at these
lengths TabbyAPI's window contains something that is not prefill. LM Studio's
row has the same shape in its own clock: 0.435 s at 126 tokens and 0.689 s at
406 is 1,100 tokens per second, where its own long prompts give 775. The two
ends of one line cannot belong to rates a third apart, and the intercept fitted
across them carries that disagreement in its error bar. Whatever
that is, it is not measured here, and it is why those two rows are quoted with
intervals four to nine times wider than the other two. **The piece does not rank
them against each other on a number it cannot pin down** — which is the
difference between the table above and the one this piece published first.

All four stream. The reply that arrives *after* the first chunk is 0.66 s for
TabbyAPI, 1.06 s for llama.cpp, 1.42 s for LM Studio and 1.65 s for Ollama — so
the client's clock is a time to first token on all four and not, on any of them,
the whole reply.

For someone running one long conversation none of this matters. For an agent
making four hundred short calls to do one task, the difference between Ollama
and LM Studio is 42 seconds of overhead against 166.

---

## 5. Six explanations, all wrong

A fixed per-request cost of a tenth of a second invites an obvious reply: it is
obviously *something*. So each candidate was measured rather than argued about.

| candidate | how it was tested | result |
|---|---|---|
| the streaming | the four cells of D1, seven lengths | **out** — 6 ms apart |
| the telemetry flag | the same four cells | **out** — same |
| re-reading the cached prefix | the 0% and 90% cells of D2 | **out** — cached tokens are free |
| preparing to generate | the output budget swept at 1, 64 and 256 tokens | **out** — see below |
| KV precision, flash attention, parallel slots | llama.cpp run under LM Studio's settings | **out** — 1.5% and 2.5% |
| the context size | LM Studio's intercept at 32k and at 64k | **out** — 0.220 against 0.225, inside the error |

The generation test is the one that needed a new knob:

| tokens allowed | fixed cost | R² |
|---|---|---|
| 1 | 0.212 s | 0.9967 |
| 64 | 0.211 s | 0.9938 |
| 256 | 0.192 s | 0.9949 |

Allowing a model to write **256 times more** moves the fixed cost by 20
milliseconds, in the wrong direction and inside the noise.

The configuration row was not a hypothesis so much as a suspicion that the
differences in section 4 were settings and not engines. llama.cpp was run three
times on the same file — flash attention on with `q8_0` KV, flash attention on
with `q4_0` KV, and four parallel slots instead of one — and came out at 1140,
1123 and 1112 tok/s. A 2.5% spread against a gap of 36%.

**What is left is the part of the engine that receives a request and hands it to
the model.** Tokenisation, template rendering, slot allocation, whatever happens
at the front door before the first forward pass. This data does not separate
those, and it would take someone who knows one of these engines from the inside
to do it. Six explanations are excluded. The seventh is where the cost lives, and
it is named rather than measured — except that section 7 measures one piece of
it.

---

## 6. Why LM Studio is slower, and it is not LM Studio

The throughput column in section 4 has a gap that needed explaining: LM Studio
reaches 729 tok/s where llama.cpp reaches 1145, on the same file. The
configuration differences above account for 2.5% of it.

The rest is the backend.

```
$ lms runtime ls
llama.cpp-linux-x86_64-nvidia-cuda-avx2@2.41.0
llama.cpp-linux-x86_64-vulkan-avx2@2.51.0         ✓   <- selected
```

LM Studio is running the **Vulkan** build of llama.cpp, not the CUDA one. Its
server log names `vulkan` throughout and `cuda` never, and reports
`ggml_vulkan: Device memory allocation` and `failed to allocate Vulkan0 buffer`.
Ollama and llama.cpp, on the same machine, use CUDA.

**This is not a preference that can simply be switched.** Selecting the CUDA
runtime and reloading makes LM Studio abort inside `llama_context` construction
— `signal=SIGABRT` — and on a smaller context it loads without offloading
anything: the process holds 756 MiB of VRAM, the model sits in system memory,
and a single short request takes a minute.

**And the Vulkan backend is at the edge of the card.** At a 64,000-token context
LM Studio loads the model and then fails to allocate the 256 MiB its speculative
decoding context wants, with 23 GB nominally free:

```
ggml_vulkan: vk::Device::allocateMemory: ErrorOutOfDeviceMemory
failed to allocate Vulkan0 buffer of size 268435456
```

At a 32,000-token context it loads. So the measurements in section 4 were taken
at 32k — and the context is not what moved the number: the same sweep at 64k,
when it still fitted, gave 0.225 ± 0.041 s against 0.220 ± 0.041 s at 32k.

On this machine, with this model, **Vulkan is the only backend that works for
LM Studio, it costs about a third of the prefill throughput, and it cannot
allocate a context the card has room for.** That is a fact about a backend, not
a ranking of the programs: the same llama.cpp code, the same weights, a
different way of reaching the card.

This is the single most useful thing in the piece, and it was found by trying to
explain a number rather than by measuring anything new.

---

## 7. What the words are worth

The weakest thing about every measurement above is the prompt. Sequences drawn
from a fixed vocabulary of a thousand words are not anyone's workload, and the
obvious objection is that real text tokenises differently and might carry a
different fixed cost.

So the same sweep was run twice, alternating, on llama.cpp: once on the
vocabulary, once on prose taken from this repository's own documents.

| run | vocabulary | real prose | difference |
|---|---|---|---|
| first | 0.096 ± 0.003 s | 0.112 ± 0.004 s | +16 ms |
| second | 0.097 ± 0.004 s | 0.110 ± 0.004 s | +13 ms |
| **median** | **0.097 s** | **0.111 s** | **+14 ms** |

Throughput is unchanged: 1123 and 1122 tok/s on the vocabulary, 1133 and 1134 on
the prose. The text moves the fixed cost and not the rate.

**And the order was controlled, because it had to be.** Run once as
vocabulary-then-prose, a 14 ms gap is exactly what a warming card looks like.
The runs went V, P, V, P: the intercept goes 0.096 → 0.112 → **0.097** → 0.110.
It comes back down when the vocabulary comes back. Machine drift is monotone; it
does not reverse.

Restricting both to a common range of tokens — 105 to 2,106, so neither fit is
extrapolating from a different place — leaves the gap at +16 ms. It is not an
artefact of the two runs having different token distributions, which they do:

| prompt | tokens, vocabulary | tokens, real prose | ratio |
|---|---|---|---|
| 20 words | 84 | 107 and 117 | 1.33x |
| 60 words | 124 | 167 and 234 | 1.62x |
| 150 words | 214 | 277 and 313 | 1.38x |
| 300 words | 364 | 581 and 593 | 1.61x |
| 2,000 words | 2106 | 3127 and 3233 | 1.51x |

**A word is not a unit of work.** The same word count is 1.3 to 1.6 times as
many tokens in real prose, and the two prose figures in each row are two
different passages of the same length: **up to 40% more tokens for the same
number of words.** A benchmark that states its prompt length in words is stating
a number that varies by half between two prompts it is treating as equal. The
fits above use the token count the engine reports, which is why this does not
disturb them.

The 14 ms is small and it is real, and it lands exactly where section 5 said the
remaining cost lives. Tokenising real text — punctuation, mixed case, subwords,
thousands of distinct words instead of a thousand repeated ones — is not free,
and it is part of the front door. It does not explain the other 84: llama.cpp's
fixed cost is 98 ms on its own clock, and this says 14 of those are the text. It
measures one piece of the thing that was named and not measured.

---

## 8. What was not done, and what was corrected

**Corrected, and this was the important one.** Section 3 used the engines' own
reported windows as the source and called the result a comparison. Two of those
windows differ by 61 ms in what they cover, and two of the four engines publish
no window at all on the endpoint most clients use. The ranking in section 4 is on
the client's clock, over streamed requests, and the numbers moved: the spread
between the fastest and the slowest engine is 4.0x, not the 3.6x the mixed table
showed, and the mixed table was never entitled to a spread at all.

**Corrected.** An earlier version of section 4 said three engines ran the same
weight file. They did not: the llama.cpp *service* was loading
`JonathanColetti/…Q4_K_M.gguf`, `sha256 bfbd68b3…`, while Ollama and LM Studio
loaded `orcarouter/…Q4_K_M.gguf`, `sha256 3445102e…`. Same model name, same
nominal quantization, 32 bytes different out of 16.8 GB. The llama.cpp
measurements in this piece were re-run on the correct file.

**Corrected.** An earlier fit of four cells at a single length gave llama.cpp
0.090 s. The same engine over seven lengths gives 0.106. Both fits are correct
and they disagree, because the intercept is an extrapolation and the shortest
prompt decides how far it has to extrapolate. Comparing cells is safe at any set
of lengths; quoting a number is only safe at lengths that pin it down.

**Corrected.** The client's own help said "a word is roughly a token". Section 7
measures it: 1.3x to 1.6x, and up to 40% between two prompts of the same length.

**Not done.**

- **One machine, one card.** A 3090, on this system, in these sessions.
- **One model.** Everything here is Qwen3.8-27B. Nothing says a 7B or a 70B
  behaves the same way.
- **The engines were measured one at a time**, because two do not fit on this
  card together. "In the same session" means within the same hour, with the
  environment card captured alongside.
- **The context sizes differ between engines** — 32k for LM Studio, 64k for
  llama.cpp, 128k for TabbyAPI — because that is what each one will load. The
  one place it was tested, on LM Studio, halving it moved the intercept by 5 ms.
- **D2 was run on TabbyAPI only.** The other engines might cache differently.
- **The two engines that carry the widest errors are unranked against each
  other**, for the reason given in section 4.
- **Four engines, four shapes for the same number**, and two of them publish
  nothing at all on the OpenAI-compatible endpoint most clients use:

  | engine | where its window lives |
  |---|---|
  | TabbyAPI | `prompt_tokens_per_sec`, a rate, to be inverted |
  | llama.cpp | `prompt_n` and `prompt_ms`, two numbers to divide |
  | Ollama | `prompt_eval_duration`, nanoseconds, **native API only** |
  | LM Studio | `time_to_first_token`, ready, **native API only** |

  Anyone comparing engines has been comparing whichever of these four they
  happened to be able to read — and on the surface they are all speaking, two of
  the four offer nothing.

---

## 9. Reproduce this

The raw data for everything above is in the repository, and each comparison is
one command. The files are named individually rather than globbed: a wildcard
pools the control experiments, and a pooled number looks like a measurement.

```bash
# the four engines, one clock
python3 bench/compare_engines.py --cell stream \
    data/2026-10-03-stream-ollama.jsonl data/2026-10-03-stream-llamacpp.jsonl \
    data/2026-10-03-stream-tabbyapi.jsonl data/2026-10-03-stream-lmstudio.jsonl

# the four cells of D1
python3 bench/analyze_d1.py data/2026-10-03-d1-llamacpp.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-tabbyapi.jsonl

# prose against the fixed vocabulary, and the order control
python3 bench/compare_engines.py --cell plain \
    data/2026-10-03-ordine-vocab-1.jsonl data/2026-10-03-ordine-corpus-1.jsonl \
    data/2026-10-03-ordine-vocab-2.jsonl data/2026-10-03-ordine-corpus-2.jsonl
```

`bench/measure.py` records the engine version on every row, because an engine
update moves these numbers and without the version a regression and a
configuration change look identical. `bench/environment.sh` prints the rest of
the card. `bin/verify_piece.py` recomputes every fit quoted here from the
committed files, so a number in the text can be checked against the data rather
than against the text.
