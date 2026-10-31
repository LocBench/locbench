# Contributing

The useful contribution here is **a number that does not reproduce**.

Open an issue with:

- the engine and its version
- the source commit, for llama.cpp, TabbyAPI or exllamav3
- the cell, the prompt length, and whether it streamed
- the raw JSONL line, or the command and its output
- the environment card (`bench/environment.sh`)

A disagreement is not a problem. It is the next measurement. If the number is
different and the method is sound, I will rerun it and publish the correction
with the piece — with your name or handle, unless you prefer otherwise.

No pull request is needed for a report. If you are changing code, run what CI
runs:

```bash
bin/reproduce.sh
```

It fetches the pinned sources, reruns the analyses, checks the chart and the
card, runs both gates and the tests. It is the same command the README gives a
reader.

The data in `data/` is CC BY 4.0: reuse it, redo it, build on it, and say where
it came from. The code is MIT.
