import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

class RFUScraper:
    def __init__(self, url):
        self.url = url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def fetch_data(self):
        """
        Fetches fixtures and results from the RFU website using the observed HTML structure.
        Returns a list of dictionaries with match details.
        """
        try:
            print(f"Fetching data from: {self.url}")
            response = requests.get(self.url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            matches = []
            
            # Process both Upcomming Fixtures and Recent Results
            # Structure: Each match is inside a .resultWrapper
            # The date/competition is in .coh-style-cardheaderlayout
            # The match info is in .coh-style-card-body
            
            result_wrappers = soup.select('.resultWrapper')
            print(f"Found {len(result_wrappers)} match wrappers")
            
            for wrapper in result_wrappers:
                match = self._parse_match_wrapper(wrapper)
                if match:
                    matches.append(match)
            
            # De-duplicate matches based on date and teams
            unique_matches = self._deduplicate_matches(matches)
            return unique_matches

        except Exception as e:
            print(f"Error scraping RFU: {e}")
            return []

    def _parse_match_wrapper(self, wrapper):
        try:
            # 1. Extract Date and Competition from Header
            header = wrapper.select_one('.coh-style-cardheaderlayout')
            if not header:
                return None
                
            date_str = header.select_one('.coh-style-card-left-date').get_text(strip=True)
            competition = header.select_one('.coh-style-sub-header-right').get_text(strip=True)
            
            # Parse Date: "Saturday, 31 Jan 2026"
            # Remove "Saturday, " prefix for easier parsing or parse full string
            try:
                # Format: %A, %d %b %Y
                match_date = datetime.strptime(date_str, "%A, %d %b %Y")
            except ValueError:
                # Fallback or logging
                print(f"Failed to parse date: {date_str}")
                return None

            # 2. Extract Teams and Scores from Body
            body = wrapper.select_one('.coh-style-card-body')
            if not body:
                return None
            
            home_team_elem = body.select_one('.coh-style-hometeam .coh-style-right-comp-name')
            away_team_elem = body.select_one('.coh-style-away-team .coh-style-right-comp-name')
            
            if not home_team_elem or not away_team_elem:
                return None
                
            home_team = home_team_elem.get_text(strip=True)
            away_team = away_team_elem.get_text(strip=True)
            
            # 3. Extract Scores (if available)
            # Home Score (Left side, usually aligned right visually in the score block)
            score_home_elem = body.select_one('.fnr-scores .fnr-align-right')
            # Away Score (Right side, usually aligned left visually in the score block)
            score_away_elem = body.select_one('.fnr-scores .fnr-align-left')
            
            result = None
            score = None
            
            if score_home_elem and score_away_elem:
                home_score = score_home_elem.get_text(strip=True)
                away_score = score_away_elem.get_text(strip=True)
                if home_score.isdigit() and away_score.isdigit():
                    score = f"{home_score}-{away_score}"
                    
                    # Determine Result relative to Guildford (assuming we know Guildford's name or can inference it)
                    # For now, we store the raw info. "Guildford" logic should happen in the service caller or here.
                    # Let's assume passed-in logic checks for "Guildford"
                    pass

            # 4. Determine Location and Opposition
            our_team = "Guildford"
            if our_team in home_team:
                opposition = away_team
                location = "Home"
            elif our_team in away_team:
                opposition = home_team
                location = "Away"
            else:
                # Not a Guildford match (unlikely given the URL, but possible)
                return None

            # 5. Determine Result (Win/Loss/Draw)
            result_status = "Pending"
            if score:
                h_score, a_score = map(int, score.split('-'))
                if location == "Home":
                    if h_score > a_score: result_status = "Win"
                    elif h_score < a_score: result_status = "Loss"
                    else: result_status = "Draw"
                else: # Away
                    if a_score > h_score: result_status = "Win"
                    elif a_score < h_score: result_status = "Loss"
                    else: result_status = "Draw"

            # 6. Check if match is upcoming (future) or result (past) determines "Pending" vs result
            if match_date > datetime.now() and not score:
                result_status = "Pending"

            return {
                'date': match_date,
                'opposition': opposition,
                'location': location,
                'result': result_status,
                'score': score,
                'competition': competition
            }
            
        except Exception as e:
            print(f"Error parsing match row: {e}")
            return None

    def _deduplicate_matches(self, matches):
        # Dedupe logic if needed (e.g. list might contain duplicates if scraping multiple sections)
        # Using a tuple of (date, opposition) as key
        unique = {}
        for m in matches:
            key = (m['date'], m['opposition'])
            unique[key] = m
        return list(unique.values())
