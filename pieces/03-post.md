# Post texts for piece 03

Ready to paste. Lengths are checked by `bin/verify_post.py`.

The main post carries the finding and the link; the reply carries the caveat, so
the main stays readable. Attach `pieces/fixed-cost-five.png` to the main post.

---

## X

<!-- limit: 280 -- an X post -->

```
The 4x was not the ceiling.

A fifth engine — HyperQwen/vLLM — came in at 0.052 s per request: half of Ollama, 7.9x below LM Studio. Same 27B class, one RTX 3090. The four-engine 4x was the edge of the sample, not a law.

https://github.com/LocBench/locbench
```

**Below it, as a reply:**

<!-- limit: 280 -- an X reply -->

```
Caveat first: HyperQwen ran the base 27B in W4A16; the other four ran the uncensored 27B in Q4_K_M/EXL3. Same class, not the same file. The next control is the same checkpoint in both. The 4x wasn't wrong; it was a sample.
```

---

## r/LocalLLaMA

Use this after the first post has had its day, not on the same day. The body is
native text, so the table is a code block and not a pipe table.

**Title:**

<!-- limit: 300 -- a Reddit post title -->

```
The 4x wasn't the ceiling: a fifth engine came in at 0.052 s per request
```

**Body:**

```
A fifth engine on the same 27B class, same RTX 3090, same client, same seven
lengths x three repetitions:

    HyperQwen/vLLM   0.0525 ± 0.0022 s   1532 tok/s
    Ollama           0.1047 ± 0.0071 s   1158 tok/s
    llama.cpp        0.1608 ± 0.0097 s   1145 tok/s
    TabbyAPI         0.2731 ± 0.0442 s   1106 tok/s
    LM Studio        0.4165 ± 0.0607 s    729 tok/s

The four-engine spread was 4.0x. With the fifth it is 7.9x. The caveat comes
before the conclusion: HyperQwen ran the base 27B in W4A16; the other four ran
the uncensored 27B in Q4_K_M/EXL3. Same class, not the same file. So this is a
sample boundary, not a same-checkpoint ranking. The next control is the same
checkpoint in both.

The piece, the raw data and the check that recomputes every number:
https://github.com/LocBench/locbench
```
