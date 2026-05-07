"""
Locustfile pour les tests de charge TinyInsta.
Chaque utilisateur Locust fait exactement une requête GET /api/timeline
sur un user aléatoire, puis s'arrête. Le run se termine quand tous les
utilisateurs ont reçu leur réponse (succès ou erreur).
"""
from locust import HttpUser, task, between
from locust.exception import StopUser
import random


class TimelineUser(HttpUser):
    wait_time = between(0, 0)

    NUM_USERS = 1000
    PREFIX = "user"

    @task
    def get_timeline(self):
        user_id = random.randint(1, self.NUM_USERS)
        username = f"{self.PREFIX}{user_id}"
        self.client.get(
            f"/api/timeline?user={username}&limit=20",
            name="/api/timeline"
        )
        raise StopUser()