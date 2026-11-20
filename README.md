<p align="center">
  <img src="https://raw.githubusercontent.com/figranium/frowse/main/banner.png" alt="Frowse" width="100%">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/frowse">npm</a> •
  <a href="https://pypi.org/project/frowse/">PyPI</a> •
  <a href="https://github.com/figranium/folate">Folate</a> •
  <a href="https://github.com/figranium/frowse/blob/main/LICENSE">Apache 2.0</a>
</p>

<p align="center">
  A drop-in replacement for <code>agent-browser</code> that pairs ultra-lightweight DOM summaries with local <a href="https://github.com/figranium/folate">Folate</a> neural DOM grounding—cutting agent token costs by up to 90%+ per step.
</p>

Instead of dumping full accessibility trees or hundreds of `@eN` element references on every `snapshot`, **Frowse** returns a compact semantic summary of the page—just enough for an AI agent to craft a precise natural-language query for **Folate**, which traverses the live DOM locally on CPU (`10–25 ms`, `< 250 MB` RAM, `$0` API cost) and resolves the exact CSS/XPath selector.

---

## Overview

| Capability | `agent-browser` (Full Refs) | **Frowse** (`snapshot` + Folate) |
| :--- | :--- | :--- |
| **Snapshot Output** | Full accessibility tree / `@e1..@eN` list | Deduplicated region summary (~100–300 tokens) |
| **Repeated Grid / List Items** | Every item emitted individually | Collapsed (`"Add to cart" (x100)`, `+92 more`) |
| **Element Targeting** | `@eN` refs or manual CSS/XPath | Natural-language Folate prompts, CSS, XPath, or `@eN` |
| **Selector Grounding Cost** | Agent context tokens | `$0` (100% local CPU INT8 ONNX via `folate`) |
| **CLI Compatibility** | `agent-browser` | Drop-in `frowse` & `agent-browser` binaries |

### Key Capabilities

* **Ultra-Lightweight DOM Summary** — Groups visible interactive elements by semantic landmark (`dialog`, `header`, `nav`, `form`, `main`, `aside`, `footer`), preserves input types, labels, placeholders, and select options, and deduplicates repeated actions to keep token usage minimal.
* **Natural-Language Folate Grounding** — Pass plain descriptions directly to `click`, `fill`, `type`, `select`, `hover`, `check`, `get`, or `wait` (e.g. `frowse click "Run Search button"`), or inspect ranked matches with `frowse query`.
* **Persistent Session Daemon** — Keeps headless Chromium and the quantized `folate-int8` ONNX model warm in memory across CLI calls via per-session Unix sockets (`--session <name>`).
* **Drop-In `agent-browser` Compatibility** — Exposes both `frowse` and `agent-browser` CLI binaries, supports `--json`, `--headed`, `--cdp`, `--refs` (`@e1`, `@e2`), tabs, iframes, cookies, storage, dialogs, and screenshots.

---

## Quickstart

### Setup Prompt

Paste this prompt into your AI coding agent (Claude Code, Codex, Cursor, etc.) to install Frowse, its bundled skills, and verify everything works:

```text
Install and set up Frowse (https://github.com/figranium/frowse) for browser automation:
1. Install the CLI globally with `npm install -g frowse` (requires Python 3.10+; or use `pip install frowse`).
2. Install the bundled agent skills for your environment using `frowse skills install --target <claude|codex|cursor|agents>` (add `--global` to install in your home directory).
3. Verify the setup by running `frowse open https://example.com`, `frowse snapshot`, and `frowse close`.
4. Use `frowse` (and the installed Frowse skills) for any browser tasks in the future.
```

### Installation

Install globally via **npm** (recommended):

```bash
npm install -g frowse
```

Or run directly with `npx`:

```bash
npx frowse open https://example.com
```

> **Note:** Frowse requires Python 3.10+ on `PATH`. On first run, the CLI automatically provisions an isolated environment in `~/.frowse/venv` if `frowse` is not already installed.

Or install directly via **pip**:

```bash
pip install frowse
```

Or install from source:

```bash
git clone https://github.com/figranium/frowse
cd frowse
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Usage

```bash
# 1. Open a page (persistent session stays alive in the background)
frowse open https://example.com

# 2. Get a compact, Folate-ready DOM summary
frowse snapshot

# 3. Act using natural-language Folate prompts (or CSS / XPath / @eN)
frowse fill "Search packages input" "folate"
frowse select "Country dropdown" "Canada"
frowse click "Run Search button"

# 4. Read back state and close the session
frowse get text "#out"
frowse close
```

You can also query Folate directly without performing an action:

```bash
frowse query "Sign in link in header" --top-k 3
```

And if you need legacy `@eN` refs for an existing `agent-browser` workflow:

```bash
frowse snapshot --refs
frowse click @e1
```

---

## Commands

| Command | Description |
| :--- | :--- |
| `open <url>` | Launch browser & navigate (aliases: `goto`, `navigate`) |
| `snapshot` / `summary` | Lightweight Folate-ready DOM summary (`--section`, `--max-chars`, `--refs`) |
| `query <prompt>` / `folate` | Query Folate directly for ranked CSS/XPath selectors (`--top-k N`) |
| `click <sel\|prompt>` | Click element (`--button`, `--modifiers`, `--new-tab`) |
| `fill <sel\|prompt> <text>` | Clear and fill input |
| `type <sel\|prompt> <text>` | Type into element (`--clear`, `--delay <ms>`) |
| `select <sel\|prompt> <val>` | Select dropdown option by value or label |
| `get <prop> [sel\|prompt]` | Get `text`, `html`, `value`, `attr`, `title`, `url`, `count`, `box`, `styles` |
| `is <state> <sel\|prompt>` | Check `visible`, `enabled`, or `checked` |
| `wait <target>` | Wait for selector/prompt, `ms`, `--text`, `--url`, `--load`, or `--fn` |
| `tab [new\|close\|<id>]` | Manage tabs (`--label <name>`) |
| `frame <sel\|@ref\|main>` | Switch iframe context |
| `screenshot [path]` / `pdf <path>` | Capture screenshot (`--full`) or PDF |
| `eval <js>` | Execute JavaScript in the active page/frame |
| `close [--all]` | Close active session (or all sessions) |

Global flags: `--json`, `--session <name>`, `--headed`, `--timeout <ms>`, `--cdp <port|url>`, `--viewport <w>x<h>`, `--model-dir <path>`.

---

## Benchmarks

Independent subagent runs with **Gemini 4 Hydrogen Medium** in **Antigravity Cloud** (`o200k_base` CLI output tokens, no shared context) comparing **Frowse** (`0.1.0` with bundled `frowse` & `frowse-extract` skills) against **`agent-browser`** (`0.43.0`) across three real-world workflows:

| Workflow | Frowse (`o200k` tokens) | `agent-browser` (`o200k` tokens) | Token Reduction |
| :--- | :---: | :---: | :---: |
| **Google Store Pixel Ecosystem (< $1,000)** | **15,154** *(64 steps)* | **59,290** *(41 steps)* | **74.4%** (**3.9× lower**) |
| **Hacker News Top Stories + Comments** | **761** *(7 steps)* | **8,457** *(5 steps)* | **91.0%** (**11.1× lower**) |
| **crates.io Package Discovery (`ort`)** | **3,096** *(29 steps)* | **6,773** *(12 steps)* | **54.3%** (**2.2× lower**) |
| **Total (All 3 Workflows)** | **19,011** | **74,520** | **74.5%** (**3.9× lower**) |

> **Notes:** Token counts measure exact `o200k_base` CLI stdout/stderr during browser execution (`21,913` total for Frowse if also including initial `frowse skills show` reads). On all three workflows, both independent agents completed the task end-to-end and arrived at identical verified answers (the same 4-device $977.98 Google Pixel ecosystem on Google Store, the same top 3 stories + top comment on Hacker News, and the same `ort` crate metadata on crates.io).
>
> **Why more steps?** `agent-browser` takes fewer, much larger steps by dumping full accessibility trees on `snapshot`. Frowse instead uses compact summaries plus targeted micro-queries (`query`, scoped `get text`, `is enabled`, and small `eval` calls)—most responses are under 200 bytes—trading extra small CLI round-trips (and occasional Folate prompt disambiguation or extra stock checks) for **54%–91% fewer context tokens**.

<details>
<summary>Benchmark prompts</summary>

1. **Google Store Pixel Ecosystem (< $1,000):**
   > On the Google Store (`https://store.google.com/us/?hl=en-US`), find a full Google Pixel ecosystem (Pixel phone, Pixel Watch, and Pixel Buds — plus any other Google Pixel device if it fits) for under $1,000 total (pre-tax), with ONLY: (1) Brand new items (full outright purchase price, no trade-in), (2) Google-branded items only, (3) Sold & fulfilled directly by Google Store. Verify each item's exact configuration, outright price, and URL on its product/configurator page.

2. **Hacker News Top Stories + Comments:**
   > 1. Open `https://news.ycombinator.com/`
   > 2. Find the top 3 stories with at least 50 points (extract title, points, and comment count).
   > 3. Navigate to the comments page of the highest-scoring story among those 3, and extract the top-level first comment's author and a brief summary/excerpt of the comment.

3. **crates.io Package Discovery (`ort`):**
   > 1. Open `https://crates.io/`
   > 2. Search for `ort` using the search box.
   > 3. Open the `ort` crate page from the search results.
   > 4. Extract and report the latest version, release date/time, license, and repository URL (or Rust version/MSRV if shown).

</details>

---

## Bundled Agent Skills

Frowse bundles four lightweight, bloat-free `SKILL.md` guides (`frowse`, `frowse-extract`, `frowse-auth`, `frowse-debug`) covering Folate prompting, bulk extraction handoff, auth/sessions, and debugging:

```bash
frowse skills list                         # List bundled skills
frowse skills show frowse                  # Print Folate prompting skill
frowse skills install --target claude      # Install into .claude/skills/ (or agents, codex, cursor)
```

---

## License

Frowse is released under the [Apache 2.0 License](https://github.com/figranium/frowse/blob/main/LICENSE).
