# Showcase README layout

The layout `/kirei-showcase` builds a full README rewrite from (pasted into the `kirei-showcase` agent prompt). Replace every `<...>`, drop every line whose facts do
not exist (no release yet, no website, one language), and keep the order. Images come from
`@noctcore/showcase-kit` (`showcase all`, `showcase hero`, `showcase readme --cols 2 --base .`).

````markdown
<div align="center">
  <img src="assets/showcase/hero.webp" alt="<Name>: <tagline>" width="100%" />

  <h1><Name></h1>

  <p><strong><One line: the product in plain words.></strong></p>

  <p>
    <a href="https://github.com/<owner>/<repo>/releases/latest">
      <img src="https://img.shields.io/github/v/release/<owner>/<repo>?style=flat&color=<accent hex without #>" alt="Latest release" />
    </a>
    <a href="https://github.com/<owner>/<repo>/actions/workflows/<ci>.yml">
      <img src="https://img.shields.io/github/actions/workflow/status/<owner>/<repo>/<ci>.yml?branch=<default>&style=flat&label=ci" alt="CI" />
    </a>
    <!-- packages: <img src="https://img.shields.io/npm/v/<pkg>?style=flat" alt="npm" /> -->
    <a href="LICENSE">
      <img src="https://img.shields.io/badge/License-<License>-lightgrey?style=flat" alt="<License> License" />
    </a>
  </p>

  <p>
    <a href="<download or live url>"><strong><Download | Live site></strong></a>
    &nbsp;·&nbsp;
    <a href="<docs url>"><strong>Docs</strong></a>
    &nbsp;·&nbsp;
    <a href="CHANGELOG.md"><strong>Changelog</strong></a>
    &nbsp;·&nbsp;
    <a href="README.<lang>.md"><Language name></a>
  </p>

  <blockquote>
    <p><Two sentences: who it is for and what it does, concretely.></p>
  </blockquote>
</div>

---

### What is <Name>?

<One short paragraph. What problem, what it does about it, what makes it different. Plain words.>

### Screenshots

<paste `showcase readme --cols 2 --base .` output: a 2 column <table> with <sub> captions>

### What's inside

|                    |                                                    |
| ------------------ | -------------------------------------------------- |
| **<Feature>**      | <What it does, in one line, verified in the code>  |

### Built with

|           |                                              |
| --------- | -------------------------------------------- |
| Framework | <name and major version from the manifest>   |
| Language  | <...>                                        |
| Styling   | <...>                                        |
| Tooling   | <lint, test, release tools that exist>       |

### Getting started

<Prerequisites from `engines` / `packageManager`.>

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
<pm> install
cp .env.example .env    # on Windows cmd: copy .env.example .env
<pm> dev
```

| Command      | What it does |
| ------------ | ------------ |
| `<pm> <cmd>` | <...>        |

### Showcase images

The images in this README are captured with
[`@noctcore/showcase-kit`](https://www.npmjs.com/package/@noctcore/showcase-kit): `<pm> showcase` rebuilds them
(<one line: what it starts and what it freezes>).

### Releases

<How releases happen: tags, changesets, semantic-release; where the changelog is.>

### License

<License>, see [LICENSE](LICENSE).
````

## Notes

- Libraries: replace "Screenshots" with a short usage example when there is nothing to capture, and keep the API
  reference (below "What's inside", or linked in `docs/`).
- Terminal apps: a clip (`.webp` or `.gif` from `showcase record`) can replace the hero or lead the screenshots.
- A second language gets its own `README.<lang>.md` with images from `assets/showcase/<lang>/`.
