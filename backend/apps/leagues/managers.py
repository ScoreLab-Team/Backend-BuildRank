from django.db import models


class LeagueManager(models.Manager):

    def create_efficiency_leagues(self, temporada):
        divisions = ["Bronze", "Silver", "Gold"]

        return [
            self.create(
                nom=f"Lliga {div}",
                categoria="EFICIENCIA",
                divisio=div,
                temporada=temporada
            )
            for div in divisions
        ]

    def create_resilience_leagues(self, temporada):
        divisions = ["Bronze", "Silver", "Gold"]

        return [
            self.create(
                nom=f"Lliga {div}",
                categoria="RESILIENCIA",
                divisio=div,
                temporada=temporada
            )
            for div in divisions
        ]

    def create_progress_leagues(self, temporada):
        divisions = ["Bronze", "Silver", "Gold"]

        return [
            self.create(
                nom=f"Lliga {div}",
                categoria="PROGRES",
                divisio=div,
                temporada=temporada
            )
            for div in divisions
        ]

    def get_segmented_ranking(self, group):
        return self.participations.filter(
            building__grupComparable=group
        ).order_by("-score")