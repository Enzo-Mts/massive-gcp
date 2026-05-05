"""
Locustfile pour les tests de charge TinyInsta.
Chaque requête GET /api/timeline utilise un user DIFFERENT
pour éviter tout effet de cache côté Datastore ou App Engine.
"""
from locust import HttpUser, task, between
import random


class TimelineUser(HttpUser):
    """Simule un utilisateur qui consulte sa timeline."""

    wait_time = between(0, 0)

    NUM_USERS = 1000
    PREFIX = "user"

    @task
    def get_timeline(self):
        """Chaque requête choisit un user aléatoire différent."""
        user_id = random.randint(1, self.NUM_USERS)
        username = f"{self.PREFIX}{user_id}"
        self.client.get(
            f"/api/timeline?user={username}&limit=20",
            name="/api/timeline"
        )