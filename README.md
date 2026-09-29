# PJF v2

Remote video game jobs open to someone living in Spain. Manual runs, no paid services, Python 3.9+ standard library only (nothing to install).

## Daily use

Runs happen on GitHub, the PC is only for looking and marking. That way only GitHub writes the results and the two copies never clash.

```
gh workflow run run.yml     # run on GitHub (or the "Run workflow" button in the Actions tab)
git pull                    # get the results
python pjf.py serve         # open the page with mark buttons
```

Marks (interesting, applied, hide) are saved to `marks.json`, which never leaves the PC. The phone page (GitHub Pages) is read-only.

Local runs still work for testing: `python pjf.py run` (options: `--probe N`, `--no-ats`, `--no-feeds`, `--no-remote`, `--no-workday`). Do not push local results; discard them with `git checkout state docs`.

`python -m unittest -v` runs the offline tests.

## Sources

| Group | Where | Setup |
|---|---|---|
| Company job boards | Greenhouse, Lever (US and EU), Ashby, SmartRecruiters, Workable, Recruitee, Teamtailor, Personio | Automatic: each name in `config/companies.txt` is looked up once (`--probe N` per run). Fix or force a board in `sources.json` > `boards` |
| Workday | big publishers | By hand: `sources.json` > `workday`, the careers page URL plus a search keyword |
| Game job feeds | RSS/Atom | `sources.json` > `feeds` |
| General remote boards | Remotive, RemoteOK, Himalayas, Jobicy, We Work Remotely, Working Nomads | `sources.json` > `remote_boards`. Only game companies are kept: listed companies, or ads that clearly mention games. Gambling is excluded |
| Sites to check by hand | Hitmarker, ArtStation, LinkedIn searches... | `sources.json` > `quick_links` |

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

