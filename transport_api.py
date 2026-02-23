"""
Transport for London (TfL) API Integration
Provides transport data for property analysis
"""

import requests
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

# Configuration
TFL_APP_ID = os.getenv('TFL_APP_ID', 'afcaf66b')
TFL_APP_KEY = os.getenv('TFL_APP_KEY', '01143ec72ae2c8e4c3aa631e5f27b845')
TFL_BASE_URL = "https://api.tfl.gov.uk"

@dataclass
class Station:
    """Represents a transport station"""
    name: str
    station_id: str
    distance: float  # meters
    modes: List[str]
    lines: List[str]
    lat: float
    lon: float

class TransportAPI:
    """
    Transport for London API Client
    Provides transport connectivity data for properties
    """
    
    def __init__(self, app_id: str = None, app_key: str = None):
        self.app_id = app_id or TFL_APP_ID
        self.app_key = app_key or TFL_APP_KEY
        self.base_url = TFL_BASE_URL
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make authenticated request to TfL API"""
        url = f"{self.base_url}/{endpoint}"
        
        # Add auth params
        params = params or {}
        params['app_id'] = self.app_id
        params['app_key'] = self.app_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': f'Request failed: {str(e)}'}
        except Exception as e:
            return {'error': str(e)}
    
    def get_nearest_stations(self, lat: float, lon: float, radius: int = 1000) -> List[Station]:
        """
        Find nearest tube/rail stations to coordinates
        
        Args:
            lat: Latitude
            lon: Longitude  
            radius: Search radius in meters (default 1000m)
            
        Returns:
            List of Station objects sorted by distance
        """
        endpoint = "StopPoint"
        params = {
            'lat': lat,
            'lon': lon,
            'stopTypes': 'NaptanMetroStation,NaptanRailStation,NaptanPublicBusCoachTram',
            'radius': radius,
            'returnLines': 'true'
        }
        
        data = self._make_request(endpoint, params)
        
        if 'error' in data:
            return []
        
        stations = []
        for stop in data.get('stopPoints', []):
            station = Station(
                name=stop.get('commonName', 'Unknown'),
                station_id=stop.get('id', ''),
                distance=stop.get('distance', 9999),
                modes=stop.get('modes', []),
                lines=[line.get('name') for line in stop.get('lines', []) if line.get('name')],
                lat=stop.get('lat', 0),
                lon=stop.get('lon', 0)
            )
            stations.append(station)
        
        # Sort by distance
        stations.sort(key=lambda x: x.distance)
        return stations
    
    def get_journey_time(self, from_location: str, to_location: str) -> Optional[Dict]:
        """
        Get journey time between two locations
        
        Args:
            from_location: Starting point (postcode or station)
            to_location: Destination (postcode or station)
            
        Returns:
            Journey details or None if not found
        """
        # URL encode locations
        from_encoded = requests.utils.quote(from_location)
        to_encoded = requests.utils.quote(to_location)
        
        endpoint = f"Journey/JourneyResults/{from_encoded}/to/{to_encoded}"
        data = self._make_request(endpoint)
        
        if 'error' in data:
            return None
        
        journeys = data.get('journeys', [])
        if not journeys:
            return None
        
        # Get fastest journey
        fastest = min(journeys, key=lambda x: x.get('duration', 999))
        
        return {
            'duration_minutes': fastest.get('duration'),
            'arrival_time': fastest.get('arrivalDateTime'),
            'departure_time': fastest.get('startDateTime'),
            'modes': list(set([leg.get('mode', {}).get('name') for leg in fastest.get('legs', [])])),
            'fare': fastest.get('fare', {}).get('totalCost'),
            'legs': len(fastest.get('legs', []))
        }
    
    def calculate_transport_score(self, stations: List[Station]) -> Dict:
        """
        Calculate transport connectivity score
        
        Args:
            stations: List of nearby stations
            
        Returns:
            Dict with score and analysis
        """
        if not stations:
            return {
                'score': 0,
                'rating': 'Poor',
                'nearest_station': None,
                'nearest_distance': None,
                'has_tube': False,
                'has_rail': False
            }
        
        nearest = stations[0]
        distance = nearest.distance
        
        # Calculate score based on distance
        if distance < 500:
            score = 10
            rating = 'Excellent'
        elif distance < 1000:
            score = 8
            rating = 'Good'
        elif distance < 2000:
            score = 6
            rating = 'Acceptable'
        else:
            score = 3
            rating = 'Poor'
        
        # Check transport modes
        all_modes = set()
        for station in stations[:5]:  # Top 5 stations
            all_modes.update(station.modes)
        
        has_tube = 'tube' in all_modes
        has_rail = 'national-rail' in all_modes or 'overground' in all_modes
        has_bus = 'bus' in all_modes
        
        # Bonus for multiple modes
        if has_tube and has_rail:
            score = min(10, score + 1)
        
        return {
            'score': score,
            'rating': rating,
            'nearest_station': nearest.name,
            'nearest_distance': round(distance),
            'nearest_modes': nearest.modes,
            'nearest_lines': nearest.lines[:3],  # Top 3 lines
            'has_tube': has_tube,
            'has_rail': has_rail,
            'has_bus': has_bus,
            'total_stations': len(stations)
        }
    
    def get_transport_summary(self, lat: float, lon: float) -> Dict:
        """
        Get complete transport summary for a location
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Complete transport analysis
        """
        # Get nearest stations
        stations = self.get_nearest_stations(lat, lon, radius=2000)
        
        # Calculate score
        score_data = self.calculate_transport_score(stations)
        
        # Get top 3 stations detail
        top_stations = []
        for station in stations[:3]:
            top_stations.append({
                'name': station.name,
                'distance': round(station.distance),
                'modes': station.modes,
                'lines': station.lines[:3]
            })
        
        return {
            'connectivity_score': score_data,
            'nearest_stations': top_stations,
            'summary': f"{score_data['rating']} transport links. "
                      f"Nearest: {score_data['nearest_station']} "
                      f"({score_data['nearest_distance']}m). "
                      f"{'Tube available.' if score_data['has_tube'] else 'No tube nearby.'}"
        }
    
    def is_configured(self) -> bool:
        """Check if API credentials are configured"""
        return bool(self.app_id and self.app_key and 
                   self.app_id != 'your_app_id' and 
                   self.app_key != 'your_app_key')

# Global instance
transport_api = TransportAPI()

# Helper function for deal analysis
def get_transport_context(lat: float, lon: float) -> Dict:
    """
    Get transport context for deal analysis
    
    Args:
        lat: Property latitude
        lon: Property longitude
        
    Returns:
        Transport analysis for AI
    """
    if not transport_api.is_configured():
        return {'error': 'Transport API not configured'}
    
    try:
        return transport_api.get_transport_summary(lat, lon)
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    # Test the API
    print("🚇 Testing Transport API...")
    
    if not transport_api.is_configured():
        print("❌ API not configured. Check TFL_APP_ID and TFL_APP_KEY.")
        exit(1)
    
    # Test with Manchester coordinates (example)
    lat, lon = 53.4773, -2.2301  # Manchester Piccadilly area
    
    print(f"\n📍 Testing with coordinates: {lat}, {lon}")
    print("\nNearest stations:")
    
    stations = transport_api.get_nearest_stations(lat, lon)
    for i, station in enumerate(stations[:5], 1):
        lines = ', '.join(station.lines[:3]) if station.lines else 'N/A'
        print(f"  {i}. {station.name} - {station.distance:.0f}m - {lines}")
    
    print("\n📊 Transport Score:")
    score = transport_api.calculate_transport_score(stations)
    print(f"  Score: {score['score']}/10 ({score['rating']})")
    print(f"  Nearest: {score['nearest_station']} ({score['nearest_distance']}m)")
    print(f"  Has tube: {score['has_tube']}")
    
    print("\n✅ Test complete!")
