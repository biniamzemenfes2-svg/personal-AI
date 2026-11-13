import unittest

from memory.vector_store import VectorStore, cosine_similarity
from tests.helpers import FakeClient, TempCase


class CosineTests(unittest.TestCase):
    def test_basics(self):
        self.assertEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertEqual(cosine_similarity([0, 0], [1, 1]), 0.0)


class VectorStoreTests(TempCase):
    def test_store_and_search(self):
        vs = VectorStore(self.db, FakeClient(), "m")
        vs.store("I am learning Flask")
        vs.store("I like python")
        self.assertEqual(vs.search("flask question", top_k=1), ["I am learning Flask"])

    def test_malformed_record_skipped(self):
        vs = VectorStore(self.db, FakeClient(), "m")
        vs.store("I am learning Flask")
        with self.db.connect() as conn:
            conn.execute("INSERT INTO vector_memory (text, embedding) VALUES ('bad', 'not json')")
        self.assertEqual(vs.search("flask"), ["I am learning Flask"])

    def test_embedding_failure_returns_empty(self):
        class Broken:
            class embeddings:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("api down")
        vs = VectorStore(self.db, Broken(), "m")
        self.assertEqual(vs.store("x"), "Failed to process memory vector.")
        self.assertEqual(vs.search("x"), [])


if __name__ == "__main__":
    unittest.main()
