# The 4x was not the ceiling

The second piece ended with four engines, one clock, and a 4.0x spread. It also
ended with a warning: **the ranking is not the engines' to keep.** The obvious
next question was whether the 4x was a property of local inference or a property
of the sample.

A fifth engine was already installed. It came in at **0.052 s per request** —
half of Ollama, **7.9x** below LM Studio. The 4x was not the ceiling. It was the
edge of the sample.

---

## 1. The fifth engine, and the comparison that is not quite the same

The engine is **HyperQwen**: vLLM 0.31.0 with a patch series, served from the
container `ghcr.io/syv-ai/hyperqwen@sha256:b628adf3…` on port 18020. It runs
`qwen3.8-27b`, the 27B W4A16 AutoRound checkpoint, on one RTX 3090.

The client is the same one that measured the other four: the same seven prompt
lengths, from 20 to 4,000 words, three repetitions each, streamed, 64 tokens of
output, the client's clock. Two sessions, back to back, same container, same
model.

The comparison is not the same file, and that has to be said before the numbers.
The four engines of the earlier campaign ran the **uncensored** Qwen3.8-27B —
Q4_K_M for Ollama, llama.cpp and LM Studio, EXL3 4.0bpw for TabbyAPI. HyperQwen
runs the **base** checkpoint in **W4A16**. Same nominal 27B, both around four
bits, different weights and a different format.

The protocol's rule is: same model and same quantization where possible, and
where it is not possible, say so and compare at equal nominal parameters and
quantization. This is a **same-class** replication, not a same-file comparison.
What it tests is whether a fifth independent runtime lands inside the four-engine
range. It does not isolate the checkpoint from the engine.

**Two sessions, because one number is not a replication.** The first gave
**0.0514 ± 0.0037 s**; the second **0.0541 ± 0.0014 s**. The two differ by 2.7 ms,
less than the error of the first. The combined fit over both sessions is
**0.0525 ± 0.0022 s**, with **1,532 tok/s** and R² = 0.99998. The number is not a
single run that happened to be fast.

---

## 2. Five engines, one clock

| engine | fixed cost | throughput | R² | what it ran |
|---|---|---|---|---|
| **HyperQwen / vLLM 0.31.0** | **0.0525 ± 0.0022 s** | 1,532 tok/s | 0.99998 | 27B base, W4A16, 31 Oct |
| Ollama 0.34.4 | 0.1047 ± 0.0071 s | 1,158 tok/s | 0.9999 | 27B uncensored, Q4_K_M, 3 Oct |
| llama.cpp b427 | 0.1608 ± 0.0097 s | 1,145 tok/s | 0.9998 | same file as Ollama, 3 Oct |
| TabbyAPI / exllamav3 | 0.2731 ± 0.0442 s | 1,106 tok/s | 0.9963 | 27B uncensored, EXL3 4.0bpw, 3 Oct |
| LM Studio 69d945a | 0.4165 ± 0.0607 s | 729 tok/s | 0.9971 | same file as Ollama, Vulkan, 3 Oct |

- The four-engine spread was **4.0x**. The five-engine spread is **7.9x**.
- HyperQwen is **2.0x** faster than Ollama in fixed cost, and **7.9x** faster
  than LM Studio.
- The order is HyperQwen, Ollama, llama.cpp, TabbyAPI, LM Studio. The middle is
  still not resolved: TabbyAPI and LM Studio are 1.9σ apart, and llama.cpp is
  2.5σ from TabbyAPI. The ends are now much farther apart than they were.
- Throughput is a separate column and a separate claim: HyperQwen is 32% above
  Ollama and 7.9x is **not** a throughput ratio. The fixed cost is the part
  before the first token; the throughput is the part after it.

---

## 3. What it means

The fixed cost is not a property of "local inference". It is a property of the
runtime. A fifth engine, on the same card and the same class of model, halves
the best case of the four-engine sample.

The four-engine 4x was **correct for its four engines**. It was not a bound. That
is the difference the method is supposed to make: a benchmark would have kept
the 4x and defended it; a measurement goes looking for a fifth engine and
publishes what the fifth engine does to the table.

It also repeats the lesson of the 8B: **the ranking is not the engines' to
keep.** The 8B run changed the order between Ollama and llama.cpp; the fifth
engine changes the top of the table. The next engine can change it again.

---

## 4. What it does not mean

**It is not a same-checkpoint comparison.** HyperQwen ran the base 27B in W4A16;
the other four ran the uncensored 27B in Q4_K_M or EXL3. The extra 2x could be
the runtime, the checkpoint, the quantization, or a mix. This experiment does not
separate them. The next control is the same checkpoint in HyperQwen — the
uncensored weights, prepared for vLLM — or the base model in the four engines,
which needs a GGUF and an EXL3 conversion.

**It is not the same date.** The four rows are from 3 October, with driver
595.99.02, kernel 7.2.6 and Ollama 0.34.4. The fifth is from 31 October, with
driver 595.112.07, kernel 7.3.0 and vLLM 0.31.0. I tried to rerun Ollama on the
current stack; its install cannot start a model because the `llama-server`
binary is missing, so the four rows remain the original campaign. This is a
cross-date comparison, and it is declared.

**It is one machine, one card, one 27B class, and prompts that are still not
anyone's real workload.** The limits from the earlier pieces stand. The 8B
reversal stands: on the 8B, llama.cpp and Ollama are 6 ms apart at 0.4σ, and no
pair of engines is separated. A fifth 27B engine does not make the ranking
general.

**And it is not a verdict on LM Studio.** Its row is the Vulkan build on this
machine, with the CUDA builds aborting or loading without offloading. The 729
tok/s and the 0.416 s belong to that configuration, not to the program in the
abstract.

---

## 5. Reproduce this

The four-engine campaign:

```bash
bin/reproduce.sh
```

The fifth engine, on the machine where the container lives:

```bash
cd ~/tools/HyperQwen && docker compose --profile single up -d
bash ~/Claude/LocBench/bench/run_hyperqwen.sh
```

The script reads the API key from the container's `.env`, warms up, runs the same
seven lengths and three repetitions, and writes the JSONL and the environment
card. The two sessions are committed as
`data/2026-10-31-stream-hyperqwen.jsonl` and
`data/2026-10-31-stream-hyperqwen-2.jsonl`; the card is
`data/2026-10-31-environment-hyperqwen.txt`.

The five-engine chart is computed, not drawn by hand:

```bash
python3 bench/plot_fixed_cost_five.py --check
```

It recomputes each intercept from the committed rows and exits non-zero if a
number has moved away from the one above.

---

## 6. What was not done

- **The same-checkpoint control.** It is the difference between "a fifth engine
  is faster" and "vLLM is faster on this checkpoint". The first is measured; the
  second is not.
- **A same-session rerun of the four.** The four rows are still the 3 October
  campaign; the fifth is 31 October. A five-engine session with all five loaded
  one after the other is the cleaner comparison, and it is not this one.
- **A second card, a 70B, and a real agent workload.** They were in the earlier
  "not done" list and they are still there.
- **The middle of the field.** TabbyAPI and LM Studio are not separated; a fifth
  engine does not resolve them.

The 4x was not the ceiling. It was the edge of the sample. The fifth engine is
not a footnote to the four-engine piece; it is the reason the number moved. That
is the method: add a row, publish what it does to the table, and say what the row
is not.
