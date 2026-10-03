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
engine, that three engines running the **same weight file** differ by a factor
of 3.6, and that six of the explanations one would reach for first are all
wrong.

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

**llama.cpp**, on the same weight file as the engines in section 3, R² = 0.9999:

| cell | fixed cost |
|---|---|
| non-streaming, no flag | 0.099 ± 0.006 s |
| non-streaming, with the flag | 0.101 ± 0.006 s |
| streaming, with `stream_options` | 0.104 ± 0.006 s |
| streaming, no flag | 0.104 ± 0.006 s |

**Spread of 5 milliseconds against an error of 6 — every cell is the same cell.**

The telemetry flag is innocent. So is streaming. Whatever the cost is, it is
there however you ask for it.

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

## 3. Four engines, three of them on one identical file

Every window here is the engine's own clock. Nothing is a client measuring a
server.

| engine | fixed cost | throughput | R² |
|---|---|---|---|
| Ollama 0.34.4 | **0.062 ± 0.005 s** | 1154 tok/s | 1.0000 |
| llama.cpp b427 | **0.106 ± 0.004 s** | 1140 tok/s | 1.0000 |
| TabbyAPI / exllamav3 1.5.2 | 0.152 ± 0.046 s | 1104 tok/s | 0.9961 |
| LM Studio 69d945a | **0.225 ± 0.041 s** | 717 tok/s | 0.9987 |

**The first, second and fourth rows are the same file.** Not the same model
family — the same bytes: `sha256 3445102e…`, 16,811 MB, checked by hash and
loaded by three different programs. Same weights, same card, same machine.

**What the errors say.** Ollama and llama.cpp are separated by 44 ms with
combined errors of 6 — that difference is real. llama.cpp and LM Studio are
separated by 119 ms with combined errors of 41. Ollama and LM Studio by 163 ms.

**TabbyAPI's position is not established by this data.** Its error is ten times
llama.cpp's, because its points do not lie on a straight line: over the same
seven lengths its stepping is irregular — 0.65 ms per token between 1,264 and
2,064 tokens, 1.8 ms per token between 214 and 364. The interval
[0.107, 0.198] overlaps both llama.cpp and LM Studio, and this piece does not
put it in a ranking it cannot support. Whatever produces that curvature is a
measurement this project has not made.

For someone running one long conversation none of this matters. For an agent
making four hundred short calls to do one task, the difference between Ollama
and LM Studio is 25 seconds of overhead against 90.

---

## 4. Six explanations, all wrong

A fixed per-request cost of a tenth of a second invites an obvious reply: it is
obviously *something*. So each candidate was measured rather than argued about.

| candidate | how it was tested | result |
|---|---|---|
| the streaming | the four cells of D1, seven lengths | **out** — 6 ms apart |
| the telemetry flag | the same four cells | **out** — same |
| re-reading the cached prefix | the 0% and 90% cells of D2 | **out** — cached tokens are free |
| preparing to generate | the output budget swept at 1, 64 and 256 tokens | **out** — see below |
| the client's own clock | the engine's timings used throughout | **out** — the window is the engine's |
| KV precision, flash attention, parallel slots | llama.cpp run under LM Studio's settings | **out** — 1.5% and 2.5% |

The generation test is the one that needed a new knob:

| tokens allowed | fixed cost | R² |
|---|---|---|
| 1 | 0.212 s | 0.9967 |
| 64 | 0.211 s | 0.9938 |
| 256 | 0.192 s | 0.9949 |

Allowing a model to write **256 times more** moves the fixed cost by 20
milliseconds, in the wrong direction and inside the noise.

The last row is worth spelling out, because it was not a hypothesis so much as a
suspicion that the differences in section 3 were configuration and not engines.
llama.cpp was run three times on the same file — flash attention on with `q8_0`
KV, flash attention on with `q4_0` KV, and four parallel slots instead of one —
and came out at 1140, 1123 and 1112 tok/s. A 2.5% spread against a gap of 40%.

**What is left is the part of the engine that receives a request and hands it to
the model.** Tokenisation, template rendering, slot allocation, whatever happens
at the front door before the first forward pass. This data does not separate
those, and it would take someone who knows one of these engines from the inside
to do it. Six explanations are excluded. The seventh is where the cost lives,
and it is named rather than measured.

---

## 5. Why LM Studio is 40% slower, and it is not LM Studio

The throughput column in section 3 has a gap that needed explaining: LM Studio
reaches 717 tok/s where llama.cpp reaches 1140, on the same file. The three
configuration differences above account for 2.5% of it.

The rest is the backend.

```
$ lms runtime ls
llama.cpp-linux-x86_64-nvidia-cuda-avx2@2.41.0
llama.cpp-linux-x86_64-vulkan-avx2@2.51.0         ✓   <- selected
```

LM Studio is running the **Vulkan** build of llama.cpp, not the CUDA one. Its
server log names `vulkan` nineteen times and `cuda` never, and reports
`ggml_vulkan: Device memory allocation` and `failed to allocate Vulkan0 buffer`.
Ollama and llama.cpp, on the same machine, use CUDA.

**This is not a preference that can simply be switched.** Selecting the CUDA
runtime and reloading makes LM Studio abort inside `llama_context` construction
— `signal=SIGABRT` — and on a smaller context it loads without offloading
anything: the process holds 756 MiB of VRAM, the model sits in system memory,
and a single short request takes a minute.

So on this machine, with this model, **Vulkan is the only backend that works for
LM Studio, and it costs 40% of the prefill throughput.** That is a fact about a
backend, not a ranking of the programs: the same llama.cpp code, the same
weights, a different way of reaching the card.

This is the single most useful thing in the piece, and it was found by trying to
explain a number rather than by measuring anything new.

---

## 6. What was not done, and what was corrected

**Corrected.** An earlier version of section 3 said three engines ran the same
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

**Not done.**

- **One machine, one card.** A 3090, on this system, in these sessions.
- **One model.** Everything here is Qwen3.8-27B. Nothing says a 7B or a 70B
  behaves the same way.
- **The engines were measured one at a time**, because two do not fit on this
  card together. "In the same session" means within the same hour, with the
  environment card captured alongside.
- **D2 was run on TabbyAPI only.** The other engines might cache differently.
- **The prompts are synthetic** — sequences drawn from a fixed vocabulary, not
  real text. Real prompts tokenise differently and might behave differently.
- **Four engines, four shapes for the same number**, and two of them publish
  nothing at all on the OpenAI-compatible endpoint most clients use:

  | engine | where its window lives |
  |---|---|
  | TabbyAPI | `prompt_tokens_per_sec`, a rate, to be inverted |
  | llama.cpp | `prompt_n` and `prompt_ms`, two numbers to divide |
  | Ollama | `prompt_eval_duration`, nanoseconds, **native API only** |
  | LM Studio | `time_to_first_token`, ready, **native API only** |

  Anyone comparing engines has been comparing whichever of these four they
  happened to be able to read.

---

## 7. Reproduce this

The raw data for everything above is in the repository, and each comparison is
one command. The files are named individually rather than globbed: a wildcard
pools the control experiments, and a pooled number looks like a measurement.

```bash
python3 bench/compare_engines.py \
    data/2026-10-03-sweep-ollama.jsonl data/2026-10-03-cfg-8093.jsonl \
    data/2026-10-03-sweep-lmstudio.jsonl data/2026-10-03-sweep-tabbyapi.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-llamacpp.jsonl
python3 bench/analyze_d1.py data/2026-10-03-d1-tabbyapi.jsonl
```

`bench/measure.py` records the engine version on every row, because an engine
update moves these numbers and without the version a regression and a
configuration change look identical. `bench/environment.sh` prints the rest of
the card.
