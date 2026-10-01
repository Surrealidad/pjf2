"""Offline end-to-end tests with fake HTTP responses.

Run from the repo root:  python -m unittest -v
"""
import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pjf import config, feeds, filters, net, pipeline, server, state  # noqa: E402
from pjf.ats import slug_variants  # noqa: E402
from pjf.model import Job  # noqa: E402

TODAY = dt.date.today()
RECENT = (TODAY - dt.timedelta(days=5)).isoformat()
OLD = (TODAY - dt.timedelta(days=200)).isoformat()


def gh_job(title, loc, content="", updated=RECENT, n=1):
    return {"title": title, "location": {"name": loc}, "content": content,
            "absolute_url": f"https://example.test/gh/{n}", "updated_at": updated + "T10:00:00Z"}


GREENHOUSE = {"jobs": [
    gh_job("Senior Data Analyst", "Remote - Europe", "Join Studio Greenhouse!", n=1),
    gh_job("Junior Data Analyst", "Remote - Europe", n=2),
    gh_job("Producer", "Montreal, QC", n=3),
    gh_job("Lead Producer", "Remote - US", n=4),
    gh_job("Localization Manager", "Remote", n=5),
    gh_job("Senior Gameplay Engineer", "Remote - Europe", n=6),
    gh_job("Audio Director", "Remote", "<p>You must be located in the United States.</p>", n=7),
    gh_job("BI Developer", "Barcelona, Spain", n=8),
    gh_job("Data Scientist", "Remote - Europe", updated=OLD, n=9),
    gh_job("Live Ops Manager", "Europe", n=10),
]}
LEVER = [
    {"text": "Business Intelligence Lead", "categories": {"location": "Spain"},
     "workplaceType": "remote", "hostedUrl": "https://jobs.lever.co/leverco/1", "createdAt": int(
        dt.datetime.combine(TODAY, dt.time()).timestamp() * 1000)},
    {"text": "Sound Designer", "categories": {"location": "Stockholm"},
     "workplaceType": "onsite", "hostedUrl": "https://example.test/lv/2"},
]
SMARTR = {"content": [
    {"id": "111", "name": "Senior Producer", "releasedDate": RECENT + "T08:00:00.000Z",
     "company": {"identifier": "BigPub", "name": "BigPub"},
     "location": {"city": "Madrid", "country": "es", "remote": True, "fullLocation": "Madrid, Spain"}},
]}
RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>RGJ</title>
<item><title>Senior Data Analyst at Studio A</title><link>https://example.test/rgj/1</link>
<pubDate>{dt.datetime.combine(TODAY, dt.time()).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
<description>&lt;p&gt;Fully remote.&lt;/p&gt;</description></item>
<item><title>Senior Data Analyst at Studio Greenhouse</title><link>https://example.test/rgj/2</link></item>
<item><title>3D Artist at Studio B</title><link>https://example.test/rgj/3</link></item>
</channel></rss>""".encode()
ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>GJ</title>
<entry><title>Associate Producer - Studio C</title><link rel="alternate" href="https://example.test/gj/1"/>
<updated>2026-09-20T00:00:00Z</updated><summary>Remote within the EU.</summary></entry>
<entry><title>QA Producer - Studio D</title><link href="https://example.test/gj/2"/>
<summary>Office in Berlin.</summary></entry>
</feed>"""

ROUTES = {
    "https://boards-api.greenhouse.io/v1/boards/studiogreenhouse/jobs?content=true": GREENHOUSE,
    "https://api.lever.co/v0/postings/leverco?mode=json": LEVER,
    "https://api.smartrecruiters.com/v1/companies/bigpub/postings?limit=100": SMARTR,
    # "Wrong Name Games" guesses slug "wrong": a board that belongs to someone else
    "https://boards-api.greenhouse.io/v1/boards/wrong/jobs?content=true":
        {"jobs": [gh_job("Data Analyst", "Remote - Europe", "Welcome to Wrong Bank", n=99)]},
    "https://feed.test/rss": RSS,
    "https://feed.test/atom": ATOM,
}


class FakeNet:
    def __init__(self, routes):
        self.routes, self.calls = dict(routes), []

    def get(self, url, timeout=20, accept="*/*", data=None):
        self.calls.append(url)
        if data is not None:   # POST: route on url + offset
            url = f"{url}#{json.loads(data).get('offset', 0)}"
        if url not in self.routes:
            return 404, b""
        body = self.routes[url]
        if body is None:
            return 0, b""
        return 200, body if isinstance(body, bytes) else json.dumps(body).encode()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = {k: getattr(config, k) for k in dir(config) if k.endswith("_FILE")}
        for name in self.saved:
            setattr(config, name, root / Path(self.saved[name]).name)
        config.PAGE_FILE = root / "docs" / "index.html"
        config.COMPANIES_FILE.write_text("# test\nStudio Greenhouse\nLeverCo\nBigPub\nNo Board Games\nWrong Name Games\n",
                                         encoding="utf-8")
        config.SOURCES_FILE.write_text(json.dumps({
            "feeds": [{"name": "RGJ", "url": "https://feed.test/rss", "remote": True},
                      {"name": "GJ", "url": "https://feed.test/atom"},
                      {"name": "Dead", "url": "https://feed.test/dead"}],
            "quick_links": [{"name": "Hitmarker", "url": "https://hitmarker.net/jobs"}]}), encoding="utf-8")
        self.fake = FakeNet(ROUTES)
        self.real_get, net.get = net.get, self.fake.get
        self.logs = []
        self.clock = iter(f"2026-09-{d:02d}T10:00:00Z" for d in range(1, 29))
        self.real_now, state.now_ts = state.now_ts, lambda: next(self.clock)

    def tearDown(self):
        net.get = self.real_get
        state.now_ts = self.real_now
        for k, v in self.saved.items():
            setattr(config, k, v)
        self.tmp.cleanup()

    def run_once(self, **kw):
        return pipeline.run(log=self.logs.append, **kw)

    def jobs_by_title(self):
        db = state.load(config.JOBS_FILE, {})
        return {(j["title"], j["company"]): j for j in state.active_jobs(db)}


class TestPipeline(Base):
    def test_first_run(self):
        s = self.run_once()
        jobs = self.jobs_by_title()
        expected = {
            ("Senior Data Analyst", "Studio Greenhouse"): ("ok", "greenhouse"),  # ATS wins the feed duplicate
            ("Senior Data Analyst", "Studio A"): ("check", "RGJ"),
            ("Localization Manager", "Studio Greenhouse"): ("check", "greenhouse"),
            ("Live Ops Manager", "Studio Greenhouse"): ("check", "greenhouse"),
            ("Business Intelligence Lead", "LeverCo"): ("ok", "lever"),
            ("Senior Producer", "BigPub"): ("ok", "smartrecruiters"),
            ("Associate Producer", "Studio C"): ("check", "GJ"),
        }
        self.assertEqual({k: (j["verdict"], j["source"]) for k, j in jobs.items()}, expected)
        self.assertEqual(s["new"], 7)
        self.assertEqual(s["boards_failed"], ["feed:Dead"])
        for reason in ("role", "seniority", "not remote", "location", "old", "onsite"):
            self.assertIn(reason, s["dropped"], reason)
        reg = state.load(config.REGISTRY_FILE, {})
        self.assertEqual(reg["studio greenhouse"]["ats"], "greenhouse")
        self.assertEqual(reg["studio greenhouse"]["slug"], "studiogreenhouse")
        self.assertIsNone(reg["no board games"]["ats"])
        self.assertIsNone(reg["wrong name games"]["ats"])  # slug hit, but name not in the data
        self.assertTrue(reg["leverco"]["verified"])
        html = config.PAGE_FILE.read_text(encoding="utf-8")
        self.assertIn("Business Intelligence Lead", html)
        self.assertNotIn("__DATA__", html)

    def test_old_unverified_board_is_dropped(self):
        state.save(config.REGISTRY_FILE, {"wrong name games": {
            "name": "Wrong Name Games", "ats": "greenhouse", "slug": "wrong", "checked": "2026-09-01"}})
        self.run_once(probe=0, use_feeds=False)
        reg = state.load(config.REGISTRY_FILE, {})
        self.assertIsNone(reg["wrong name games"]["ats"])
        self.assertEqual(reg["wrong name games"]["rejected"], "greenhouse:wrong")
        self.assertTrue(any("dropped board" in line for line in self.logs))

    def test_second_run_state(self):
        self.run_once()
        # Second run: greenhouse drops the localization job, lever fails, feeds unchanged
        gh = {"jobs": [j for j in GREENHOUSE["jobs"] if j["title"] != "Localization Manager"]}
        self.fake.routes["https://boards-api.greenhouse.io/v1/boards/studiogreenhouse/jobs?content=true"] = gh
        self.fake.routes["https://api.lever.co/v0/postings/leverco?mode=json"] = None
        self.fake.calls.clear()
        s = self.run_once()
        jobs = self.jobs_by_title()
        self.assertNotIn(("Localization Manager", "Studio Greenhouse"), jobs)  # closed on a board that answered
        self.assertIn(("Business Intelligence Lead", "LeverCo"), jobs)         # board failed: job stays
        self.assertEqual(s["new"], 0)
        self.assertIn("lever:leverco", s["boards_failed"])
        # no re-probing: known boards are fetched directly, misses are never retried
        self.assertFalse(any("noboard" in u or "no-board" in u for u in self.fake.calls))

    def test_probe_limit(self):
        self.run_once(probe=1, use_feeds=False)
        reg = state.load(config.REGISTRY_FILE, {})
        self.assertEqual(list(reg), ["studio greenhouse"])


class TestPieces(Base):
    def test_slug_variants(self):
        self.assertEqual(slug_variants("The Game Kitchen"), ["thegamekitchen", "thekitchen", "the-game-kitchen"])
        self.assertEqual(slug_variants("Larian Studios"), ["larianstudios", "larian", "larian-studios"])

    def test_feed_parsing(self):
        items = feeds.parse_feed(ATOM)
        self.assertEqual(items[0]["link"], "https://example.test/gj/1")
        self.assertEqual(feeds.split_title("Producer at Studio X"), ("Producer", "Studio X", ""))
        self.assertEqual(feeds.split_title("Scape is hiring a Senior Producer to work from Anywhere"),
                         ("Senior Producer", "Scape", "Anywhere"))
        self.assertEqual(feeds.split_title("CI Games is hiring Senior Producer (Remote Job)"),
                         ("Senior Producer", "CI Games", ""))
        self.assertEqual(feeds.split_title("Mad Labs is hiring Roblox Producer (Contract, Remote) (Remote Job)"),
                         ("Roblox Producer (Contract, Remote)", "Mad Labs", ""))

    def test_name_check(self):
        from pjf.ats import name_matches
        self.assertTrue(name_matches("Keen Games", {"d": "Keen Games is hiring"}))
        self.assertFalse(name_matches("Keen Games", {"d": "We are keen on data"}))
        self.assertTrue(name_matches("Larian Studios", {"d": "At Larian we make RPGs"}))
        self.assertTrue(name_matches("Wooga", {"u": "https://wooga.com"}))

    def test_not_a_role(self):
        for title in ("Freelance Legal Translator | English to Galician", "Audio Transcription - Thai",
                      "Video Game LQA Testing", "Join Our Healthcare Linguist Talent Pool",
                      "Senior Farsi Linguistic QA Tester (Remote)"):
            j = Job("x", "x", title, "Co", "u", location="Remote Europe")
            self.assertEqual(filters.classify(j, TODAY), "role", title)
        j = Job("x", "x", "Senior Translation Project Manager", "Co", "u", location="Remote Europe")
        self.assertEqual(filters.classify(j, TODAY), "")

    def test_families(self):
        cases = {"Senior Localization Producer": "localization", "Audio Lead": "audio",
                 "Lead Data Engineer": "data", "Associate Producer": "production",
                 "Head of Studio Operations": "operations", "Senior Gameplay Programmer": ""}
        for title, fam in cases.items():
            self.assertEqual(filters.family(title), fam, title)

    def test_location_rule(self):
        def verdict(loc, remote=None, desc=""):
            j = Job("x", "x", "Senior Data Analyst", "Co", "u", location=loc, remote=remote, description=desc)
            reason = filters.classify(j, TODAY)
            return reason or j.verdict
        self.assertEqual(verdict("Remote - Spain"), "ok")
        self.assertEqual(verdict("Remote, EMEA"), "ok")
        self.assertEqual(verdict("Remote (Germany)"), "location")
        self.assertEqual(verdict("Remote - UK"), "location")
        self.assertEqual(verdict("Remote"), "check")
        self.assertEqual(verdict("Madrid", remote=True), "ok")
        self.assertEqual(verdict("Madrid"), "not remote")
        self.assertEqual(verdict("Hybrid - Barcelona"), "onsite")
        self.assertEqual(verdict("Paris / hybrid", remote=True), "onsite")
        self.assertEqual(verdict("Remote or Hybrid - Madrid"), "ok")
        self.assertEqual(verdict("San Francisco Bay Area or Remote (U.S.)"), "location")
        self.assertEqual(verdict("Remote - U.K."), "location")
        self.assertEqual(verdict("Rome / remote"), "location")
        self.assertEqual(verdict("Work Remotely - Massachusetts"), "location")
        self.assertEqual(verdict("Herat, Herat, Afghanistan", remote=True), "location")
        self.assertEqual(verdict("Remote Europe / Berlin"), "ok")
        self.assertEqual(verdict("Santiago de Compostela / remote"), "ok")
        self.assertEqual(verdict("", remote=True, desc="Remote scope Remote US Estimated Base Salary"), "location")
        self.assertEqual(verdict("Remote", desc="This role is US-only."), "location")
        self.assertEqual(verdict("Remote", desc="Open to remote (Canada) applicants"), "location")
        self.assertEqual(verdict("Remote", desc="Fully remote, US or Europe time zones"), "check")
        self.assertEqual(verdict("Remote", desc="Let us know. We work remote first."), "check")
        self.assertEqual(verdict("", desc="We are a remote-first studio."), "check")
        self.assertEqual(verdict("Remote", desc="Candidates must be located in Canada."), "location")


TT_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Fjord Games</title>
<item><title>Senior Data Analyst</title><link>https://fjordgames.teamtailor.com/jobs/1</link>
<pubDate>Mon, 21 Sep 2026 10:00:00 +0000</pubDate><description>Join Fjord Games.</description>
<remoteStatus>fully</remoteStatus><tt:locations><tt:location><tt:city>Europe</tt:city></tt:location></tt:locations></item>
<item><title>Lead Producer</title><link>https://fjordgames.teamtailor.com/jobs/2</link>
<description>Fjord Games office.</description><remoteStatus>hybrid</remoteStatus>
<tt:locations><tt:location><tt:city>Oslo</tt:city></tt:location></tt:locations></item>
</channel></rss>"""
PERSONIO = b"""<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs><position><id>77</id><subcompany>Meseta Games SL</subcompany><office>Remote</office>
<name>Localization Manager</name><jobDescriptions><jobDescription><name>About</name>
<value><![CDATA[<p>Meseta Games makes RPGs.</p>]]></value></jobDescription></jobDescriptions>
<createdAt>2026-09-20T10:00:00+00:00</createdAt></position></workzag-jobs>"""
REMOTIVE = {"jobs": [
    {"url": "https://remotive.test/1", "title": "Senior Data Analyst", "company_name": "Pixel Forge",
     "publication_date": RECENT + "T00:00:00", "candidate_required_location": "Worldwide",
     "description": "We build mobile games played by millions."},
    {"url": "https://remotive.test/2", "title": "Senior Data Analyst", "company_name": "Acme Bank",
     "candidate_required_location": "Worldwide", "description": "Banking."},
    {"url": "https://remotive.test/3", "title": "Data Analyst Lead", "company_name": "Lucky Games",
     "candidate_required_location": "Europe", "description": "Online casino and slots."},
    {"url": "https://remotive.test/4", "title": "Producer", "company_name": "LeverCo",
     "candidate_required_location": "Europe", "description": "Nothing about the product."},
]}
WD_API = "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/jobs"
WORKDAY = {"total": 2, "jobPostings": [
    {"title": "Senior Producer", "externalPath": "/job/Remote/Senior-Producer_R1",
     "locationsText": "Remote - Spain", "postedOn": "Posted 3 Days Ago"},
    {"title": "Senior Data Analyst", "externalPath": "/job/X/Data_R2",
     "locationsText": "2 Locations", "postedOn": "Posted Today"},
]}


class TestNewSources(Base):
    def setUp(self):
        super().setUp()
        config.COMPANIES_FILE.write_text("Fjord Games\nMeseta Games\nLeverCo\n", encoding="utf-8")
        config.SOURCES_FILE.write_text(json.dumps({
            "feeds": [], "remote_boards": ["Remotive"],
            "workday": [{"name": "Acme", "url": "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers"}],
            "boards": [{"name": "Manual Studio", "ats": "greenhouse", "slug": "studiogreenhouse"}],
        }), encoding="utf-8")
        self.fake.routes.update({
            "https://fjordgames.teamtailor.com/jobs.rss": TT_RSS,
            "https://mesetagames.jobs.personio.de/xml": PERSONIO,
            "https://remotive.com/api/remote-jobs?search=game": REMOTIVE,
            "https://remotive.com/api/remote-jobs?search=gaming": {"jobs": []},
            "https://remotive.com/api/remote-jobs?category=data": {"jobs": []},
            "https://remotive.com/api/remote-jobs?category=product": {"jobs": []},
            "https://remotive.com/api/remote-jobs?category=project-management": {"jobs": []},
            WD_API + "#0": WORKDAY,
        })

    def test_all_new_sources(self):
        s = self.run_once()
        jobs = {(j["title"], j["company"]): (j["verdict"], j["source"]) for j in self.jobs_by_title().values()}
        self.assertEqual(jobs[("Senior Data Analyst", "Fjord Games")], ("ok", "teamtailor"))
        self.assertNotIn(("Lead Producer", "Fjord Games"), jobs)                  # hybrid, Oslo
        self.assertEqual(jobs[("Localization Manager", "Meseta Games")], ("check", "personio"))
        self.assertEqual(jobs[("Senior Data Analyst", "Pixel Forge")], ("ok", "Remotive"))
        self.assertEqual(jobs[("Producer", "LeverCo")], ("ok", "Remotive"))       # known company
        self.assertNotIn(("Senior Data Analyst", "Acme Bank"), jobs)              # not games
        self.assertNotIn(("Data Analyst Lead", "Lucky Games"), jobs)              # gambling
        self.assertEqual(jobs[("Senior Producer", "Acme")], ("ok", "workday"))
        self.assertEqual(jobs[("Senior Data Analyst", "Acme")], ("check", "workday"))
        self.assertEqual(jobs[("Senior Data Analyst", "Manual Studio")], ("ok", "greenhouse"))  # manual board
        self.assertEqual(s["boards_failed"], [])
        db = state.load(config.JOBS_FILE, {})
        wd = next(r for r in db["jobs"].values() if r["title"] == "Senior Producer")
        self.assertEqual(wd["url"], "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/job/Remote/Senior-Producer_R1")

    def test_reprobe_old_misses_with_new_systems_only(self):
        state.save(config.REGISTRY_FILE, {"fjord games": {"name": "Fjord Games", "ats": None, "slug": None}})
        self.run_once(use_feeds=False, use_remote=False, use_workday=False)
        reg = state.load(config.REGISTRY_FILE, {})
        self.assertEqual(reg["fjord games"]["ats"], "teamtailor")
        self.assertFalse(any("greenhouse.io/v1/boards/fjord" in u for u in self.fake.calls))
        # a company that misses everywhere is not probed again
        self.fake.calls.clear()
        self.run_once(use_feeds=False, use_remote=False, use_workday=False)
        self.assertFalse(any("leverco" in u and "teamtailor" in u for u in self.fake.calls))

    def test_feed_detail_page(self):
        config.SOURCES_FILE.write_text(json.dumps({"feeds": [
            {"name": "RGJ", "url": "https://feed.test/rss", "remote": True, "detail_field": "Remote scope"}]}),
            encoding="utf-8")
        self.fake.routes["https://example.test/rgj/1"] = (
            b"<html><dt>Remote scope</dt><dd>Remote US</dd><p>Estimated Base Salary $95K</p></html>")
        self.run_once(use_ats=False, use_remote=False, use_workday=False)
        titles = {(j["title"], j["company"]) for j in self.jobs_by_title().values()}
        self.assertNotIn(("Senior Data Analyst", "Studio A"), titles)   # Remote US, read from the page
        # the 3D Artist item fails the role filter, so its page is never requested
        self.assertNotIn("https://example.test/rgj/3", self.fake.calls)

    def test_workday_helpers(self):
        from pjf import workday
        self.assertEqual(workday.parse_site("https://epicgames.wd5.myworkdayjobs.com/en-US/Epic_Games"),
                         ("epicgames.wd5.myworkdayjobs.com", "epicgames", "Epic_Games"))
        self.assertEqual(workday.posted_date("Posted 30+ Days Ago", dt.date(2026, 9, 30)), "2026-08-31")
        self.assertEqual(workday.posted_date("Posted Yesterday", dt.date(2026, 9, 30)), "2026-09-29")


class TestServer(Base):
    def test_marks_roundtrip(self):
        self.run_once()
        httpd = server.make_server(0)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{port}"
            page = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("<title>PJF</title>", page)
            key = next(iter(state.load(config.JOBS_FILE, {})["jobs"]))

            def post(body, ctype="application/json"):
                req = urllib.request.Request(base + "/api/marks", data=json.dumps(body).encode(),
                                             headers={"Content-Type": ctype}, method="POST")
                try:
                    return urllib.request.urlopen(req).status
                except urllib.error.HTTPError as e:
                    return e.code

            self.assertEqual(post({"key": key, "mark": "interesting"}), 200)
            self.assertEqual(state.load(config.MARKS_FILE, {})[key]["mark"], "interesting")
            self.assertEqual(post({"key": key, "mark": "delete-everything"}), 400)
            self.assertEqual(post({"key": "../etc", "mark": "hide"}), 400)
            self.assertEqual(post({"key": key, "mark": "hide"}, ctype="text/plain"), 415)
            self.assertEqual(post({"key": key, "mark": None}), 200)
            self.assertEqual(state.load(config.MARKS_FILE, {}), {})
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
