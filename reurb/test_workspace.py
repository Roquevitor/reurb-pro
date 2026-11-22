import sqlite3
import unittest

from workspace import ensure_schema


LEGACY_TABLES = (
    "projetos", "vertices", "pessoas", "prefeituras", "cartorios",
    "bairros", "logradouros", "cadastro_pessoas", "nucleos",
    "prefeitura_cartorios", "historico_logradouros", "auditoria",
)


class WorkspaceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE projetos(id INTEGER PRIMARY KEY, nome TEXT)")
        for table in LEGACY_TABLES:
            if table == "projetos":
                continue
            self.conn.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY, payload TEXT)")
        self.conn.execute("INSERT INTO projetos(id,nome) VALUES(7,'Projeto legado')")
        self.conn.execute("INSERT INTO pessoas(id,payload) VALUES(9,'Beneficiário legado')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_migrates_existing_rows_and_is_idempotent(self):
        ensure_schema(self.conn)
        ensure_schema(self.conn)
        org = self.conn.execute(
            "SELECT id FROM organizations WHERE slug='organizacao-principal'"
        ).fetchone()[0]
        self.assertEqual(
            self.conn.execute("SELECT organization_id FROM projetos WHERE id=7").fetchone()[0],
            org,
        )
        self.assertEqual(
            self.conn.execute("SELECT organization_id FROM pessoas WHERE id=9").fetchone()[0],
            org,
        )

    def test_new_legacy_route_inserts_get_default_workspace(self):
        ensure_schema(self.conn)
        self.conn.execute("INSERT INTO projetos(id,nome) VALUES(8,'Projeto novo')")
        self.conn.commit()
        self.assertEqual(
            self.conn.execute("SELECT organization_id FROM projetos WHERE id=8").fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
