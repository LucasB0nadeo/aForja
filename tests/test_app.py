import unittest

from platina_club import create_app


class ApplicationTests(unittest.TestCase):
    def test_homepage_is_available(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
            }
        )

        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"FORJA", response.data)
        self.assertIn(b"/static/styles.css", response.data)

        with app.test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session["user_id"] = 1
            authenticated_homepage = client.get("/")
        self.assertEqual(authenticated_homepage.status_code, 200)

        stylesheet = app.test_client().get("/static/styles.css")
        self.assertEqual(stylesheet.status_code, 200)
        try:
            self.assertIn(b"--forge-red", stylesheet.data)
        finally:
            stylesheet.close()

    def test_secret_key_is_required(self):
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
            create_app({"TESTING": True, "SECRET_KEY": ""})


if __name__ == "__main__":
    unittest.main()
