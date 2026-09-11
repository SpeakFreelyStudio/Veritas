from veritas.memory import MemoryBank


def test_add_and_search(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    fid = m.add("The Delaware River forms the eastern border of Bucks County.")
    m.add("Bananas are high in potassium.")
    hits = m.search("What river borders Bucks County?")
    assert hits and hits[0].id == fid


def test_supersede_hides_old_fact(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    old = m.add("The meeting is on Tuesday.")
    new = m.supersede(old, "The meeting is on Thursday.")
    ids = [f.id for f in m.search("meeting day")]
    assert new in ids and old not in ids


def test_forget(tmp_path):
    m = MemoryBank(tmp_path / "m.db")
    fid = m.add("Temporary fact about zebras.")
    assert m.forget(fid)
    assert m.search("zebras") == []


def test_old_database_upgrades_and_stays_searchable(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE facts(id INTEGER PRIMARY KEY, content TEXT NOT NULL, source TEXT,"
              " trust REAL DEFAULT 0.8, created REAL, superseded_by INTEGER)")
    c.execute("INSERT INTO facts(content) VALUES ('The Lehigh River joins the Delaware at Easton.')")
    c.commit(); c.close()
    m = MemoryBank(path)
    assert m.search("Lehigh River") and m.stats()["facts"] == 1
