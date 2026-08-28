"""Lean database reads for feature construction.

The raw provider payload can be large, so model jobs select only columns used by
the leakage-safe feature builder instead of hydrating complete ORM rows.
"""

from sqlmodel import Session, select

from oddsmith.db import MatchObservation


def load_feature_observations(session: Session) -> list[MatchObservation]:
    rows = list(
        session.exec(
            select(
                MatchObservation.source_key,
                MatchObservation.league,
                MatchObservation.season,
                MatchObservation.kickoff_utc,
                MatchObservation.home_team,
                MatchObservation.away_team,
                MatchObservation.home_goals,
                MatchObservation.away_goals,
                MatchObservation.home_shots,
                MatchObservation.away_shots,
                MatchObservation.home_shots_on_target,
                MatchObservation.away_shots_on_target,
                MatchObservation.home_corners,
                MatchObservation.away_corners,
                MatchObservation.home_yellow_cards,
                MatchObservation.away_yellow_cards,
                MatchObservation.home_red_cards,
                MatchObservation.away_red_cards,
                MatchObservation.close_home_odds,
                MatchObservation.close_draw_odds,
                MatchObservation.close_away_odds,
            ).order_by(MatchObservation.kickoff_utc)
        )
    )
    return [
        MatchObservation(
            source_key=row[0],
            source="database",
            league=row[1],
            season=row[2],
            kickoff_utc=row[3],
            home_team=row[4],
            away_team=row[5],
            home_goals=row[6],
            away_goals=row[7],
            home_shots=row[8],
            away_shots=row[9],
            home_shots_on_target=row[10],
            away_shots_on_target=row[11],
            home_corners=row[12],
            away_corners=row[13],
            home_yellow_cards=row[14],
            away_yellow_cards=row[15],
            home_red_cards=row[16],
            away_red_cards=row[17],
            close_home_odds=row[18],
            close_draw_odds=row[19],
            close_away_odds=row[20],
            raw_payload={},
        )
        for row in rows
    ]
