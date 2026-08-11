# Personal academic website (Quarto)

Minimal skeleton with two pages: Home and Papers. Expand from here whenever
you're ready (Code, Misc, CV, etc.) by adding a new `.qmd` file and a nav
entry in `_quarto.yml`.

## 1. Install Quarto locally

Download from https://quarto.org/docs/get-started/ (pick your OS). This lets
you preview the site on your own machine before pushing.

## 2. Preview locally

```bash
quarto preview
```

This opens a live-reloading local server — edit any `.qmd` file and see
changes instantly.

## 3. Fill in your details

- `_quarto.yml` — site title, your email/GitHub/LinkedIn links
- `index.qmd` — bio, research interests, news; replace `profile.jpg` with an
  actual photo (same filename, or update the `image:` field)
- `papers.qmd` — your actual papers; put PDFs in a `papers/` folder and link
  to them, e.g. `papers/mypaper.pdf`

## 4. Publish to GitHub Pages

Two options:

**Option A — GitHub Actions (recommended, fully automatic)**
This repo already includes `.github/workflows/publish.yml`. Steps:

1. Create a new GitHub repo (e.g. `yourusername.github.io` for a root domain,
   or any name for `yourusername.github.io/reponame`).
2. Push this folder to it:
   ```bash
   git init
   git add .
   git commit -m "Initial site"
   git branch -M main
   git remote add origin https://github.com/yourusername/YOUR-REPO.git
   git push -u origin main
   ```
3. In the repo on GitHub: **Settings → Pages → Source → Deploy from a
   branch → `gh-pages`**. The Action creates this branch automatically after
   your first push (check the "Actions" tab for progress).
4. Every future `git push` to `main` re-renders and re-publishes the site
   automatically — no need to run `quarto render` yourself.

**Option B — manual publish (no GitHub Actions)**
```bash
quarto publish gh-pages
```
Run this locally whenever you want to update the live site. Simpler, but you
have to remember to run it after every change.

## 5. Custom domain (optional, later)

If you get a personal domain, add a `CNAME` file with the domain name and
point its DNS at GitHub Pages — see
https://quarto.org/docs/publishing/github-pages.html#custom-domains
