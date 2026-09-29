# PJF v2

Remote video game jobs open to someone living in Spain. Manual runs, no paid services, Python 3.9+ standard library only (nothing to install).

## Run on the PC

```
python pjf.py            # run, rebuild the page, open it with mark buttons
python pjf.py run        # run only
python pjf.py serve      # open the page with mark buttons, no run
python pjf.py page       # rebuild the page from saved state, no network
python -m unittest -v    # offline tests
```

`--probe N` sets how many new companies to look up on ATS boards per run (default 40). The first runs go through `config/companies.txt` about 40 names at a time. `--no-ats` and `--no-feeds` skip a source group.

Marks (interesting, applied, hide) are saved to `marks.json`, which never leaves the PC.

## Files

| Path | What | In git |
|---|---|---|
| `config/companies.txt` | game companies to look up on ATS boards, one per line | yes |
| `config/sources.json` | RSS/Atom feeds and the "sites to check by hand" links | yes |
| `state/ats_registry.json` | company to ATS board, found by probing. Edit by hand to fix a wrong slug | yes |
| `state/jobs.json` | every kept job with first/last seen | yes |
| `state/last_run.json` | summary of the latest run | yes |
| `docs/index.html` | the results page (GitHub Pages) | yes |
| `marks.json` | your marks | no |

## Rules

- Role families (title keywords): data, production, operations, localization, audio. Junior, intern, graduate and similar titles are dropped.
- Remote only. Location must be Spain, EU/Europe/EMEA or worldwide. Other country restrictions are dropped. Unclear cases are kept with a "check" tag.
- Postings older than 60 days are dropped when the source gives a date.
- A job disappears from the page when its board answers and no longer lists it. If a board fails, its jobs stay.

## GitHub setup (once)

1. Create a public repo (e.g. `pjf2`) and push this folder.
2. Settings > Pages > Deploy from a branch > `main`, folder `/docs`.
3. Settings > Actions > General > Workflow permissions > Read and write.
4. Actions tab > "PJF run" > Run workflow. The page updates at `https://surrealidad.github.io/pjf2/`.

The PC and GitHub share state through the repo: `git pull` before a local run, commit and push after.
